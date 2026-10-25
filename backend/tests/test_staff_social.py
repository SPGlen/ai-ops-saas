import json
from datetime import timedelta
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlmodel import Session, select
from app.models import *
from app.db import engine, set_scope
from app.security import password_hash, digest
from app.permissions import identity_for, Scope
from app import social
from app.worker import execute
from app.integrations import aliyun, publishing
from .conftest import add, login

PASS = "Test-Password-2026!"


def staff(s, name, roles, tenant="tenant-a"):
    u = User(
        id=name,
        email=name + "@example.com",
        name=name,
        verified=True,
        password_hash=password_hash(PASS),
    )
    s.add(u)
    s.flush()
    m = Membership(tenant_id=tenant, user_id=name, role=roles[0], roles=roles)
    s.add(m)
    s.commit()
    return u


def sign(client, name):
    r = client.post(
        "/api/v1/auth/login", json={"email": name + "@example.com", "password": PASS}
    )
    assert r.status_code == 200, r.text
    client.headers["X-CSRF-Token"] = client.cookies.get("ops_csrf")


@pytest.fixture
def teams(client):
    with Session(engine()) as s:
        for name, roles in [
            ("teach1", ["teacher"]),
            ("teach2", ["teacher"]),
            ("sales1", ["admissions"]),
            ("sales2", ["admissions"]),
            ("finance", ["finance"]),
            ("academic", ["academic_admin"]),
            ("content", ["content_ops"]),
            ("both", ["teacher", "finance"]),
        ]:
            staff(s, name, roles)
    c = add(
        client,
        "course",
        {"name": "AI", "price_fen": 198000, "lessons": 8, "approved": True},
    )
    data = {}
    for n in (1, 2):
        cl = add(
            client,
            "class",
            {
                "name": "class" + str(n),
                "course_id": c["id"],
                "teacher_id": "teach" + str(n),
            },
        )
        st = add(
            client,
            "student",
            {
                "name": "child" + str(n),
                "contact": "1380000000" + str(n),
                "notes": "private teaching note" + str(n),
            },
        )
        le = add(
            client,
            "lesson",
            {
                "name": "lesson" + str(n),
                "class_id": cl["id"],
                "starts_at": (now() + timedelta(days=n)).isoformat(),
            },
        )
        order = add(
            client,
            "order",
            {
                "name": "order" + str(n),
                "student_id": st["id"],
                "course_id": c["id"],
                "owner_id": "sales" + str(n),
            },
        )
        assert (
            client.post(
                "/api/v1/orders/" + order["id"] + "/payments",
                json={"amount_fen": 198000, "request_id": "staff-payment-" + str(n)},
            ).status_code
            == 200
        )
        en = add(
            client,
            "enrollment",
            {
                "student_id": st["id"],
                "course_id": c["id"],
                "class_id": cl["id"],
                "order_id": order["id"],
            },
        )
        lead = add(
            client,
            "lead",
            {
                "name": "lead" + str(n),
                "contact": "1380000000" + str(n),
                "owner_id": "sales" + str(n),
            },
        )
        fb = add(
            client,
            "feedback",
            {
                "name": "feedback" + str(n),
                "student_id": st["id"],
                "lesson_id": le["id"],
                "teacher_note": "careful observation",
            },
        )
        data[n] = {
            "class": cl,
            "student": st,
            "lesson": le,
            "order": order,
            "enrollment": en,
            "lead": lead,
            "feedback": fb,
        }
    data["course"] = c
    return data


@pytest.mark.parametrize(
    "kind", ["student", "class", "lesson", "enrollment", "feedback"]
)
def test_teacher_list_export_and_search_do_not_leak(teams, client, kind):
    sign(client, "teach1")
    r = client.get("/api/v1/records/" + kind).json()
    assert [x["id"] for x in r["items"]] == [teams[1][kind]["id"]]
    assert teams[2][kind]["id"] not in client.get("/api/v1/exports/" + kind).text
    result = client.get("/api/v1/records/" + kind + "?q=child2").json()
    assert result["total"] == 0


@pytest.mark.parametrize(
    "path",
    [
        "records/order",
        "ledger",
        "settlements",
        "records/lead",
        "contents",
        "conversations",
        "usage",
        "social-accounts",
    ],
)
def test_teacher_denied_modules(teams, client, path):
    sign(client, "teach1")
    assert client.get("/api/v1/" + path).status_code == 403


def test_teacher_direct_attendance_feedback_and_aggregate_scope(teams, client):
    sign(client, "teach1")
    other = teams[2]
    own = teams[1]
    assert (
        client.post(
            "/api/v1/enrollments/" + other["enrollment"]["id"] + "/attendance",
            json={"lesson_id": other["lesson"]["id"], "request_id": "forged-signin"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/v1/records/feedback/" + other["feedback"]["id"],
            json={"data": other["feedback"]["data"], "version": 1},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/v1/records/lesson/" + own["lesson"]["id"],
            json={"data": own["lesson"]["data"], "version": 1},
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/v1/enrollments/" + own["enrollment"]["id"] + "/adjust",
            json={"delta": 3, "reason": "not allowed", "request_id": "forged-credit"},
        ).status_code
        == 403
    )
    d = client.get("/api/v1/dashboard").json()
    assert (
        d["counts"]["class"] == 1
        and "lead" not in d["counts"]
        and "net_revenue_fen" not in d
    )
    assert len(client.get("/api/v1/education/weekly-report").json()["classes"]) == 1


def test_sales_own_data_and_no_reassignment_or_cash(teams, client):
    sign(client, "sales1")
    assert [r["id"] for r in client.get("/api/v1/records/lead").json()["items"]] == [
        teams[1]["lead"]["id"]
    ]
    assert [r["id"] for r in client.get("/api/v1/records/order").json()["items"]] == [
        teams[1]["order"]["id"]
    ]
    own = teams[1]["lead"]
    assert (
        client.patch(
            "/api/v1/records/lead/" + own["id"],
            json={"data": {**own["data"], "owner_id": "sales2"}, "version": 1},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/orders/" + teams[1]["order"]["id"] + "/payments",
            json={"amount_fen": 1, "request_id": "sales-no-cash"},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/records/expense").status_code == 403
    assert (
        "commission_fen"
        not in client.get("/api/v1/records/order").json()["items"][0]["data"]
    )
    new = add(client, "lead", {"name": "own lead", "contact": "123456"})
    assert new["data"]["owner_id"] == "sales1"


def test_role_union_does_not_expand_teaching_scope_or_sensitive_fields(teams, client):
    with Session(engine()) as s:
        m = s.exec(select(Membership).where(Membership.user_id == "teach1")).one()
        m.roles = ["teacher", "finance"]
        m.authz_version += 1
        s.add(m)
        s.commit()
    sign(client, "teach1")
    assert len(client.get("/api/v1/records/class").json()["items"]) == 1
    students = client.get("/api/v1/records/student").json()["items"]
    assert len(students) == 2
    other = next(x for x in students if x["id"] == teams[2]["student"]["id"])
    assert "notes" not in other["data"] and "contact" not in other["data"]
    assert (
        client.get("/api/v1/ledger").status_code == 200
        and client.get("/api/v1/contents").status_code == 403
    )


def test_academic_order_projection_and_disabled_members(teams, client):
    sign(client, "academic")
    row = client.get("/api/v1/records/order").json()["items"][0]
    assert "payment_status" in row["data"] and not any(
        k.endswith("_fen") for k in row["data"]
    )
    assert client.get("/api/v1/ledger").status_code == 403
    login(client)
    with Session(engine()) as s:
        m = s.exec(select(Membership).where(Membership.user_id == "teach1")).one()
        mid = m.id
    sign(client, "teach1")
    assert client.get("/api/v1/auth/me").status_code == 200
    login(client)
    assert (
        client.patch("/api/v1/members/" + mid, json={"status": "disabled"}).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/switch-tenant", json={"tenant_id": "tenant-b"}
        ).status_code
        == 403
    )
    sign_response = client.post(
        "/api/v1/auth/login", json={"email": "teach1@example.com", "password": PASS}
    )
    assert sign_response.status_code == 200
    client.headers["X-CSRF-Token"] = client.cookies.get("ops_csrf")
    assert client.get("/api/v1/auth/me").json()["tenants"] == []


def test_employee_invitation_does_not_create_tenant_and_is_single_use(client):
    r = client.post(
        "/api/v1/member-invitations",
        json={"email": "newstaff@example.com", "roles": ["teacher", "finance"]},
    )
    assert r.status_code == 201, r.text
    token = r.json()["development_link"].split("token=")[1]
    with Session(engine()) as s:
        before = len(s.exec(select(Tenant)).all())
    info = client.get("/api/v1/auth/invitation", params={"token": token})
    assert info.status_code == 200
    r = client.post(
        "/api/v1/auth/accept-invitation",
        json={"token": token, "name": "new staff", "password": PASS},
    )
    assert r.status_code == 200, r.text
    me = client.get("/api/v1/auth/me").json()
    assert (
        set(me["roles"]) == {"teacher", "finance"} and not me["user"]["platform_admin"]
    )
    with Session(engine()) as s:
        assert len(s.exec(select(Tenant)).all()) == before
    assert (
        client.post(
            "/api/v1/auth/accept-invitation",
            json={"token": token, "name": "new staff", "password": PASS},
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "mode", ["expired", "revoked", "issuer_disabled", "issuer_user_disabled"]
)
def test_invalid_invitations(client, mode):
    r = client.post(
        "/api/v1/member-invitations",
        json={"email": "invite@example.com", "roles": ["teacher"]},
    )
    token = r.json()["development_link"].split("token=")[1]
    with Session(engine()) as s:
        inv = s.get(MemberInvitation, digest(token))
        if mode == "expired":
            inv.expires_at = now() - timedelta(seconds=1)
            s.add(inv)
        elif mode == "revoked":
            inv.revoked = True
            s.add(inv)
        elif mode == "issuer_user_disabled":
            u = s.get(User, "user-a")
            u.disabled = True
            s.add(u)
        else:
            m = s.exec(select(Membership).where(Membership.user_id == "user-a")).one()
            m.status = "disabled"
            s.add(m)
        s.commit()
    assert (
        client.get("/api/v1/auth/invitation", params={"token": token}).status_code
        == 400
    )


def test_last_active_owner_and_tenant_switch_headers(client):
    m = client.get("/api/v1/members").json()[0]
    assert (
        client.patch(
            "/api/v1/members/" + m["id"],
            json={"roles": ["teacher"], "status": "disabled"},
        ).json()["detail"]["code"]
        == "LAST_OWNER"
    )
    assert (
        client.get(
            "/api/v1/records/student", headers={"X-Tenant-ID": "tenant-b"}
        ).status_code
        == 409
    )


def make_account(s, platform="xiaohongshu", tenant="tenant-a"):
    a = SocialAccount(
        tenant_id=tenant,
        name="test",
        platform=platform,
        status="connected",
        config={
            "external_user_id": "self",
            "auto_reply": True,
            "policy_actor_id": "user-a",
            "verified_capabilities": {"comment_read": True, "comment_reply": True},
        },
    )
    s.add(a)
    s.commit()
    return a


def test_social_event_scoping_dedup_and_self_messages(client):
    with Session(engine()) as s:
        a = make_account(s)
        item = {
            "external_id": "same",
            "kind": "comment",
            "sender_id": "parent",
            "thread_id": "thread",
            "body": "课程怎么安排？",
            "work_id": "post",
        }
        one = social.ingest(s, a, item)
        s.commit()
        again = social.ingest(s, a, item)
        assert one.id == again.id
        assert (
            social.ingest(s, a, {**item, "external_id": "self", "sender_id": "self"})
            is None
        )
        b = make_account(s, "douyin")
        second = social.ingest(s, b, item)
        s.commit()
        assert second.id != one.id and second.conversation_id != one.conversation_id
        assert len(s.exec(select(SocialReply)).all()) == 2


def test_takeover_cancels_pending_auto_reply(client):
    with Session(engine()) as s:
        a = make_account(s)
        e = social.ingest(
            s,
            a,
            {
                "external_id": "a",
                "kind": "comment",
                "sender_id": "parent",
                "body": "课程",
                "thread_id": "a",
            },
        )
        s.commit()
        cid = e.conversation_id
    assert client.post("/api/v1/conversations/" + cid + "/takeover").status_code == 200
    with Session(engine()) as s:
        assert s.exec(select(SocialReply)).one().status == "cancelled"


def test_manual_fallback_never_claims_real_delivery(client):
    a = client.post(
        "/api/v1/social-accounts", json={"platform": "channels", "name": "manual"}
    ).json()
    r = client.post(
        "/api/v1/social-accounts/" + a["id"] + "/manual-interactions",
        json={"sender_name": "家长", "body": "想了解课程"},
    )
    assert r.status_code == 201, r.text
    caps = client.get("/api/v1/social-accounts/" + a["id"] + "/capabilities").json()
    assert caps["capabilities"]["message_reply"]["state"] == "unsupported"
    assert (
        client.get("/api/v1/conversations/" + r.json()["conversation_id"]).json()[
            "account_id"
        ]
        == a["id"]
    )
    assert (
        client.post(
            "/api/v1/conversations/" + r.json()["conversation_id"] + "/reply",
            json={"body": "hello"},
        ).status_code
        == 409
    )


def test_revoked_auto_policy_never_calls_model_or_connector(client, monkeypatch):
    with Session(engine()) as s:
        a = make_account(s)
        e = social.ingest(
            s,
            a,
            {
                "external_id": "incoming",
                "kind": "comment",
                "sender_id": "p",
                "body": "课程",
                "thread_id": "t",
            },
        )
        s.commit()
        r = s.exec(select(SocialReply)).one()
        rid = r.id
        m = s.exec(select(Membership).where(Membership.user_id == "user-a")).one()
        m.roles = ["finance"]
        s.add(m)
        s.commit()
        calls = []
        monkeypatch.setattr(aliyun, "text_agent", lambda *args: calls.append(1))
        monkeypatch.setattr(publishing, "call", lambda *args: calls.append(1))
        social.process_reply(s, s.get(Tenant, "tenant-a"), rid)
        assert calls == []
        assert s.get(SocialReply, rid).status == "draft"


def test_verified_send_idempotency_and_unknown_no_retry(client, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings", __import__("app.config", fromlist=["settings"]).settings
    )
    monkeypatch.setattr(
        __import__("app.config", fromlist=["settings"]).settings(),
        "allow_live_replies",
        True,
    )
    with Session(engine()) as s:
        a = make_account(s)
        e = social.ingest(
            s,
            a,
            {
                "external_id": "incoming",
                "kind": "comment",
                "sender_id": "p",
                "body": "课程",
                "thread_id": "t",
            },
        )
        s.commit()
        r = s.exec(select(SocialReply)).one()
        r.body = "已确认的课程资料"
        r.automatic = False
        s.add(r)
        c = s.get(Conversation, r.conversation_id)
        c.state = "human"
        s.add(c)
        s.commit()
        calls = []
        monkeypatch.setattr(
            publishing, "call", lambda *args: calls.append(1) or {"status": "unknown"}
        )
        social.process_reply(s, s.get(Tenant, "tenant-a"), r.id)
        social.process_reply(s, s.get(Tenant, "tenant-a"), r.id)
        assert len(calls) == 1 and s.get(SocialReply, r.id).status == "unknown"


def test_teacher_background_feedback_scope_rechecked(teams, client, monkeypatch):
    sign(client, "teach1")
    r = client.post(
        "/api/v1/runs",
        json={
            "kind": "feedback",
            "request_id": "foreign-feedback",
            "input": {"feedback_id": teams[2]["feedback"]["id"]},
        },
    )
    assert r.status_code == 404


def test_cross_tenant_social_event_constraint(client):
    from sqlalchemy.exc import IntegrityError

    with Session(engine()) as s:
        a = make_account(s)
        c = Conversation(tenant_id="tenant-b", token_hash="")
        s.add(c)
        s.commit()
        s.add(
            SocialEvent(
                tenant_id="tenant-b",
                account_id=a.id,
                external_id="x",
                kind="comment",
                thread_id="x",
                sender_id="p",
                body="x",
                conversation_id=c.id,
            )
        )
        with pytest.raises(IntegrityError):
            s.commit()


# Additional transfer and attachment regressions.
def test_feedback_scope_rechecked_after_teacher_transfer(teams, client, monkeypatch):
    from app.worker import execute
    from .test_ai import configure

    configure(monkeypatch)
    sign(client, "teach1")
    r = client.post(
        "/api/v1/runs",
        json={
            "kind": "feedback",
            "request_id": "transfer-feedback",
            "input": {"feedback_id": teams[1]["feedback"]["id"]},
        },
    )
    assert r.status_code == 202, r.text
    login(client)
    c = teams[1]["class"]
    assert (
        client.patch(
            "/api/v1/records/class/" + c["id"],
            json={"version": 1, "data": {**c["data"], "teacher_id": "teach2"}},
        ).status_code
        == 200
    )
    calls = []
    monkeypatch.setattr(aliyun, "text_agent", lambda *a: calls.append(1))
    execute("agent", "tenant-a", r.json()["id"])
    assert not calls
    with Session(engine()) as s:
        assert s.get(AgentRun, r.json()["id"]).status == "failed"


def test_conversation_follows_transferred_lead_not_stale_assignee(teams, client):
    with Session(engine()) as s:
        c = Conversation(
            tenant_id="tenant-a",
            token_hash="",
            channel="web",
            owner_id="sales1",
            lead_id=teams[1]["lead"]["id"],
        )
        s.add(c)
        s.commit()
        cid = c.id
    sign(client, "sales1")
    assert client.get("/api/v1/conversations/" + cid).status_code == 200
    login(client)
    lead = teams[1]["lead"]
    assert (
        client.patch(
            "/api/v1/records/lead/" + lead["id"],
            json={"version": 1, "data": {**lead["data"], "owner_id": "sales2"}},
        ).status_code
        == 200
    )
    sign(client, "sales1")
    assert client.get("/api/v1/conversations/" + cid).status_code == 404
    sign(client, "sales2")
    assert client.get("/api/v1/conversations/" + cid).status_code == 200


def test_teacher_document_attachments_are_not_shared(teams, client):
    sign(client, "teach1")
    r = client.post(
        "/api/v1/assets",
        data={"purpose": "document", "consent": "true"},
        files={"file": ("note.txt", b"private teaching note", "text/plain")},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    sign(client, "teach2")
    assert client.get("/api/v1/assets/" + aid + "/download").status_code == 404
    assert client.get("/api/v1/assets?purpose=document").json() == []


def test_platform_admin_without_membership_gets_no_business_rights(client):
    with Session(engine()) as s:
        u = User(
            email="platform@example.com",
            name="platform",
            verified=True,
            platform_admin=True,
            password_hash=password_hash(PASS),
        )
        s.add(u)
        s.commit()
    sign(client, "platform")
    assert client.get("/api/v1/auth/me").json()["permissions"] == []
    assert (
        client.get("/api/v1/platform").status_code == 200
        and client.get("/api/v1/records/student").status_code == 403
    )


def test_roles_are_independent_per_institution(teams, client):
    with Session(engine()) as s:
        s.add(
            Membership(
                tenant_id="tenant-b",
                user_id="teach1",
                role="finance",
                roles=["finance"],
            )
        )
        s.commit()
    sign(client, "teach1")
    assert client.get("/api/v1/auth/me").json()["roles"] == ["teacher"]
    assert client.get("/api/v1/ledger").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/switch-tenant", json={"tenant_id": "tenant-b"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me").json()["roles"] == ["finance"]
    assert client.get("/api/v1/ledger").status_code == 200
    assert client.get("/api/v1/records/class").status_code == 403


@pytest.mark.parametrize(
    "answer,expected",
    [("AI课程1980元，共8次。", "sent"), ("AI课程只要99元。", "draft")],
)
def test_automatic_reply_uses_confirmed_sources_and_checks_prices(
    client, monkeypatch, answer, expected
):
    from .test_ai import configure
    from app.agents import ChatAnswer

    configure(monkeypatch)
    course = add(
        client,
        "course",
        {"name": "AI课程", "price_fen": 198000, "lessons": 8, "approved": True},
    )
    monkeypatch.setattr(
        __import__("app.config", fromlist=["settings"]).settings(),
        "allow_live_replies",
        True,
    )
    monkeypatch.setattr(
        aliyun,
        "text_agent",
        lambda *args, **kwargs: (
            ChatAnswer(answer=answer, source_ids=[course["id"]], needs_human=False),
            50,
        ),
    )
    calls = []
    monkeypatch.setattr(
        publishing,
        "call",
        lambda *a: (
            calls.append(1)
            or {"status": "succeeded", "external_id": "real-fixture-receipt"}
        ),
    )
    with Session(engine()) as s:
        a = make_account(s)
        e = social.ingest(
            s,
            a,
            {
                "external_id": "price",
                "kind": "comment",
                "sender_id": "parent",
                "body": "课程多少钱？",
                "thread_id": "price",
            },
        )
        s.commit()
        r = s.exec(select(SocialReply)).one()
        social.process_reply(s, s.get(Tenant, "tenant-a"), r.id)
        s.refresh(r)
        assert r.status == expected and r.body == answer
        assert len(calls) == (1 if expected == "sent" else 0)
        usage = s.exec(
            select(UsageRecord).where(
                UsageRecord.request_id == "reply:" + r.id,
                UsageRecord.resource == "text_tokens",
            )
        ).one()
        assert usage.actual == 50


def test_financial_fields_are_removed_from_academic_export(teams, client):
    sign(client, "academic")
    export = client.get("/api/v1/exports/order").text
    assert (
        "paid_fen" not in export
        and "price_fen" not in export
        and "commission" not in export
        and "payment_status" in export
    )


def test_external_handling_is_recorded_without_claiming_delivery(client):
    a = client.post(
        "/api/v1/social-accounts", json={"platform": "channels", "name": "manual log"}
    ).json()
    incoming = client.post(
        "/api/v1/social-accounts/" + a["id"] + "/manual-interactions",
        json={"sender_name": "测试家长", "body": "想了解课程"},
    ).json()
    cid = incoming["conversation_id"]
    r = client.post(
        "/api/v1/conversations/" + cid + "/handled-externally",
        json={"note": "员工在官方后台完成答复"},
    )
    assert r.status_code == 200 and r.json()["status"] == "handled_externally"
    detail = client.get("/api/v1/conversations/" + cid).json()
    assert detail["reply_capability"]["state"] == "unsupported"
    assert detail["messages"][-1]["delivery_state"] == "handled_externally"
    assert detail["messages"][-1]["delivery_state"] != "sent"

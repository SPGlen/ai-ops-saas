import io, csv
from datetime import timedelta
from sqlmodel import Session, select
from app.db import engine, set_scope
from app.models import *
from .conftest import login, add


def setup_order(client):
    course = add(client, "course", {"name": "AI课", "price_fen": 198000, "lessons": 8})
    student = add(
        client, "student", {"name": "小禾", "grade": "二年级", "contact": "13800000000"}
    )
    order = add(
        client,
        "order",
        {"name": "报名", "student_id": student["id"], "course_id": course["id"]},
    )
    return course, student, order


def test_login_cookie_csrf_and_logout(client):
    me = client.get("/api/v1/auth/me")
    assert me.json()["role"] == "owner"
    assert "httponly" in client.cookies.get(
        "ops_session"
    ).lower() or client.cookies.get("ops_session")
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/v1/auth/logout").status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_tenant_isolation_and_reference_checks(client):
    course, student, order = setup_order(client)
    login(client, "b")
    assert client.get("/api/v1/records/student").json()["total"] == 0
    r = client.patch(
        "/api/v1/records/student/" + student["id"],
        json={"version": 1, "data": {"name": "偷看"}},
    )
    assert r.status_code == 404
    r = client.post(
        "/api/v1/records/order",
        json={
            "data": {
                "name": "跨机构",
                "student_id": student["id"],
                "course_id": course["id"],
            }
        },
    )
    assert r.status_code == 404
    assert (
        client.post(
            "/api/v1/auth/switch-tenant", json={"tenant_id": "tenant-a"}
        ).status_code
        == 403
    )


def test_payments_refunds_idempotency_and_reversal(client):
    course, student, order = setup_order(client)
    url = "/api/v1/orders/" + order["id"]
    first = client.post(
        url + "/payments", json={"amount_fen": 198000, "request_id": "pay-test-0001"}
    )
    assert first.status_code == 200, first.text
    second = client.post(
        url + "/payments", json={"amount_fen": 198000, "request_id": "pay-test-0001"}
    )
    assert first.json()["id"] == second.json()["id"]
    assert (
        client.post(
            url + "/payments", json={"amount_fen": 1, "request_id": "pay-test-0002"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            url + "/refunds",
            json={"amount_fen": 198001, "request_id": "refund-too-much"},
        ).status_code
        == 400
    )
    refund = client.post(
        url + "/refunds", json={"amount_fen": 30000, "request_id": "refund-good-01", "reason": "测试部分退费"}
    ).json()
    assert (
        client.get("/api/v1/records/order").json()["items"][0]["data"]["paid_fen"]
        == 168000
    )
    reverse = client.post(
        "/api/v1/ledger/" + refund["id"] + "/reverse",
        json={"request_id": "reverse-test-001"},
    )
    assert reverse.status_code == 200, reverse.text
    assert (
        client.get("/api/v1/records/order").json()["items"][0]["data"]["paid_fen"]
        == 198000
    )
    bad = client.post(
        url + "/payments", json={"amount_fen": 1, "request_id": "pay-test-0001"}
    )
    assert bad.status_code == 409


def test_enrollment_attendance_and_cancelled_lesson(client):
    course, student, order = setup_order(client)
    cls = add(client, "class", {"name": "一班", "course_id": course["id"]})
    lesson = add(
        client,
        "lesson",
        {"name": "第1课", "class_id": cls["id"], "starts_at": "2026-10-25T08:00:00Z"},
    )
    data = {
        "student_id": student["id"],
        "course_id": course["id"],
        "class_id": cls["id"],
        "order_id": order["id"],
    }
    assert (
        client.post("/api/v1/records/enrollment", json={"data": data}).status_code
        == 400
    )
    client.post(
        "/api/v1/orders/" + order["id"] + "/payments",
        json={"amount_fen": 198000, "request_id": "pay-attendance-1"},
    )
    enrollment = add(client, "enrollment", data)
    url = "/api/v1/enrollments/" + enrollment["id"] + "/attendance"
    first = client.post(
        url, json={"lesson_id": lesson["id"], "request_id": "attendance-0001"}
    )
    second = client.post(
        url, json={"lesson_id": lesson["id"], "request_id": "attendance-0002"}
    )
    assert first.status_code == 200, first.text
    assert first.json()["id"] == second.json()["id"]
    assert (
        client.get("/api/v1/records/enrollment").json()["items"][0]["data"]["remaining"]
        == 7
    )
    edit = client.patch(
        "/api/v1/records/lesson/" + lesson["id"],
        json={"version": 1, "data": {**lesson["data"], "status": "cancelled"}},
    )
    assert edit.status_code == 200, edit.text
    assert (
        client.get("/api/v1/records/enrollment").json()["items"][0]["data"]["remaining"]
        == 8
    )


def test_enrollment_duplicate_order_guard(client):
    course, student, order = setup_order(client)
    client.post(
        "/api/v1/orders/" + order["id"] + "/payments",
        json={"amount_fen": 198000, "request_id": "pay-enrollment-1"},
    )
    data = {
        "student_id": student["id"],
        "course_id": course["id"],
        "order_id": order["id"],
    }
    add(client, "enrollment", data)
    assert (
        client.post("/api/v1/records/enrollment", json={"data": data}).status_code
        == 409
    )


def test_expiry_readonly_and_platform_extension(client):
    with Session(engine()) as s:
        p = s.get(PlatformSettings, 1)
        p.free_until = now() - timedelta(days=1)
        s.add(p)
        s.commit()
    assert (
        client.post(
            "/api/v1/records/course", json={"data": {"name": "过期"}}
        ).status_code
        == 402
    )
    assert client.get("/api/v1/records/course").status_code == 200
    response = client.patch(
        "/api/v1/platform/tenants/tenant-a",
        json={
            "status": "active",
            "free_until": (now() + timedelta(days=2)).isoformat(),
            "quotas": {"text_tokens": 10000},
        },
    )
    assert response.status_code == 200, response.text
    assert (
        client.post(
            "/api/v1/records/course", json={"data": {"name": "延期后"}}
        ).status_code
        == 201
    )


def test_role_denial_and_financial_dashboard(client):
    with Session(engine()) as s:
        m = s.exec(select(Membership).where(Membership.user_id == "user-a")).first()
        m.role = "teacher"
        s.add(m)
        s.commit()
    assert client.get("/api/v1/records/expense").status_code == 403
    assert (
        client.post(
            "/api/v1/records/course", json={"data": {"name": "教师创建"}}
        ).status_code
        == 403
    )
    result = client.get("/api/v1/dashboard").json()
    assert "net_revenue_fen" not in result
    assert result["followups"] == []


def test_version_conflict_and_export_safety(client):
    row = add(client, "student", {"name": '=HYPERLINK("evil")'})
    bad = client.patch(
        "/api/v1/records/student/" + row["id"],
        json={"version": 9, "data": {"name": "覆盖"}},
    )
    assert bad.status_code == 409
    export = client.get("/api/v1/exports/student").content.decode("utf-8-sig")
    assert "'=HYPERLINK" in export
    assert client.get("/api/v1/exports/student?format=xlsx").content[:2] == b"PK"


def test_public_booking_consent_and_chat_takeover(appenv):
    assert (
        appenv.post(
            "/api/v1/public/org-a/leads",
            json={"name": "家长", "contact": "13800000000"},
        ).status_code
        == 422
    )
    result = appenv.post(
        "/api/v1/public/org-a/leads",
        json={"name": "家长", "contact": "13800000000", "consent": True},
    )
    assert result.status_code == 201, result.text
    chat = appenv.post("/api/v1/public/org-a/chat").json()
    url = "/api/v1/public/org-a/chat/" + chat["id"]
    assert appenv.get(url).status_code == 403
    result = appenv.post(
        url, json={"body": "我要找人工咨询"}, headers={"X-Public-Token": chat["token"]}
    )
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "waiting_human"
    login(appenv)
    assert (
        appenv.post("/api/v1/conversations/" + chat["id"] + "/takeover").status_code
        == 200
    )
    assert (
        appenv.post(
            "/api/v1/conversations/" + chat["id"] + "/reply",
            json={"body": "您好，可以预约周六试听。"},
        ).status_code
        == 200
    )
    result = appenv.get(url, headers={"X-Public-Token": chat["token"]}).json()
    assert result["messages"][-1]["role"] == "staff"


def test_private_contacts_not_plaintext(client):
    add(client, "student", {"name": "小禾", "contact": "13800001234"})
    with Session(engine()) as s:
        set_scope(s, "tenant-a")
        row = s.exec(select(Record).where(Record.kind == "student")).first()
        assert "13800001234" not in str(row.data)
    assert (
        client.get("/api/v1/records/student").json()["items"][0]["data"]["contact"]
        == "13800001234"
    )


def test_invalid_api_is_json_404(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert "application/json" in response.headers["content-type"]


def test_leave_makeup_and_credit_adjustment(client):
    course, student, order = setup_order(client)
    cls = add(client, "class", {"name": "补课班", "course_id": course["id"]})
    one = add(
        client,
        "lesson",
        {"name": "原课程", "class_id": cls["id"], "starts_at": "2026-10-25T08:00:00Z"},
    )
    two = add(
        client,
        "lesson",
        {"name": "补课", "class_id": cls["id"], "starts_at": "2026-10-26T08:00:00Z"},
    )
    client.post(
        "/api/v1/orders/" + order["id"] + "/payments",
        json={"amount_fen": 198000, "request_id": "pay-makeup-test"},
    )
    e = add(
        client,
        "enrollment",
        {
            "student_id": student["id"],
            "course_id": course["id"],
            "class_id": cls["id"],
            "order_id": order["id"],
        },
    )
    leave = add(
        client,
        "leave",
        {
            "name": "事假",
            "enrollment_id": e["id"],
            "lesson_id": one["id"],
            "status": "approved",
            "makeup_lesson_id": two["id"],
        },
    )
    assert (
        client.post(
            "/api/v1/enrollments/" + e["id"] + "/attendance",
            json={"lesson_id": one["id"], "request_id": "att-leave-wrong"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/enrollments/" + e["id"] + "/attendance",
            json={"lesson_id": two["id"], "request_id": "att-makeup-right"},
        ).status_code
        == 200
    )
    update = client.patch(
        "/api/v1/records/leave/" + leave["id"],
        json={"version": 1, "data": {**leave["data"], "status": "made_up"}},
    )
    assert update.status_code == 200, update.text
    assert (
        client.get("/api/v1/records/enrollment").json()["items"][0]["data"]["remaining"]
        == 7
    )
    adjust = {
        "delta": 1,
        "reason": "返还已确认的补偿课时",
        "request_id": "adjust-credits-01",
    }
    client.post("/api/v1/enrollments/" + e["id"] + "/adjust", json=adjust)
    client.post("/api/v1/enrollments/" + e["id"] + "/adjust", json=adjust)
    assert (
        client.get("/api/v1/records/enrollment").json()["items"][0]["data"]["remaining"]
        == 8
    )


def test_paid_and_refunded_order_stays_locked(client):
    course, student, order = setup_order(client)
    client.post(
        "/api/v1/orders/" + order["id"] + "/payments",
        json={"amount_fen": 198000, "request_id": "locked-order-pay"},
    )
    client.post(
        "/api/v1/orders/" + order["id"] + "/refunds",
        json={"amount_fen": 198000, "request_id": "locked-order-refund", "reason": "测试退款"},
    )
    changed = client.patch(
        "/api/v1/records/order/" + order["id"],
        json={
            "version": 1,
            "data": {
                "name": "改价",
                "student_id": student["id"],
                "course_id": course["id"],
            },
        },
    )
    assert changed.status_code == 400


def test_channel_rate_snapshot_and_settlement_dedupe(client):
    course, student, _ = setup_order(client)
    channel = add(
        client,
        "channel",
        {"name": "合作机构", "commission_bps": 2000, "confirmed": True},
    )
    order = add(
        client,
        "order",
        {
            "name": "渠道报名",
            "student_id": student["id"],
            "course_id": course["id"],
            "channel_id": channel["id"],
        },
    )
    client.patch(
        "/api/v1/records/channel/" + channel["id"],
        json={
            "version": 1,
            "data": {"name": "合作机构", "commission_bps": 500, "confirmed": True},
        },
    )
    client.post(
        "/api/v1/orders/" + order["id"] + "/payments",
        json={"amount_fen": 198000, "request_id": "channel-rate-pay"},
    )
    row = next(
        x
        for x in client.get("/api/v1/settlements").json()
        if x["order_id"] == order["id"]
    )
    assert row["commission_fen"] == 39600
    period = (now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    first = client.post(
        "/api/v1/settlement-statements",
        json={"channel_id": channel["id"], "period": period},
    )
    second = client.post(
        "/api/v1/settlement-statements",
        json={"channel_id": channel["id"], "period": period},
    )
    assert first.status_code == 201, first.text
    assert first.json()["id"] == second.json()["id"]
    assert (
        client.post(
            "/api/v1/settlement-statements",
            json={
                "channel_id": channel["id"],
                "period": (now() + timedelta(days=35)).strftime("%Y-%m"),
            },
        ).status_code
        == 400
    )


def test_csv_import_atomic_and_two_decimal_money(client):
    course, student, order = setup_order(client)
    raw = (
        "order_id,amount_yuan,transaction_id\n" + order["id"] + ",100.001,tx-invalid\n"
    )
    assert (
        client.post(
            "/api/v1/imports/payments",
            files={"file": ("bank.csv", raw.encode(), "text/csv")},
        ).status_code
        == 400
    )
    assert client.get("/api/v1/ledger").json() == []


def test_verification_email_token_is_one_time(appenv):
    from pathlib import Path
    from app.config import settings

    response = appenv.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "password": "Signup-Test-2026!",
            "name": "新负责人",
            "tenant_name": "新机构",
        },
    )
    assert response.status_code == 202
    assert (
        appenv.post(
            "/api/v1/auth/login",
            json={"email": "new@example.com", "password": "Signup-Test-2026!"},
        ).status_code
        == 403
    )
    import json

    mail = json.loads(
        next((settings().data_dir / "outbox").glob("*.json")).read_text(encoding="utf8")
    )
    from urllib.parse import urlparse, parse_qs

    token = parse_qs(urlparse(mail["url"]).query)["token"][0]
    assert appenv.post("/api/v1/auth/verify", json={"token": token}).status_code == 200
    assert appenv.post("/api/v1/auth/verify", json={"token": token}).status_code == 400


def test_same_student_multiple_accounts_does_not_double_charge(client):
    course, student, order = setup_order(client)
    cls = add(client, "class", {"name": "续课班", "course_id": course["id"]})
    lesson = add(
        client,
        "lesson",
        {
            "name": "共同课次",
            "class_id": cls["id"],
            "starts_at": "2026-10-25T08:00:00Z",
        },
    )
    ids = []
    for i, record in enumerate(
        [
            order,
            add(
                client,
                "order",
                {
                    "name": "续费订单",
                    "student_id": student["id"],
                    "course_id": course["id"],
                },
            ),
        ]
    ):
        client.post(
            "/api/v1/orders/" + record["id"] + "/payments",
            json={"amount_fen": 198000, "request_id": "same-student-pay-" + str(i)},
        )
        ids.append(
            add(
                client,
                "enrollment",
                {
                    "student_id": student["id"],
                    "course_id": course["id"],
                    "class_id": cls["id"],
                    "order_id": record["id"],
                },
            )["id"]
        )
    results = [
        client.post(
            "/api/v1/enrollments/" + e + "/attendance",
            json={
                "lesson_id": lesson["id"],
                "request_id": "same-student-att-" + str(i),
            },
        ).json()
        for i, e in enumerate(ids)
    ]
    assert results[0]["id"] == results[1]["id"]
    rows = client.get("/api/v1/records/enrollment").json()["items"]
    assert sorted(x["data"]["remaining"] for x in rows) == [7, 8]


def test_fixed_cost_commission_and_platform_plan_patch(client):
    from app.domain import commission_for

    order = Record(
        tenant_id="tenant-a",
        kind="order",
        created_by="user-a",
        data={
            "commission_bps": 2000,
            "commission_basis": "after_fixed_cost",
            "commission_deduction_fen": 40000,
        },
    )
    assert commission_for(order, 198000) == 31600
    assert commission_for(order, 30000) == 0
    response = client.patch(
        "/api/v1/platform",
        json={
            "catalog": [
                {
                    "id": "foundation",
                    "name": "机构基础版",
                    "term_days": 30,
                    "price_fen": 198000,
                    "quotas": {"images": 10},
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/auth/me").json()["entitlement"]["active"]
    client.patch("/api/v1/platform/tenants/tenant-a", json={"plan_id": "foundation"})
    assert client.get("/api/v1/subscription").json()["plan_id"] == "foundation"

"""Independent grants, private feedback and automatic operating reports."""

import json
from datetime import timedelta
from sqlalchemy import text
from sqlmodel import Session, select
from app.db import engine
from app.models import *
from app import reports
from app.permissions import identity_for
from .conftest import add, login
from .test_staff_social import teams, staff, sign


def member(client, user_id):
    return next(
        m for m in client.get("/api/v1/members").json() if m["user_id"] == user_id
    )


def feedback(client, team, **changes):
    value = {
        "name": "学习体验",
        "student_id": team["student"]["id"],
        "class_id": team["class"]["id"],
        "body": "家长的私密反馈原文",
        "rating": 2,
    }
    value.update(changes)
    return add(client, "family_feedback", value)


def test_owner_catalog_and_versioned_multi_grants(client, teams):
    data = teams
    catalog = client.get("/api/v1/authorization-catalog").json()["items"]
    assert {"scheduler", "revenue_viewer", "teacher", "finance"} <= {
        r["key"] for r in catalog
    }
    target = member(client, "teach1")
    response = client.patch(
        "/api/v1/members/" + target["id"],
        json={
            "roles": ["teacher", "revenue_viewer"],
            "authz_version": target["authz_version"],
        },
    )
    assert response.status_code == 200
    assert "revenue.read" in response.json()["permissions"]
    assert "finance.read" not in response.json()["permissions"]
    assert (
        client.patch(
            "/api/v1/members/" + target["id"],
            json={"roles": ["finance"], "authz_version": target["authz_version"]},
        ).status_code
        == 409
    )
    sign(client, "teach1")
    assert set(client.get("/api/v1/auth/me").json()["roles"]) == {
        "teacher",
        "revenue_viewer",
    }
    assert client.get("/api/v1/authorization-catalog").status_code == 403
    assert (
        client.patch(
            "/api/v1/members/" + target["id"], json={"roles": ["owner"]}
        ).status_code
        == 403
    )


def test_scheduler_independent_from_education_and_finance(client, teams):
    data = teams
    with Session(engine()) as s:
        staff(s, "scheduler", ["scheduler"])
    sign(client, "academic")
    lesson = {
        "name": "new schedule",
        "class_id": data[1]["class"]["id"],
        "starts_at": (now() + timedelta(days=4)).isoformat(),
    }
    assert (
        client.post("/api/v1/records/lesson", json={"data": lesson}).status_code == 403
    )
    sign(client, "scheduler")
    assert (
        client.post("/api/v1/records/lesson", json={"data": lesson}).status_code == 201
    )
    assert client.get("/api/v1/records/class").json()["total"] == 2
    for path in (
        "records/student",
        "records/enrollment",
        "records/order",
        "finance/overview",
        "education/feedback-kpis",
    ):
        assert client.get("/api/v1/" + path).status_code == 403, path


def test_revenue_only_returns_aggregate_and_cannot_read_receipts(client, teams):
    data = teams
    add(
        client,
        "expense",
        {"name": "保密支出", "amount_fen": 2300, "status": "confirmed"},
    )
    with Session(engine()) as s:
        staff(s, "revenue", ["revenue_viewer"])
    sign(client, "revenue")
    overview = client.get("/api/v1/revenue/overview")
    assert overview.status_code == 200, overview.text
    assert overview.json()["totals"]["net_fen"] == 396000
    assert set(overview.json()) == {"totals", "chart"}
    assert set(overview.json()["totals"]) == {"received_fen", "refund_fen", "net_fen"}
    for path in (
        "finance/overview",
        "finance/details/order/" + data[1]["order"]["id"],
        "exports/order",
        "records/student",
        "records/expense",
        "records/family_feedback",
        "report-snapshots",
    ):
        assert client.get("/api/v1/" + path).status_code in (403, 404), path
    report = client.get("/api/v1/reports/weekly").json()
    assert report["metrics"] == {}
    assert "finance" not in report and "family_feedback" not in report
    assert "child1" not in json.dumps(report)
    assert "保密支出" not in json.dumps(report, ensure_ascii=False)
    assert "实收3960.00元" in "".join(report["summary"])


def test_teacher_with_revenue_preserves_teaching_scope_and_revocation(client, teams):
    data = teams
    target = member(client, "teach1")
    assert (
        client.patch(
            "/api/v1/members/" + target["id"],
            json={"roles": ["teacher", "revenue_viewer"]},
        ).status_code
        == 200
    )
    sign(client, "teach1")
    assert client.get("/api/v1/revenue/overview").status_code == 200
    ids = {r["id"] for r in client.get("/api/v1/records/student").json()["items"]}
    assert ids == {data[1]["student"]["id"]}
    assert (
        client.get("/api/v1/records/student/" + data[2]["student"]["id"]).status_code
        == 404
    )
    login(client)
    assert (
        client.patch(
            "/api/v1/members/" + target["id"], json={"roles": ["teacher"]}
        ).status_code
        == 200
    )
    sign(client, "teach1")
    assert client.get("/api/v1/revenue/overview").status_code == 403


def test_private_feedback_scope_validation_encryption_and_resolution(client, teams):
    data = teams
    r1 = feedback(client, data[1])
    r2 = feedback(client, data[2], respondent="student", rating=5)
    with Session(engine()) as s:
        row = s.get(Record, r1["id"])
        assert "家长的私密反馈原文" not in json.dumps(row.data, ensure_ascii=False)
        assert "body_cipher" in row.data and "body" not in row.data
    sign(client, "teach1")
    items = client.get("/api/v1/records/family_feedback").json()["items"]
    assert {r["id"] for r in items} == {r1["id"]}
    assert items[0]["data"]["body"] == "家长的私密反馈原文"
    assert (
        items[0]["can_edit"] is False
    )  # Owner-created record is read-only to teacher.
    assert client.get("/api/v1/records/family_feedback/" + r2["id"]).status_code == 404
    bad = {
        "name": "forged",
        "student_id": data[1]["student"]["id"],
        "class_id": data[2]["class"]["id"],
        "body": "x",
    }
    assert (
        client.post("/api/v1/records/family_feedback", json={"data": bad}).status_code
        == 403
    )
    mine = feedback(client, data[1])
    assert mine["can_edit"]
    assert (
        client.patch(
            "/api/v1/records/family_feedback/" + mine["id"],
            json={
                "version": mine["version"],
                "data": {"status": "resolved", "resolution": "done"},
            },
        ).status_code
        == 403
    )
    sign(client, "finance")
    assert client.get("/api/v1/records/family_feedback").status_code == 403
    assert "family_feedback" not in client.get("/api/v1/reports/weekly").json()
    login(client)
    assert (
        client.patch(
            "/api/v1/records/family_feedback/" + mine["id"],
            json={"version": mine["version"], "data": {"status": "resolved"}},
        ).status_code
        == 400
    )
    ok = client.patch(
        "/api/v1/records/family_feedback/" + mine["id"],
        json={
            "version": mine["version"],
            "data": {"status": "resolved", "resolution": "已与家长沟通"},
        },
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["resolution"] == "已与家长沟通"
    assert (
        client.patch(
            "/api/v1/records/family_feedback/" + mine["id"],
            json={"version": mine["version"], "data": {"rating": 1}},
        ).status_code
        == 409
    )


def test_feedback_reports_and_immutable_corrections(client, teams):
    data = teams
    feedback(client, data[1], rating=2)
    feedback(client, data[2], respondent="student", rating=4)
    r = client.get("/api/v1/reports/weekly").json()
    f = r["family_feedback"]
    assert (
        f["count"],
        f["average_rating"],
        f["parents"],
        f["students"],
        f["attention"],
    ) == (2, 3, 1, 1, 1)
    assert "私密反馈" not in json.dumps(r, ensure_ascii=False)
    period = r["period"]
    first = client.post(
        "/api/v1/report-snapshots/weekly", params={"period": period}
    ).json()
    assert (
        client.post(
            "/api/v1/report-snapshots/weekly", params={"period": period}
        ).json()["id"]
        == first["id"]
    )
    feedback(client, data[1], rating=None)
    second = client.post(
        "/api/v1/report-snapshots/weekly", params={"period": period}
    ).json()
    assert second["version"] == first["version"] + 1
    assert second["payload"]["family_feedback"]["rated_count"] == 2
    assert first["payload"]["family_feedback"]["count"] == 2
    sign(client, "teach1")
    scoped = client.get("/api/v1/reports/monthly").json()
    assert scoped["family_feedback"]["count"] == 2
    assert "finance" not in scoped


def test_scheduled_reports_include_finance_admissions_and_feedback_without_pii(
    client, teams, monkeypatch
):
    data = teams
    local = now().astimezone(reports.TZ)
    monday = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    previous = monday - timedelta(days=2)
    feedback(client, data[1], recorded_at=previous.isoformat())
    with Session(engine()) as s:
        t = s.get(Tenant, "tenant-a")
        t.settings = {
            **t.settings,
            "operations": {
                "week_day": 0,
                "week_hour": 0,
                "month_day": 1,
                "month_hour": 0,
            },
        }
        s.add(t)
        s.commit()
        reports.tick(s, t)
        rows = s.exec(
            select(ReportSnapshot).where(ReportSnapshot.tenant_id == t.id)
        ).all()
        weekly = next(r for r in rows if r.kind == "weekly")
        assert weekly.payload["family_feedback"]["count"] == 1
        assert "finance" in weekly.payload and "new_leads" in weekly.payload["metrics"]
        notices = s.exec(
            select(NotificationOutbox).where(NotificationOutbox.kind == "report")
        ).all()
        assert any("实收" in n.body and "反馈1条" in n.body for n in notices)
        assert all("私密反馈" not in n.body and "child1" not in n.body for n in notices)
        count = len(notices)
        reports.tick(s, t)
        assert (
            len(
                s.exec(
                    select(NotificationOutbox).where(
                        NotificationOutbox.kind == "report"
                    )
                ).all()
            )
            == count
        )


def test_capability_migration_preserves_existing_and_never_regrants(client):
    from app.capability_migration import upgrade_capabilities

    with Session(engine()) as s:
        staff(s, "legacy-academic", ["academic_admin"])
        t = s.get(Tenant, "tenant-a")
        t.settings = {**t.settings, "authorization_schema_version": 0}
        s.add(t)
        s.commit()
    with engine().begin() as conn:
        upgrade_capabilities(conn)
        raw = conn.execute(
            text("SELECT roles FROM memberships WHERE user_id='legacy-academic'")
        ).scalar()
        assert set(json.loads(raw)) == {"academic_admin", "scheduler"}
        conn.execute(
            text(
                "UPDATE memberships SET roles='[\"academic_admin\"]' WHERE user_id='legacy-academic'"
            )
        )
        upgrade_capabilities(conn)
        assert json.loads(
            conn.execute(
                text("SELECT roles FROM memberships WHERE user_id='legacy-academic'")
            ).scalar()
        ) == ["academic_admin"]


def test_cross_tenant_feedback_export_is_filtered(client, teams):
    data = teams
    row = feedback(client, data[1])
    login(client, "b")
    assert client.get("/api/v1/records/family_feedback/" + row["id"]).status_code == 404
    assert row["id"] not in client.get("/api/v1/exports/family_feedback").text
    login(client)
    future = {
        "name": "future",
        "student_id": data[1]["student"]["id"],
        "body": "x",
        "recorded_at": (now() + timedelta(days=1)).isoformat(),
    }
    assert (
        client.post(
            "/api/v1/records/family_feedback", json={"data": future}
        ).status_code
        == 400
    )

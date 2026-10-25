"""Idempotent SQLite development migration; production uses frozen Alembic 0003."""

import json
from sqlalchemy import text


def upgrade_03(conn):
    rows = conn.execute(
        text(
            "SELECT id,kind,data FROM records WHERE kind IN ('order','enrollment','class','lesson')"
        )
    ).all()
    allrows = {
        rid: (kind, json.loads(data) if isinstance(data, str) else dict(data))
        for rid, kind, data in rows
    }
    courses = {
        rid: json.loads(data) if isinstance(data, str) else data
        for rid, data in conn.execute(
            text("SELECT id,data FROM records WHERE kind='course'")
        ).all()
    }
    for rid, (kind, old) in allrows.items():
        data = dict(old)
        course = courses.get(data.get("course_id"), {})
        if kind == "order":
            data.setdefault(
                "program_name", course.get("name", data.get("name", "历史报名"))
            )
            data.setdefault(
                "purchased_units", data.get("course_lessons", course.get("lessons", 0))
            )
            data.setdefault("price_fen", course.get("price_fen", 0))
            data.setdefault("course_lessons", data["purchased_units"])
        if kind == "enrollment":
            order = allrows.get(data.get("order_id"), ("", {}))[1]
            data.setdefault(
                "program_name",
                order.get(
                    "program_name",
                    courses.get(data.get("course_id"), {}).get("name", "历史报名"),
                ),
            )
            data.setdefault("status", "active")
            data.setdefault("history_calibrated", False)
        if kind == "lesson":
            data.setdefault("kpi_eligible", False)
        if data != old:
            conn.execute(
                text("UPDATE records SET data=:data WHERE id=:id"),
                {"id": rid, "data": json.dumps(data, ensure_ascii=False)},
            )
    for tid, raw in conn.execute(text("SELECT id,settings FROM tenants")).all():
        cfg = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if cfg.get("ops_schema_version", 0) < 3:
            cfg.update(ops_schema_version=3, consultation_enabled=False)
            conn.execute(
                text("UPDATE tenants SET settings=:cfg WHERE id=:id"),
                {"id": tid, "cfg": json.dumps(cfg, ensure_ascii=False)},
            )

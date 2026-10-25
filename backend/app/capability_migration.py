"""Preserve prior scheduling access once; new grants stay independent."""

import json
from sqlalchemy import text


def upgrade_capabilities(conn):
    for tid, raw in conn.execute(text("SELECT id,settings FROM tenants")).all():
        cfg = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if cfg.get("authorization_schema_version", 0) >= 1:
            continue
        for mid, raw_roles, legacy in conn.execute(
            text("SELECT id,roles,role FROM memberships WHERE tenant_id=:t"), {"t": tid}
        ).all():
            roles = json.loads(raw_roles) if isinstance(raw_roles, str) else raw_roles
            roles = (
                roles
                if roles is not None
                else (
                    ["admissions", "content_ops", "academic_admin"]
                    if legacy == "operator"
                    else [legacy]
                )
            )
            if "academic_admin" in roles and "scheduler" not in roles:
                conn.execute(
                    text(
                        "UPDATE memberships SET roles=:r,authz_version=authz_version+1 WHERE id=:id"
                    ),
                    {"r": json.dumps([*roles, "scheduler"]), "id": mid},
                )
        cfg["authorization_schema_version"] = 1
        conn.execute(
            text("UPDATE tenants SET settings=:s WHERE id=:id"),
            {"s": json.dumps(cfg, ensure_ascii=False), "id": tid},
        )

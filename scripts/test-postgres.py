"""Native PG integration gate. Only an EMPTY, separately named *_test database is accepted."""

import os, secrets, json, tempfile
from pathlib import Path
from datetime import timedelta
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url, URL

root = Path(__file__).resolve().parents[1]
admin_url = os.environ.get("OPS_TEST_POSTGRES_URL", "")
url = make_url(admin_url)
if not url.database or not url.database.endswith("_test"):
    raise SystemExit("OPS_TEST_POSTGRES_URL must name a disposable *_test database")
password = secrets.token_hex(24)
role = "ops_ci_" + secrets.token_hex(5)
conn = psycopg.connect(admin_url)
with conn:
    if conn.execute(
        "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
    ).fetchone()[0]:
        raise SystemExit(
            "Native PG test requires an empty database; existing data preserved"
        )
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute(
        sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)
        )
    )
    # Test the complete frozen Alembic chain, using the disposable runtime role.
    migration_sql = (root / "docs/migration-upgrade-0006.sql").read_text(
        encoding="utf-8-sig"
    )
    migration_sql = migration_sql.replace(" TO ops_app", " TO " + role)
    conn.execute(migration_sql)
    conn.execute(
        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
    )
    conn.execute(
        sql.SQL(
            "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO {}"
        ).format(sql.Identifier(role))
    )
runtime = URL.create(
    "postgresql+psycopg",
    username=role,
    password=password,
    host=url.host,
    port=url.port,
    database=url.database,
).render_as_string(hide_password=False)
with tempfile.TemporaryDirectory(prefix="ops-native-test-") as temp:
    os.environ.update(
        OPS_DATABASE_URL=runtime,
        OPS_SECRET_KEY=secrets.token_hex(32),
        OPS_TASK_MODE="test",
        OPS_ENVIRONMENT="development",
        OPS_DATA_DIR=temp,
        OPS_ALIYUN_API_KEY="",
        OPS_SMTP_HOST="",
        OPS_S3_BUCKET="",
    )
    from app.config import settings
    from app.db import engine, set_scope, check_runtime_role, TENANT_TABLES
    from app.models import *
    from app.security import password_hash
    from sqlmodel import Session, select
    from sqlalchemy import text
    from app.main import app
    from fastapi.testclient import TestClient

    check_runtime_role()
    with Session(engine()) as s:
        s.add(PlatformSettings(free_until=now() + timedelta(days=1)))
        for suffix in ("a", "b"):
            user = User(
                id="native-user-" + suffix,
                email="native-" + suffix + "@example.com",
                name="Native " + suffix,
                verified=True,
                password_hash=password_hash("Native-Only-Test-2026!"),
            )
            tenant = Tenant(
                id="native-" + suffix,
                slug="native-" + suffix,
                name="Native " + suffix,
                settings={"legacy_maintenance": True, "ops_schema_version": 3},
            )
            s.add(user)
            s.add(tenant)
            s.flush()
            s.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))
        s.commit()
    checks = 0
    with TestClient(app) as client:

        def login(suffix):
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": "native-" + suffix + "@example.com",
                    "password": "Native-Only-Test-2026!",
                },
            )
            assert response.status_code == 200, response.text
            client.headers["X-CSRF-Token"] = client.cookies.get("ops_csrf")

        login("a")
        checks += 1
        created = client.post(
            "/api/v1/records/student",
            json={"data": {"name": "Native Student", "contact": "synthetic-contact"}},
        )
        assert created.status_code == 201, created.text
        checks += 1
        student = created.json()
        login("b")
        assert client.get("/api/v1/records/student").json()["total"] == 0
        checks += 1
        assert (
            client.patch(
                "/api/v1/records/student/" + student["id"],
                json={"version": 1, "data": {"name": "cross-tenant"}},
            ).status_code
            == 404
        )
        checks += 1
    with Session(engine()) as s:
        for table in TENANT_TABLES:
            assert s.exec(text("SELECT count(*) FROM " + table)).one()[0] == 0
            checks += 1
        set_scope(s, "native-a")
        assert s.exec(select(Record)).one().id == student["id"]
        checks += 1
        s.commit()
        assert s.exec(select(Record)).one().id == student["id"]
        checks += 1
        s.rollback()
        set_scope(s, "native-b")
        assert s.exec(select(Record)).all() == []
        checks += 1
    report = {
        "status": "passed",
        "engine": "native PostgreSQL + psycopg",
        "checks": checks,
        "runtime_role": "NOSUPERUSER NOBYPASSRLS non-owner",
        "tenant_tables": len(TENANT_TABLES),
    }
    (root / "docs/native-postgres-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report))

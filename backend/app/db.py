from functools import lru_cache
from pathlib import Path
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, Session, create_engine
from .config import settings
from . import models

TENANT_TABLES = [
    "media_profiles", "account_groups", "account_group_members", "automation_plans", "automation_plan_versions", "automation_runs", "automation_account_tasks", "automation_steps", "matrix_charges",
    "business_events",
    "feedback_kpis",
    "lesson_rosters",
    "admission_imports",
    "studio_definitions",
    "studio_versions",
    "form_submissions",
    "flow_instances",
    "flow_tasks",
    "report_snapshots",
    "ops_alerts",
    "notification_outbox",
    "receipt_links",
    "addon_requests",
    "member_invitations",
    "social_events",
    "social_replies",
    "records",
    "audit_events",
    "ledger_entries",
    "credit_entries",
    "integrations",
    "assets",
    "contents",
    "content_versions",
    "predictions",
    "agent_runs",
    "media_jobs",
    "social_accounts",
    "publish_jobs",
    "metric_snapshots",
    "usage_records",
    "budget_buckets",
    "conversations",
    "messages",
    "knowledge_chunks",
    "webhook_receipts",
    "rubric_candidates",
    "settlements",
]
IMMUTABLE_TABLES = [
    "automation_plan_versions",
    "business_events",
    "studio_versions",
    "report_snapshots",
    "lesson_rosters",
    "predictions",
    "content_versions",
    "ledger_entries",
    "credit_entries",
    "audit_events",
    "settlements",
]


@event.listens_for(Engine, "connect")
def sqlite_foreign_keys(dbapi_connection, connection_record):
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.execute("PRAGMA journal_mode=WAL")


@lru_cache
def engine():
    url = settings().database_url
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        url,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
        pool_pre_ping=True,
    )


def set_scope(session: Session, tenant_id: str = "", user_id: str = ""):
    session.info["tenant_id"] = tenant_id
    session.info["user_id"] = user_id
    if session.bind.dialect.name == "postgresql":
        session.execute(
            text(
                "SELECT set_config('ops.tenant_id', :t, true), set_config('ops.user_id', :u, true)"
            ),
            {"t": tenant_id, "u": user_id},
        )


@event.listens_for(Session, "after_begin")
def apply_scope(session, transaction, connection):
    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                "SELECT set_config('ops.tenant_id', :t, true), set_config('ops.user_id', :u, true)"
            ),
            {
                "t": session.info.get("tenant_id", ""),
                "u": session.info.get("user_id", ""),
            },
        )


def session_dep():
    with Session(engine(), expire_on_commit=False) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


def initialize():
    db = engine()
    if db.dialect.name == "postgresql":
        raise RuntimeError("Use alembic with migration credentials for PostgreSQL")
    SQLModel.metadata.create_all(db)
    with db.begin() as conn:
        from sqlalchemy import inspect

        additions = {
            "usage_records": [("model_usage", "JSON NOT NULL DEFAULT '{}'")],
            "rubric_candidates": [("profile_id", "VARCHAR")],
            "social_accounts": [("profile_id", "VARCHAR"), ("identity_key", "VARCHAR"), ("paused", "BOOLEAN NOT NULL DEFAULT 0")],
            "social_replies": [("draft_only", "BOOLEAN NOT NULL DEFAULT 0")],
            "assets": [("uploaded_by", "VARCHAR NOT NULL DEFAULT ''")],
            "memberships": [
                ("roles", "JSON"),
                ("status", "VARCHAR NOT NULL DEFAULT 'active'"),
                ("authz_version", "INTEGER NOT NULL DEFAULT 1"),
            ],
            "conversations": [
                (name, "VARCHAR NOT NULL DEFAULT ''")
                for name in (
                    "owner_id",
                    "account_id",
                    "external_thread_id",
                    "source_work_id",
                )
            ]
            + [("interaction_kind", "VARCHAR NOT NULL DEFAULT 'private_message'")],
        }
        for table, columns in additions.items():
            present = {c["name"] for c in inspect(conn).get_columns(table)}
            for name, ddl in columns:
                if name not in present:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
        conn.execute(
            text(
                "UPDATE memberships SET roles = CASE WHEN role='operator' THEN '[\"admissions\",\"content_ops\",\"academic_admin\"]' ELSE '[\"' || role || '\"]' END WHERE roles IS NULL"
            )
        )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_business_workflow ON studio_definitions (tenant_id, binding) WHERE kind='workflow' AND enabled=1"
            )
        )
        from .legacy_03 import upgrade_03

        upgrade_03(conn)
        from .capability_migration import upgrade_capabilities

        upgrade_capabilities(conn)
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_social_identity ON social_accounts (tenant_id, identity_key)"))
        from .matrix_migration import upgrade_matrix
        upgrade_matrix(conn)
        for table in IMMUTABLE_TABLES:
            for verb in ("UPDATE", "DELETE"):
                conn.execute(
                    text(
                        f'CREATE TRIGGER IF NOT EXISTS immutable_{table}_{verb.lower()} BEFORE {verb} ON {table} BEGIN SELECT RAISE(ABORT, "immutable record"); END'
                    )
                )


def rls_statements():
    statements = []
    for table in TENANT_TABLES:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY tenant_isolation ON {table} USING (tenant_id = current_setting('ops.tenant_id', true)) WITH CHECK (tenant_id = current_setting('ops.tenant_id', true))",
        ]
    return statements


def check_runtime_role():
    if engine().dialect.name == "postgresql":
        with engine().connect() as conn:
            row = conn.execute(
                text(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                )
            ).one()
            owns = conn.execute(
                text(
                    "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tableowner=current_user"
                )
            ).scalar()
            if row[0] or row[1] or owns:
                raise RuntimeError(
                    "Runtime database role must be non-owner, NOSUPERUSER, NOBYPASSRLS"
                )
            missing = conn.execute(
                text(
                    "SELECT count(*) FROM pg_class WHERE relname = ANY(:names) AND (NOT relrowsecurity OR NOT relforcerowsecurity)"
                ),
                {"names": TENANT_TABLES},
            ).scalar()
            count = conn.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname=ANY(:names) AND EXISTS(SELECT 1 FROM pg_policy p WHERE p.polrelid=c.oid AND p.polname='tenant_isolation')"
                ),
                {"names": TENANT_TABLES},
            ).scalar()
            if missing or count != len(TENANT_TABLES):
                raise RuntimeError(
                    "Tenant tables require ENABLE/FORCE ROW LEVEL SECURITY"
                )

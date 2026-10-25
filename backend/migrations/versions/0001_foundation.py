"""SaaS foundation: frozen DDL, tenant RLS and append-only journals."""

import json
from pathlib import Path
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    statements = json.loads(
        (Path(__file__).resolve().parents[1] / "0001-ddl.json").read_text(
            encoding="utf8"
        )
    )
    for statement in statements:
        op.execute(statement)
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ops_app"
    )
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO ops_app")
    op.execute("REVOKE ALL ON alembic_version FROM ops_app")


def downgrade():
    raise RuntimeError(
        "Use a reviewed forward migration or restore a verified backup; destructive downgrade is disabled"
    )

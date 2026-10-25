"""Add staff authorization, invitations and social interactions without rewriting history."""

import json
from pathlib import Path
import sqlalchemy as sa
from alembic import op

revision = "0002_staff_social"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("memberships", sa.Column("roles", sa.JSON(), nullable=True))
    op.add_column(
        "memberships",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column(
        "memberships",
        sa.Column("authz_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute(
        'UPDATE memberships SET roles=CASE WHEN role=\'operator\' THEN \'["admissions","content_ops","academic_admin"]\'::json ELSE json_build_array(role) END WHERE roles IS NULL'
    )
    op.add_column(
        "assets",
        sa.Column("uploaded_by", sa.String(), nullable=False, server_default=""),
    )
    for name in ("owner_id", "account_id", "external_thread_id", "source_work_id"):
        op.add_column(
            "conversations",
            sa.Column(name, sa.String(), nullable=False, server_default=""),
        )
    op.add_column(
        "conversations",
        sa.Column(
            "interaction_kind",
            sa.String(),
            nullable=False,
            server_default="private_message",
        ),
    )
    for stmt in json.loads(
        (Path(__file__).resolve().parents[1] / "0002-ddl.json").read_text(
            encoding="utf-8"
        )
    ):
        op.execute(stmt)


def downgrade():
    raise RuntimeError(
        "Restore a verified backup with its matching application image; historical journals must not be rewritten"
    )

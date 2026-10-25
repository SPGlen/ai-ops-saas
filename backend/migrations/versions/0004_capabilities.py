"""Independent scheduling and revenue grants; keep existing staff access."""

from alembic import op

revision = "0004_capabilities"
down_revision = "0003_operations"
branch_labels = None
depends_on = None


def upgrade():
    # Frozen PostgreSQL-only migration, also emitted in offline release SQL.
    op.execute("""UPDATE memberships m SET roles = (m.roles::jsonb || '["scheduler"]'::jsonb)::json,
                  authz_version = m.authz_version + 1 FROM tenants t
                  WHERE t.id=m.tenant_id
                  AND COALESCE((t.settings->>'authorization_schema_version')::int,0) < 1
                  AND m.roles::jsonb ? 'academic_admin' AND NOT (m.roles::jsonb ? 'scheduler')""")
    op.execute("""UPDATE tenants SET settings = (settings::jsonb || jsonb_build_object('authorization_schema_version', 1))::json
                  WHERE COALESCE((settings->>'authorization_schema_version')::int,0) < 1""")


def downgrade():
    raise RuntimeError(
        "Restore matching code after reviewing independent grants; do not drop business data"
    )

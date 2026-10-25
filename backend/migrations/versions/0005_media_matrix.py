"""Versioned media automation, explicit account targets and isolated matrix budgets."""
import json
from pathlib import Path
from alembic import op
revision = '0005_media_matrix'
down_revision = '0004_capabilities'
branch_labels = None
depends_on = None


def upgrade():
    for stmt in json.loads((Path(__file__).resolve().parents[1]/'0005-ddl.json').read_text(encoding='utf8')):
        op.execute(stmt)


def downgrade():
    raise RuntimeError('Restore a verified backup with its matching application version; retain published content and charge history')

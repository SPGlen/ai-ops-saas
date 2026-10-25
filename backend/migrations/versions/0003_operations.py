"""Operations 0.3: historical snapshots, versioned studio, reports and notifications."""
import json
from pathlib import Path
from alembic import op
revision='0003_operations'
down_revision='0002_staff_social'
branch_labels=None
depends_on=None

def upgrade():
    for stmt in json.loads((Path(__file__).resolve().parents[1]/'0003-ddl.json').read_text(encoding='utf-8')):
        op.execute(stmt)

def downgrade():
    raise RuntimeError('Restore a verified backup with its matching application image; preserve journals and snapshots')

"""Text provider routing and usage breakdown. Existing rows retain empty metadata."""
from alembic import op
import sqlalchemy as sa
revision = '0006_deepseek'
down_revision = '0005_media_matrix'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('usage_records', sa.Column('model_usage', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade():
    raise RuntimeError('Restore the verified backup and its matching application; keep model usage history')

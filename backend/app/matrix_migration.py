"""One-time, non-destructive retirement of platform-only campaign scheduling."""
import json
from sqlalchemy import select, update
from .models import Tenant, Record, MediaProfile, AutomationPlan, AutomationPlanVersion
from .matrix_schemas import PlanSpec


def upgrade_matrix(conn):
    from .models import uid, now
    for row in conn.execute(select(Tenant.__table__)).mappings().all():
        settings = dict(row['settings'] or {})
        if settings.get('matrix_schema_version', 0) >= 1:
            continue
        camps = conn.execute(select(Record.__table__).where(Record.tenant_id == row['id'], Record.kind == 'campaign')).mappings().all()
        if camps:
            profile_id = uid()
            conn.execute(MediaProfile.__table__.insert().values(id=profile_id, tenant_id=row['id'], created_at=now(), name=row['name']+' · 待配置品牌', audience='请配置品牌受众', style='', knowledge_ids=[], asset_ids=[], rubrics={}, version=1, updated_at=now()))
            for c in camps:
                data = dict(c['data'])
                data['enabled'] = False
                data['matrix_migration'] = '待确认品牌、明确账号、预算及试运行'
                conn.execute(update(Record.__table__).where(Record.id == c['id']).values(data=data))
                pid = uid()
                spec = PlanSpec(direction=data.get('objective') or data.get('name') or '待配置内容方向').model_dump()
                conn.execute(AutomationPlan.__table__.insert().values(id=pid, tenant_id=row['id'], created_at=now(), profile_id=profile_id, name=data.get('name', '历史计划')+'（待确认）', spec=spec, version=1, enabled=False, actor_id=c['created_by'], authorized_by='', last_error='旧计划已停用，需补齐配置', updated_at=now()))
                conn.execute(AutomationPlanVersion.__table__.insert().values(id=uid(), tenant_id=row['id'], created_at=now(), plan_id=pid, version=1, snapshot={'legacy_record_id': c['id'], 'spec': spec}))
        settings['matrix_schema_version'] = 1
        conn.execute(update(Tenant.__table__).where(Tenant.id == row['id']).values(settings=settings))

"""Durable fixed pipeline; each side effect has a stable per-account request id."""
import json, hashlib, base64
from datetime import timedelta, datetime
from collections import Counter
from fastapi import HTTPException
from sqlalchemy import update, or_
from sqlmodel import Session, select
from .models import *
from .db import engine, set_scope
from .domain import own, query, save_content, policy_notes, audit
from .schemas import ContentInput
from .config import settings
from .security import fail, redact_error
from .permissions import identity_for, permit
from . import matrix as m

DONE = {'trial_ready', 'succeeded', 'cancelled'}


def dispatch_run(tid, rid):
    from .worker import celery, pool
    if settings().task_mode == 'celery':
        celery.send_task('ops.matrix', args=[tid, rid], queue='ops')
    elif settings().task_mode == 'local':
        pool.submit(execute_run, tid, rid)


def step(s, task, key):
    obj = s.exec(query(s, AutomationStep, task.tenant_id).where(AutomationStep.task_id == task.id, AutomationStep.key == key)).first()
    if not obj:
        obj = AutomationStep(tenant_id=task.tenant_id, task_id=task.id, key=key)
        s.add(obj)
        s.flush()
    return obj


def ensure_agent(s, task, run, key, kind, data, shared=False):
    from .worker import dispatch
    st = step(s, task, key)
    req = 'mx:' + (run.id if shared else task.id) + ':' + key
    job = own(s, AgentRun, task.tenant_id, st.object_id) if st.object_id else s.exec(query(s, AgentRun, task.tenant_id).where(AgentRun.request_id == req)).first()
    if not job:
        m.charge(s, task.tenant_id, task, req, 'text_tokens', 20000, run.snapshot['spec']['funding'], shared=shared, purpose='vision' if kind == 'predict' else 'text')
        job = AgentRun(tenant_id=task.tenant_id, kind=kind, request_id=req, actor_id=run.actor_id, funding=run.snapshot['spec']['funding'], input={**data, '_matrix_task_id': task.id})
        s.add(job)
        s.flush()
    st.object_id, st.status = job.id, job.status
    s.add(st)
    s.commit()
    if job.status in ('queued', 'retrying', 'processing', 'submitting'):
        if job.status == 'queued':
            dispatch('agent', task.tenant_id, job.id)
        return None
    if job.status == 'succeeded':
        st.status, st.detail = 'succeeded', job.output
        s.add(st)
        return job.output
    fail(job.error_code or 'MODEL_TASK_WAITING', job.error or '模型任务等待处理', 409)


def ensure_media(s, task, run, key, kind, prompt, parameters, resource, units):
    from .worker import dispatch
    st = step(s, task, key)
    req = 'mx:' + task.id + ':' + key
    job = own(s, MediaJob, task.tenant_id, st.object_id) if st.object_id else s.exec(query(s, MediaJob, task.tenant_id).where(MediaJob.request_id == req)).first()
    if not job:
        m.charge(s, task.tenant_id, task, req, resource, units, run.snapshot['spec']['funding'])
        job = MediaJob(tenant_id=task.tenant_id, kind=kind, prompt=prompt, request_id=req, actor_id=run.actor_id, funding=run.snapshot['spec']['funding'], parameters={**parameters, '_matrix_task_id': task.id})
        s.add(job)
        s.flush()
    st.object_id, st.status = job.id, job.status
    s.add(st)
    s.commit()
    if job.status in ('queued', 'polling', 'finishing'):
        dispatch('media', task.tenant_id, job.id)
        return None
    if job.status in ('processing', 'submitting', 'retrying'):
        return None
    if job.status == 'succeeded':
        st.status, st.detail = 'succeeded', {'asset_ids': job.asset_ids, 'provider_task_id': job.provider_task_id}
        s.add(st)
        return job.asset_ids
    fail(job.error_code or 'MEDIA_TASK_WAITING', job.error or '媒体任务等待处理', 409)


def enqueue_publish(s, task, run, account, actor=None):
    m.guard(s, task.tenant_id, task.id, publishing=True)
    if task.publish_job_id:
        return own(s, PublishJob, task.tenant_id, task.publish_job_id)
    version = own(s, ContentVersion, task.tenant_id, task.version_id)
    if policy_notes(s, task.tenant_id, version.title, version.body, version.assets) or not version.policy_checked:
        fail('CONTENT_REVIEW_REQUIRED', '成品存在待处理检查项')
    prediction = s.exec(query(s, Prediction, task.tenant_id).where(Prediction.version_id == version.id)).first()
    if not prediction or prediction.payload.get('credibility', 0) < 3:
        fail('CONTENT_REVIEW_REQUIRED', '盲评可信度不足，请核对成品')
    req = 'mx:' + task.id + ':publish'
    job = PublishJob(tenant_id=task.tenant_id, account_id=account.id, version_id=task.version_id, actor_id=run.actor_id, request_id=req, scheduled_at=max(as_utc(run.slot), now()))
    s.add(job)
    s.flush()
    task.publish_job_id, task.status, task.stage = job.id, 'running', 'publish'
    s.add(task)
    audit(s, task.tenant_id, actor or run.actor_id, 'matrix.publish.approved', task.id, publish_job_id=job.id)
    return job


def advance(s, task, run):
    tid = task.tenant_id
    if task.status in DONE:
        return
    _, run, account = m.guard(s, tid, task.id)
    selected = next(a for a in run.snapshot['accounts'] if a['id'] == account.id)
    task.status = 'running'
    if 'booking_url' not in task.data:
        tenant = s.get(Tenant, tid)
        task.data = {**task.data, 'attribution_source': 'matrix:'+task.id, 'booking_url': settings().public_url.rstrip('/')+'/book/'+tenant.slug+'?source=matrix%3A'+task.id}
    if task.stage == 'sources':
        pack = next((st.detail for st in s.exec(query(s, AutomationStep, tid).where(AutomationStep.key == 'sources', AutomationStep.status == 'succeeded')).all() if st.detail.get('run_id') == run.id), None)
        if not pack:
            from .matrix_sources import collect
            pack = {**collect(s, run), 'run_id': run.id}
        st = step(s, task, 'sources')
        st.status, st.detail = 'succeeded', pack
        s.add(st)
        task.data = {**task.data, 'sources': pack}
        task.stage = 'creation'
    elif task.stage == 'creation':
        shared = run.snapshot['spec']['mode'] == 'matrix'
        topic = ensure_agent(s, task, run, 'topic', 'matrix_topic', {'profile': {k: run.snapshot['profile'][k] for k in ('name','audience','style')}, 'direction': run.snapshot['spec']['direction'], 'sources': {**task.data['sources'], 'items': task.data['sources']['items'][:10], 'notes': task.data['sources']['notes'][:10]}, 'positioning': '' if shared else selected['positioning']}, shared=shared)
        if topic is None:
            return
        data = ensure_agent(s, task, run, 'director', 'matrix_content', {'profile': run.snapshot['profile'], 'facts': run.snapshot['facts'], 'account': selected, 'topic': topic, 'spec': run.snapshot['spec'], 'budget_context': m.budget_context(s, run, account)})
        if data is None:
            return
        if data.get('estimated_remaining_cost_fen', 0) > m.budget_context(s, run, account)['available_fen']:
            fail('MATRIX_BUDGET_EXCEEDED', '分镜后续素材、配音、盲评与复盘的预估上限超过剩余预算，尚未提交媒体调用')
        if policy_notes(s, tid, data['title'], data['body'], []) or (selected['form'] == 'video' and policy_notes(s, tid, data['title'], ''.join(x['narration'] for x in data['scenes']), [])):
            fail('CONTENT_REVIEW_REQUIRED', '文案或配音存在待核实表述')
        task.data = {**task.data, 'topic': topic, 'draft': data}
        task.stage = 'media'
    elif task.stage == 'media':
        draft = task.data['draft']
        if selected['form'] == 'image_text':
            assets = ensure_media(s, task, run, 'image', 'image', draft['image_prompt'], {'ratio': '3:4', 'raw_only': True}, 'images', 1)
            if assets is None:
                return
            task.data = {**task.data, 'image_assets': assets}
        else:
            clips = dict(task.data.get('clips', {}))
            for index, scene in enumerate(draft['scenes']):
                if scene['kind'] == 'aigc' and str(index) not in clips:
                    assets = ensure_media(s, task, run, 'clip-'+str(index), 'video', scene['prompt'], {'ratio': '9:16', 'duration': 10, 'raw_only': True}, 'video_seconds', 10)
                    if assets is None:
                        return
                    clips[str(index)] = assets[0]
                    task.data = {**task.data, 'clips': clips}
                    s.add(task)
                    s.commit()
            narration = ''.join(x['narration'] for x in draft['scenes'])
            audio = ensure_media(s, task, run, 'speech', 'speech', narration, {}, 'speech_characters', len(narration))
            if audio is None:
                return
            task.data = {**task.data, 'voice_asset': audio[0]}
        task.stage = 'composition'
    elif task.stage == 'composition':
        st = step(s, task, 'composition')
        # Local rendering can be repeated safely; no external posting or paid call occurs here.
        st.status = 'processing'
        s.add(st)
        s.commit()
        from .integrations.storage import Storage, save_asset
        from .integrations.rendering import cards
        from .matrix_rendering import story_video
        draft = task.data['draft']
        if selected['form'] == 'image_text':
            original = own(s, Asset, tid, task.data['image_assets'][0])
            raw = Storage().read(original.object_key)
            assets = [save_asset(s, tid, f'矩阵图文-{i+1}.png', img, 'image/png', True).id for i,img in enumerate(cards(raw, draft['title'], '\n\n'.join(draft['cards']), run.snapshot['profile']['name']))]
        else:
            scenes = []
            for idx, scene in enumerate(draft['scenes']):
                source = task.data.get('clips', {}).get(str(idx)) if scene['kind'] == 'aigc' else scene.get('asset_id')
                raw, mime = None, None
                if source:
                    a = own(s, Asset, tid, source)
                    if not a.consent:
                        fail('ASSET_CONSENT_REQUIRED', '素材授权已撤销')
                    raw, mime = Storage().read(a.object_key), a.mime
                scenes.append({**scene, 'raw': raw, 'mime': mime})
            voice = own(s, Asset, tid, task.data['voice_asset'])
            video, cover, duration = story_video(scenes, draft['title'], run.snapshot['profile']['name'], Storage().read(voice.object_key), run.snapshot['spec']['min_video_seconds'], run.snapshot['spec']['max_video_seconds'])
            assets = [save_asset(s, tid, '矩阵成片.mp4', video, 'video/mp4', True).id, save_asset(s, tid, '矩阵封面.png', cover, 'image/png', True).id]
            task.data = {**task.data, 'duration_seconds': duration}
        content, version = save_content(s, tid, run.actor_id, ContentInput(title=draft['title'], body=draft['body'], assets=assets, form=selected['form']))
        task.content_id, task.version_id, task.stage = content.id, version.id, 'prediction'
        st.status, st.detail = 'succeeded', {'asset_ids': assets, 'version_id': version.id}
        s.add(st)
    elif task.stage == 'prediction':
        result = ensure_agent(s, task, run, 'prediction', 'predict', {'version_id': task.version_id, 'matrix_profile_id': run.snapshot['profile']['id']})
        if result is None:
            return
        if result.get('credibility', 0) < 3:
            fail('CONTENT_REVIEW_REQUIRED', '盲评可信度不足，需核对成品')
        task.stage = 'review'
        task.status = 'trial_ready' if run.trial else 'awaiting_review'
    elif task.stage == 'review':
        if run.trial:
            task.status = 'trial_ready'
        elif run.snapshot['spec']['review'] == 'auto':
            enqueue_publish(s, task, run, account)
        else:
            task.status = 'awaiting_review'
    elif task.stage == 'publish':
        job = own(s, PublishJob, tid, task.publish_job_id)
        st = step(s, task, 'publish')
        st.status, st.object_id = job.status, job.id
        st.detail = {'external_id': job.external_id, 'external_url': job.external_url}
        s.add(st)
        if job.error_code == 'ACCOUNT_BUSY':
            fail('ACCOUNT_BUSY', job.error, 409)
        if job.status == 'succeeded':
            task.stage = 'metrics'
        elif job.status == 'cancelled':
            task.status = 'cancelled'
        elif job.status in ('unknown', 'failed', 'waiting_authorization'):
            fail(job.error_code or 'PUBLISH_WAITING', job.error or '发布结果等待核实', 409)
    elif task.stage == 'metrics':
        job = own(s, PublishJob, tid, task.publish_job_id)
        metrics = s.exec(query(s, MetricSnapshot, tid).where(MetricSnapshot.publish_job_id == job.id).order_by(MetricSnapshot.created_at.desc())).first()
        if not metrics:
            task.status = 'waiting_metrics'
            st = step(s, task, 'metrics')
            st.status, st.detail = 'waiting_metrics', {'due_at': as_utc(job.retro_due_at).isoformat() if job.retro_due_at else None, 'note': job.error or '默认T+3回收，缺失指标支持补录'}
            s.add(st)
            return
        st = step(s, task, 'metrics')
        st.status, st.detail = 'succeeded', metrics.metrics
        s.add(st)
        task.data = {**task.data, 'metric_id': metrics.id}
        task.stage = 'retro'
    elif task.stage == 'retro':
        output = ensure_agent(s, task, run, 'retro', 'retro', {'metric_id': task.data['metric_id']})
        if output is None:
            return
        task.status = 'succeeded'
    task.error, task.error_code = '', ''
    task.updated_at = now()
    s.add(task)


def notify_block(s, tenant, run, task):
    from .reports import enqueue
    # The outbox and in-app task carry only operating status, no family information.
    enqueue(s, tenant, 'matrix:'+task.id+':'+task.error_code, 'matrix', f'自媒体任务需要处理：{run.snapshot["name"]}，阶段{task.stage}。请负责人登录矩阵账号中心查看。')


def execute_run(tid, rid):
    token = uid()
    with Session(engine(), expire_on_commit=False) as s:
        set_scope(s, tid)
        m.lock_tenant(s, tid)
        r = own(s, AutomationRun, tid, rid)
        if r.paused or r.status in ('succeeded', 'trial_ready', 'cancelled'):
            return
        count = len(s.exec(query(s, AutomationRun, tid).where(AutomationRun.lease_until > now(), AutomationRun.id != rid)).all())
        if count >= max(1, settings().matrix_max_running):
            return
        changed = s.exec(update(AutomationRun).where(AutomationRun.id == rid, AutomationRun.tenant_id == tid, or_(AutomationRun.lease_until == None, AutomationRun.lease_until < now())).values(lease_token=token, lease_until=now()+timedelta(minutes=30)))
        s.commit()
        if changed.rowcount != 1:
            return
    try:
        with Session(engine(), expire_on_commit=False) as s:
            set_scope(s, tid)
            r = own(s, AutomationRun, tid, rid)
            tasks = s.exec(query(s, AutomationAccountTask, tid).where(AutomationAccountTask.run_id == rid).order_by(AutomationAccountTask.created_at, AutomationAccountTask.id)).all()
            for original in tasks:
                task_id = original.id
                try:
                    r = own(s, AutomationRun, tid, rid)
                    if r.lease_token != token or r.paused:
                        break
                    task = own(s, AutomationAccountTask, tid, task_id)
                    advance(s, task, r)
                    s.commit()
                except Exception as error:
                    s.rollback()
                    task = own(s, AutomationAccountTask, tid, task_id)
                    detail = error.detail if isinstance(error, HTTPException) and isinstance(error.detail, dict) else {}
                    task.status, task.error_code = 'blocked', detail.get('code', 'EXECUTION_ERROR')
                    task.error = detail.get('message', redact_error(error))
                    task.updated_at = now()
                    s.add(task)
                    notify_block(s, s.get(Tenant, tid), own(s, AutomationRun, tid, rid), task)
                    s.commit()
            m.sync_charges(s, tid)
            r = own(s, AutomationRun, tid, rid)
            s.refresh(r)
            states = [t.status for t in s.exec(query(s, AutomationAccountTask, tid).where(AutomationAccountTask.run_id == rid)).all()]
            if states and all(x == 'trial_ready' for x in states):
                r.status = 'trial_ready'
            elif states and all(x in ('succeeded', 'cancelled') for x in states):
                r.status = 'succeeded' if 'succeeded' in states else 'cancelled'
            elif any(x == 'blocked' for x in states):
                r.status = 'partial' if any(x != 'blocked' for x in states) else 'blocked'
            else:
                r.status = 'running'
            r.revision += 1
            r.updated_at = now()
            s.add(r)
            s.commit()
    finally:
        with Session(engine()) as s:
            set_scope(s, tid)
            s.exec(update(AutomationRun).where(AutomationRun.id == rid, AutomationRun.tenant_id == tid, AutomationRun.lease_token == token).values(lease_until=None, lease_token=''))
            s.commit()


def tick_matrix(s, tenant):
    from .auth import entitlement
    if not entitlement(s, tenant)['active']:
        return
    current = now().astimezone(m.TZ)
    if not tenant.settings.get('matrix_paused'):
        for p in s.exec(query(s, AutomationPlan, tenant.id).where(AutomationPlan.enabled == True)).all():
            try:
                if current.weekday() not in p.spec['weekdays']:
                    continue
                for hhmm in p.spec['times']:
                    hh, mm = map(int, hhmm.split(':'))
                    slot = current.replace(hour=hh, minute=mm, second=0, microsecond=0)
                    if not (timedelta(0) <= current-slot <= timedelta(minutes=15)):
                        continue
                    req = 'schedule:'+p.id+':'+str(p.version)+':'+slot.isoformat()
                    m.create_run(s, tenant.id, p.actor_id, p, req, False, slot)
                    s.commit()
            except Exception as error:
                s.rollback()
                p = own(s, AutomationPlan, tenant.id, p.id)
                p.last_error = redact_error(error)
                s.add(p)
                s.commit()
    for r in s.exec(query(s, AutomationRun, tenant.id).where(AutomationRun.status.notin_(['trial_ready','succeeded','cancelled']), AutomationRun.paused == False)).all():
        dispatch_run(tenant.id, r.id)


def matrix_overview(s, tenant, profile_id='', group_id='', account_id='', start=None, end=None):
    tid = tenant.id
    if start and end and as_utc(start) >= as_utc(end):
        fail('PERIOD_INVALID', '结束日期须晚于开始日期')
    account_ids = None
    if profile_id:
        own(s, MediaProfile, tid, profile_id)
    if group_id:
        group = own(s, AccountGroup, tid, group_id)
        account_ids = {x.account_id for x in s.exec(query(s, AccountGroupMember, tid).where(AccountGroupMember.group_id == group.id)).all()}
    if account_id:
        own(s, SocialAccount, tid, account_id)
        account_ids = {account_id} if account_ids is None else account_ids & {account_id}
    all_accounts = s.exec(query(s, SocialAccount, tid)).all()
    accounts = [a for a in all_accounts if (not profile_id or a.profile_id == profile_id) and (account_ids is None or a.id in account_ids)]
    ids = {a.id for a in accounts}
    jobs = [j for j in s.exec(query(s, PublishJob, tid)).all() if j.account_id in ids and (not start or as_utc(j.created_at) >= as_utc(start)) and (not end or as_utc(j.created_at) < as_utc(end))]
    charges = [c for c in s.exec(query(s, MatrixCharge, tid)).all() if (not profile_id or c.profile_id == profile_id) and (not c.account_id or c.account_id in ids) and (not start or as_utc(c.created_at) >= as_utc(start)) and (not end or as_utc(c.created_at) < as_utc(end))]
    metrics = s.exec(query(s, MetricSnapshot, tid).order_by(MetricSnapshot.created_at.desc())).all()
    latest = {}
    for metric in metrics:
        latest.setdefault(metric.publish_job_id, metric.metrics)
    group_rows = s.exec(query(s, AccountGroupMember, tid)).all()
    plans = s.exec(query(s, AutomationPlan, tid)).all()
    tasks = [t for t in s.exec(query(s, AutomationAccountTask, tid)).all() if t.account_id in ids]
    sources = {'matrix:'+t.id: t.account_id for t in tasks}
    leads = [l for l in s.exec(query(s, Record, tid).where(Record.kind == "lead")).all() if l.data.get("source") in sources and (not start or as_utc(l.created_at) >= as_utc(start)) and (not end or as_utc(l.created_at) < as_utc(end))]
    entries = []
    for a in accounts:
        ownjobs = sorted([j for j in jobs if j.account_id == a.id], key=lambda j: as_utc(j.created_at), reverse=True)
        costs = [c for c in charges if c.account_id == a.id]
        next_dates = []
        for p in plans:
            if p.enabled and a.id in {target.id for target in m.targets(s, tid, p.profile_id, p.spec)}:
                next_dates.append(m.next_slot(p.spec))
        entries.append({**a.model_dump(mode='json'), 'identity_verified': bool(a.identity_key), 'group_ids': [g.group_id for g in group_rows if g.account_id == a.id], 'cost_fen': sum(c.actual_fen for c in costs if c.state == 'settled'), 'reserved_fen': sum(c.reserved_fen for c in costs if c.state == 'reserved'), 'published': sum(j.status == 'succeeded' for j in ownjobs), 'attributed_leads': sum(sources[l.data['source']] == a.id for l in leads), 'attributed_enrollments': sum(sources[l.data['source']] == a.id and bool(l.data.get('won_at')) for l in leads), 'last_result': ownjobs[0].model_dump(mode='json') if ownjobs else None, 'next_publish_at': min(filter(None, next_dates), default=None), 'works': [{**j.model_dump(mode='json'), 'metrics': latest.get(j.id)} for j in ownjobs[:100]]})
    return {'attributed_leads': len(leads), 'attributed_enrollments': sum(bool(l.data.get('won_at')) for l in leads), 'account_used': len(all_accounts), 'account_limit': m.account_limit(s, tenant), 'monthly_budget_fen': tenant.settings.get('matrix_monthly_budget_fen', 0), 'paused': tenant.settings.get('matrix_paused', False), 'accounts': entries, 'published': sum(j.status == 'succeeded' for j in jobs), 'exceptions': sum(j.status in ('failed','unknown','waiting_authorization') for j in jobs), 'cost_fen': sum(c.actual_fen for c in charges if c.state == 'settled'), 'reserved_fen': sum(c.reserved_fen for c in charges if c.state == 'reserved'), 'shared_cost_fen': sum(c.actual_fen for c in charges if not c.account_id and c.state == 'settled'), 'platforms': dict(Counter(a.platform for a in accounts)), 'metric_note': '不同平台指标分别展示；缺失为null，不以0替代。招生归因仅统计明确关联记录。'}

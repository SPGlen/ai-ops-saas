"""Matrix APIs share institution membership and the existing role catalog."""
import asyncio, json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select, delete
from .models import *
from .db import engine, set_scope
from .auth import Identity, scoped, platform, writable
from .permissions import permit, identity_for, has
from .domain import own, query, audit
from .security import fail, redact_error
from . import matrix as m
from . import matrix_schemas as S
from .integrations import publishing

router = APIRouter(prefix="/api/v1", tags=["自媒体自动运营与矩阵"])


def owner(i):
    permit(i, "social.manage")
    writable(i)


def disable_plans(s, tid, profile_id):
    for p in s.exec(query(s, AutomationPlan, tid).where(AutomationPlan.profile_id == profile_id)).all():
        p.enabled = False
        p.authorized_by = ""
        s.add(p)


def check_version(obj, version):
    if version != obj.version:
        fail("VERSION_CONFLICT", "资料已被更新，请刷新后操作", 409)


@router.get("/media-profiles", response_model=list[MediaProfile])
def profiles(i: Identity = Depends(scoped)):
    permit(i, "content.read")
    return i.session.exec(query(i.session, MediaProfile, i.tenant.id)).all()


@router.post("/media-profiles", status_code=201, response_model=MediaProfile)
def profile_add(body: S.ProfileInput, i: Identity = Depends(scoped)):
    permit(i, "content.write")
    writable(i)
    p = MediaProfile(tenant_id=i.tenant.id, **body.model_dump(exclude={"version"}))
    m.validate_profile(i.session, i.tenant.id, p)
    i.session.add(p)
    audit(i.session, i.tenant.id, i.user.id, "matrix.profile.created", p.id)
    i.session.commit()
    return p


@router.patch("/media-profiles/{profile_id}", response_model=MediaProfile)
def profile_edit(profile_id: str, body: S.ProfileInput, i: Identity = Depends(scoped)):
    permit(i, "content.write")
    writable(i)
    m.lock_tenant(i.session, i.tenant.id)
    p = own(i.session, MediaProfile, i.tenant.id, profile_id)
    i.session.refresh(p)
    check_version(p, body.version)
    for k,v in body.model_dump(exclude={"version"}).items():
        setattr(p, k, v)
    m.validate_profile(i.session, i.tenant.id, p)
    p.version += 1
    p.updated_at = now()
    i.session.add(p)
    disable_plans(i.session, i.tenant.id, p.id)
    audit(i.session, i.tenant.id, i.user.id, "matrix.profile.updated", p.id)
    i.session.commit()
    return p


def group_view(s, tid, group):
    return {**group.model_dump(), "account_ids": [x.account_id for x in s.exec(query(s, AccountGroupMember, tid).where(AccountGroupMember.group_id == group.id)).all()]}


@router.get("/account-groups")
def groups(i: Identity = Depends(scoped)):
    permit(i, "social.read")
    return [group_view(i.session, i.tenant.id, g) for g in i.session.exec(query(i.session, AccountGroup, i.tenant.id)).all()]


def save_group(i, body, gid=None):
    owner(i)
    m.lock_tenant(i.session, i.tenant.id)
    own(i.session, MediaProfile, i.tenant.id, body.profile_id)
    accounts = [own(i.session, SocialAccount, i.tenant.id, a) for a in set(body.account_ids)]
    if any(a.profile_id != body.profile_id for a in accounts):
        fail("PROFILE_MISMATCH", "分组只能包含相同品牌账号")
    g = own(i.session, AccountGroup, i.tenant.id, gid) if gid else AccountGroup(tenant_id=i.tenant.id, profile_id=body.profile_id, name=body.name)
    if gid:
        check_version(g, body.version)
        if g.profile_id != body.profile_id:
            fail("PROFILE_MISMATCH", "已有分组不能改变品牌")
        g.name = body.name
        g.version += 1
        i.session.exec(delete(AccountGroupMember).where(AccountGroupMember.tenant_id == i.tenant.id, AccountGroupMember.group_id == gid))
    i.session.add(g)
    i.session.flush()
    for a in accounts:
        i.session.add(AccountGroupMember(tenant_id=i.tenant.id, group_id=g.id, account_id=a.id))
    disable_plans(i.session, i.tenant.id, body.profile_id)
    audit(i.session, i.tenant.id, i.user.id, "matrix.group.saved", g.id)
    i.session.commit()
    return group_view(i.session, i.tenant.id, g)


@router.post("/account-groups", status_code=201)
def group_add(body: S.GroupInput, i: Identity = Depends(scoped)):
    return save_group(i, body)


@router.patch("/account-groups/{group_id}")
def group_edit(group_id: str, body: S.GroupInput, i: Identity = Depends(scoped)):
    return save_group(i, body, group_id)


@router.patch("/social-accounts/{account_id}/matrix", response_model=SocialAccount)
def account_config(account_id: str, body: S.AccountConfig, i: Identity = Depends(scoped)):
    owner(i)
    m.lock_tenant(i.session, i.tenant.id)
    a = own(i.session, SocialAccount, i.tenant.id, account_id)
    if body.profile_id:
        own(i.session, MediaProfile, i.tenant.id, body.profile_id)
    if a.profile_id != body.profile_id:
        links = i.session.exec(query(i.session, AccountGroupMember, i.tenant.id).where(AccountGroupMember.account_id == a.id)).all()
        if links:
            fail("ACCOUNT_IN_GROUP", "请先将账号移出原品牌分组")
    old_profile = a.profile_id
    a.profile_id, a.paused = body.profile_id, body.paused
    old = a.config.get("matrix", {})
    a.config = {**a.config, "matrix": body.model_dump(exclude={"profile_id", "paused"})}
    if old != a.config["matrix"] or old_profile != a.profile_id:
        for profile in set(filter(None, [old_profile, a.profile_id])):
            disable_plans(i.session, i.tenant.id, profile)
    i.session.add(a)
    audit(i.session, i.tenant.id, i.user.id, "matrix.account.configured", a.id)
    i.session.commit()
    return a


@router.post("/matrix/accounts/batch")
def account_batch(body: S.BatchInput, i: Identity = Depends(scoped)):
    owner(i)
    accounts = [own(i.session, SocialAccount, i.tenant.id, aid) for aid in sorted(set(body.account_ids))]
    results = []
    for a in accounts:
        try:
            if body.operation == "check":
                result = publishing.check_login(i.tenant.id, a)
                m.observed_identity(i.session, i.tenant.id, a, result)
            else:
                a.paused = body.operation == "pause"
                i.session.add(a)
            results.append({"account_id": a.id, "status": a.status, "paused": a.paused, "identity_verified": bool(a.identity_key)})
        except Exception as e:
            results.append({"account_id": a.id, "status": "failed", "error": redact_error(e)})
    audit(i.session, i.tenant.id, i.user.id, "matrix.accounts.batch", i.tenant.id, operation=body.operation, account_ids=body.account_ids)
    i.session.commit()
    return {"results": results}


class MatrixSettings(S.Strict):
    monthly_budget_fen: int = S.Field(ge=0, le=100000000)
    paused: bool = False


@router.put("/matrix/settings")
def matrix_settings(body: MatrixSettings, i: Identity = Depends(scoped)):
    owner(i)
    i.tenant = m.lock_tenant(i.session, i.tenant.id)
    i.tenant.settings = {**i.tenant.settings, "matrix_monthly_budget_fen": body.monthly_budget_fen, "matrix_paused": body.paused}
    i.session.add(i.tenant)
    audit(i.session, i.tenant.id, i.user.id, "matrix.settings", i.tenant.id, **body.model_dump())
    i.session.commit()
    return body


@router.put("/platform/tenants/{tenant_id}/matrix")
def matrix_entitlement(tenant_id: str, body: S.MatrixEntitlementInput, i: Identity = Depends(platform)):
    tenant = i.session.get(Tenant, tenant_id)
    if not tenant:
        fail("NOT_FOUND", "机构不存在", 404)
    tenant.settings = {**tenant.settings, "matrix_account_limit": body.account_limit}
    i.session.add(tenant)
    set_scope(i.session, tenant_id, i.user.id)
    audit(i.session, tenant_id, i.user.id, "matrix.entitlement", tenant_id, account_limit=body.account_limit)
    i.session.commit()
    return {"account_limit": body.account_limit}


@router.get("/automation-plans", response_model=list[AutomationPlan])
def plans(i: Identity = Depends(scoped)):
    permit(i, "campaign.read")
    return i.session.exec(query(i.session, AutomationPlan, i.tenant.id).order_by(AutomationPlan.created_at.desc())).all()


def save_plan(i, body, pid=None):
    permit(i, "campaign.write")
    writable(i)
    m.lock_tenant(i.session, i.tenant.id)
    own(i.session, MediaProfile, i.tenant.id, body.profile_id)
    spec = body.spec.model_dump()
    m.targets(i.session, i.tenant.id, body.profile_id, spec)
    p = own(i.session, AutomationPlan, i.tenant.id, pid) if pid else AutomationPlan(tenant_id=i.tenant.id, profile_id=body.profile_id, name=body.name, actor_id=i.user.id)
    if pid:
        check_version(p, body.version)
        if p.profile_id != body.profile_id:
            fail("PROFILE_MISMATCH", "计划不能变更品牌，请新建")
        p.version += 1
    p.name, p.spec = body.name, spec
    p.enabled = False
    p.authorized_by = i.user.id if "owner" in i.roles else ""
    p.actor_id = i.user.id
    p.updated_at = now()
    i.session.add(p)
    i.session.flush()
    i.session.add(AutomationPlanVersion(tenant_id=i.tenant.id, plan_id=p.id, version=p.version, snapshot=m.snapshot(i.session, p)))
    audit(i.session, i.tenant.id, i.user.id, "matrix.plan.saved", p.id, version=p.version)
    i.session.commit()
    return p


@router.post("/automation-plans", status_code=201, response_model=AutomationPlan)
def plan_add(body: S.PlanInput, i: Identity = Depends(scoped)):
    return save_plan(i, body)


@router.patch("/automation-plans/{plan_id}", response_model=AutomationPlan)
def plan_edit(plan_id: str, body: S.PlanInput, i: Identity = Depends(scoped)):
    return save_plan(i, body, plan_id)


@router.post("/automation-plans/{plan_id}/authorize", response_model=AutomationPlan)
def plan_authorize(plan_id: str, body: S.EnabledInput, i: Identity = Depends(scoped)):
    owner(i)
    p = own(i.session, AutomationPlan, i.tenant.id, plan_id)
    check_version(p, body.version)
    p.authorized_by = i.user.id if body.enabled else ""
    p.actor_id = i.user.id
    p.enabled = False
    i.session.add(p)
    audit(i.session, i.tenant.id, i.user.id, "matrix.plan.authorized", p.id, enabled=body.enabled)
    i.session.commit()
    return p


@router.post("/automation-plans/{plan_id}/enabled", response_model=AutomationPlan)
def plan_enabled(plan_id: str, body: S.EnabledInput, i: Identity = Depends(scoped)):
    owner(i)
    p = own(i.session, AutomationPlan, i.tenant.id, plan_id)
    check_version(p, body.version)
    if body.enabled:
        m.check_ready(i.session, i.tenant, p)
    p.enabled = body.enabled
    p.authorized_by, p.actor_id = i.user.id, i.user.id
    i.session.add(p)
    audit(i.session, i.tenant.id, i.user.id, "matrix.plan.enabled", p.id, enabled=body.enabled)
    i.session.commit()
    return p


@router.get("/automation-plans/{plan_id}/preview")
def plan_preview(plan_id: str, i: Identity = Depends(scoped)):
    permit(i, "campaign.read")
    p = own(i.session, AutomationPlan, i.tenant.id, plan_id)
    snap = m.snapshot(i.session, p)
    return {"accounts": snap["accounts"], "account_count": len(snap["accounts"]), "budget_ceiling_fen": p.spec["run_budget_fen"], "next_slot": m.next_slot(p.spec), "model_call_range": {"min": len(snap["accounts"])*3, "max": len(snap["accounts"])*13}, "note": "实际成本取决于AI分镜；每次调用前检查预算"}


@router.get("/automation-runs", response_model=list[S.RunSummary])
def runs(i: Identity = Depends(scoped), plan_id: str = "", limit: int = 50):
    permit(i, "campaign.read")
    q = query(i.session, AutomationRun, i.tenant.id)
    if plan_id:
        own(i.session, AutomationPlan, i.tenant.id, plan_id)
        q = q.where(AutomationRun.plan_id == plan_id)
    return [m.run_summary(i.session, r) for r in i.session.exec(q.order_by(AutomationRun.created_at.desc()).limit(max(1, min(limit, 100)))).all()]


@router.post("/automation-runs", status_code=202, response_model=S.RunView)
def run_add(body: S.RunInput, i: Identity = Depends(scoped)):
    permit(i, "campaign.write")
    writable(i)
    p = own(i.session, AutomationPlan, i.tenant.id, body.plan_id)
    r = m.create_run(i.session, i.tenant.id, i.user.id, p, body.request_id, body.trial, body.slot)
    i.session.commit()
    from .matrix_worker import dispatch_run
    dispatch_run(i.tenant.id, r.id)
    return m.run_view(i.session, r)


@router.get("/automation-runs/{run_id}", response_model=S.RunView)
def run_detail(run_id: str, i: Identity = Depends(scoped)):
    permit(i, "campaign.read")
    return m.run_view(i.session, own(i.session, AutomationRun, i.tenant.id, run_id))


@router.post("/automation-runs/{run_id}/{operation}", response_model=S.RunView)
def run_action(run_id: str, operation: str, i: Identity = Depends(scoped)):
    permit(i, "campaign.write")
    writable(i)
    r = own(i.session, AutomationRun, i.tenant.id, run_id)
    if operation not in ("pause", "resume"):
        fail("OPERATION_INVALID", "不支持此操作")
    r.paused = operation == "pause"
    r.revision += 1
    r.updated_at = now()
    i.session.add(r)
    audit(i.session, i.tenant.id, i.user.id, "matrix.run." + operation, r.id)
    i.session.commit()
    return m.run_view(i.session, r)


@router.post("/automation-tasks/{task_id}/approve", response_model=S.TaskView)
def task_approve(task_id: str, i: Identity = Depends(scoped)):
    permit(i, "publish.write")
    writable(i)
    task, run, account = m.guard(i.session, i.tenant.id, task_id, publishing=True)
    if task.status != "awaiting_review":
        fail("TASK_STATE_INVALID", "该任务当前不在审核阶段", 409)
    from .matrix_worker import enqueue_publish
    enqueue_publish(i.session, task, run, account, i.user.id)
    i.session.commit()
    return m.task_view(i.session, i.tenant.id, task)


@router.get("/automation-runs/{run_id}/events")
def run_events(run_id: str, request: Request, i: Identity = Depends(scoped)):
    permit(i, "campaign.read")
    own(i.session, AutomationRun, i.tenant.id, run_id)
    tid, uid, sid = i.tenant.id, i.user.id, i.auth.id
    async def events():
        previous = ""
        for _ in range(240):
            if await request.is_disconnected():
                return
            with Session(engine()) as s:
                set_scope(s, tid, uid)
                auth = s.get(AuthSession, sid)
                if not auth or as_utc(auth.expires_at) <= now() or auth.tenant_id != tid:
                    return
                try:
                    actor = identity_for(s, s.get(Tenant, tid), uid)
                    permit(actor, "campaign.read")
                    data = json.dumps(m.run_view(s, own(s, AutomationRun, tid, run_id)), ensure_ascii=False, default=str)
                except Exception:
                    return
            if data != previous:
                yield "event: update\ndata: " + data + "\n\n"
                previous = data
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/matrix/overview")
def overview(i: Identity = Depends(scoped), profile_id: str = "", group_id: str = "", account_id: str = "", start: datetime | None = None, end: datetime | None = None):
    permit(i, "social.read")
    from .matrix_worker import matrix_overview
    return matrix_overview(i.session, i.tenant, profile_id, group_id, account_id, start, end)


@router.get("/matrix/calendar")
def matrix_calendar(i: Identity = Depends(scoped), profile_id: str = "", group_id: str = "", account_id: str = "", start: datetime | None = None, end: datetime | None = None):
    permit(i, "publish.read")
    start = as_utc(start) if start else now()
    end = as_utc(end) if end else start+timedelta(days=14)
    if end <= start or end-start > timedelta(days=35):
        fail("PERIOD_INVALID", "日历范围应为1至35天")
    view = overview(i, profile_id, group_id, account_id)
    allowed = {a["id"] for a in view["accounts"]}
    events = [{"type": "publish_job", "account_id": j.account_id, "at": as_utc(j.scheduled_at).isoformat(), "status": j.status, "id": j.id, "external_url": j.external_url} for j in i.session.exec(query(i.session, PublishJob, i.tenant.id).where(PublishJob.account_id.in_(allowed), PublishJob.scheduled_at >= start, PublishJob.scheduled_at < end)).all()]
    for p in i.session.exec(query(i.session, AutomationPlan, i.tenant.id).where(AutomationPlan.enabled == True)).all():
        targets = {a.id for a in m.targets(i.session, i.tenant.id, p.profile_id, p.spec)} & allowed
        slot = m.next_slot(p.spec, start-timedelta(seconds=1))
        while slot and slot < end:
            events += [{"type": "plan_slot", "account_id": aid, "at": slot.isoformat(), "status": "projected", "plan_id": p.id, "name": p.name} for aid in sorted(targets)]
            slot = m.next_slot(p.spec, slot)
    return sorted(events, key=lambda e: e["at"])[:2000]


@router.post("/social-accounts/{account_id}/matrix-probe")
def matrix_probe(account_id: str, i: Identity = Depends(scoped)):
    owner(i)
    a = own(i.session, SocialAccount, i.tenant.id, account_id)
    result = publishing.check_login(i.tenant.id, a)
    m.observed_identity(i.session, i.tenant.id, a, result)
    verified = dict(a.config.get("verified_capabilities", {}))
    reason = "发布能力通过实际发布确认，指标能力通过实际作品回收确认"
    if a.identity_key and a.platform == "xiaohongshu":
        try:
            out = publishing.call(i.tenant.id, a.id, "search", {"platform": a.platform, "keyword": "AI教育"}, 60)
            verified["search"] = out.get("available") is True and isinstance(out.get("items"), list)
        except Exception:
            verified["search"] = False
            reason = "搜索暂不可用；" + reason
    a.config = {**a.config, "verified_capabilities": verified}
    i.session.add(a)
    i.session.commit()
    return {"account_id": a.id, "identity_verified": bool(a.identity_key), "capabilities": verified, "reason": reason}


class RetryStepInput(S.Strict):
    request_id: str = S.Field(min_length=8, max_length=100)


@router.post("/automation-tasks/{task_id}/steps/{key}/retry")
def retry_step(task_id: str, key: str, body: RetryStepInput, i: Identity = Depends(scoped)):
    permit(i, "content.write")
    writable(i)
    task, run, account = m.guard(i.session, i.tenant.id, task_id)
    m.lock_tenant(i.session, i.tenant.id)
    i.session.refresh(run)
    if run.lease_until and as_utc(run.lease_until) > now():
        fail("RUN_BUSY", "任务正在更新，请稍后重试", 409)
    st = i.session.exec(query(i.session, AutomationStep, i.tenant.id).where(AutomationStep.task_id == task.id, AutomationStep.key == key)).first()
    if not st or not st.object_id:
        fail("NOT_FOUND", "步骤没有可重试的模型任务", 404)
    model = MediaJob if key == "image" or key == "speech" or key.startswith("clip-") else AgentRun
    if key in ("publish", "metrics", "sources", "composition"):
        fail("RESUME_NOT_SAFE", "该步骤请使用结果核实或恢复运行")
    if key == "topic" and run.snapshot["spec"]["mode"] == "matrix":
        fail("RESUME_NOT_SAFE", "共享选题失败请创建新运行；未知结果仍需先核实")
    req = "mx:retry:" + body.request_id
    prior = i.session.exec(query(i.session, model, i.tenant.id).where(model.request_id == req)).first()
    if prior:
        tagged = prior.parameters if model is MediaJob else prior.input
        if tagged.get("_matrix_task_id") != task_id or tagged.get("_matrix_step_key") != key:
            fail("IDEMPOTENCY_CONFLICT", "请求已用于其他任务", 409)
        return {"object_id": prior.id, "status": prior.status}
    old = own(i.session, model, i.tenant.id, st.object_id)
    safe = {"MODEL_RATE_LIMITED", "MODEL_REQUEST_REJECTED", "MODEL_KEY_REJECTED", "KEY_REQUIRED", "MODEL_UNCONFIGURED"}
    if old.status not in ("failed", "waiting_authorization") or old.error_code not in safe:
        fail("RESUME_NOT_SAFE", "只允许重试已明确拒绝且未产生结果的调用；超时或未知结果须先核实", 409)
    if model is MediaJob and (old.provider_task_id or old.parameters.get("result_urls") or old.parameters.get("raw_assets") or old.parameters.get("result_url")):
        fail("RESUME_NOT_SAFE", "已有供应商结果，请继续回收，不能重新付费创建", 409)
    resource = "text_tokens" if model is AgentRun else "images" if old.kind == "image" else "speech_characters" if old.kind == "speech" else "video_seconds"
    original = i.session.exec(query(i.session, UsageRecord, i.tenant.id).where(UsageRecord.request_id == old.request_id, UsageRecord.resource == resource)).first()
    if not original or original.state != "settled" or original.actual:
        fail("RESUME_NOT_SAFE", "原调用费用尚未明确结算，不能创建新的付费调用", 409)
    m.charge(i.session, i.tenant.id, task, req, resource, original.reserved, old.funding)
    if model is AgentRun:
        job = AgentRun(tenant_id=i.tenant.id, kind=old.kind, request_id=req, actor_id=run.actor_id, funding=old.funding, input={**old.input, "_matrix_step_key": key})
    else:
        params = {k:v for k,v in old.parameters.items() if k not in ("submitted", "_retry_count")}
        job = MediaJob(tenant_id=i.tenant.id, kind=old.kind, request_id=req, actor_id=run.actor_id, funding=old.funding, prompt=old.prompt, parameters={**params, "_matrix_step_key": key})
    i.session.add(job)
    i.session.flush()
    st.object_id, st.status = job.id, "queued"
    task.status, task.error, task.error_code = "queued", "", ""
    run.status = "running"
    run.revision += 1
    i.session.add(st);i.session.add(task);i.session.add(run)
    audit(i.session, i.tenant.id, i.user.id, "matrix.step.retry", task.id, previous_id=old.id, object_id=job.id, key=key)
    i.session.commit()
    from .worker import dispatch
    dispatch("media" if model is MediaJob else "agent", i.tenant.id, job.id)
    return {"object_id": job.id, "status": job.status}

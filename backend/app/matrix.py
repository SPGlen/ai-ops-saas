"""Institution matrix policy. No credential or personal-workspace imports."""
import hashlib, json, math
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
from sqlmodel import select
from sqlalchemy import update
from .models import *
from .domain import own, query, audit
from .security import fail
from .permissions import identity_for, permit, has, member_roles
from .auth import entitlement
from .matrix_schemas import PlanSpec

TZ = ZoneInfo("Asia/Shanghai")
TABLES = ["media_profiles", "account_groups", "account_group_members", "automation_plans", "automation_plan_versions", "automation_runs", "automation_account_tasks", "automation_steps", "matrix_charges"]
STAGES = ["sources", "creation", "media", "composition", "prediction", "review", "publish", "metrics", "retro"]


def lock_tenant(s, tid):
    # A real write lock also serializes SQLite development writers.
    s.exec(update(Tenant).where(Tenant.id == tid).values(status=Tenant.status))
    return s.exec(select(Tenant).where(Tenant.id == tid).execution_options(populate_existing=True).with_for_update()).one()


def account_limit(s, tenant):
    cfg = s.get(PlatformSettings, 1)
    catalog = cfg.plans.get("catalog", []) if cfg else []
    plan = next((p for p in catalog if p.get("id") == tenant.settings.get("plan_id")), {})
    return int(tenant.settings.get("matrix_account_limit", plan.get("account_limit", 9)))


def facts(s, tid, profile):
    result = []
    for rid in profile.knowledge_ids:
        r = own(s, Record, tid, rid)
        if r.kind != "knowledge" or not r.data.get("approved"):
            fail("KNOWLEDGE_REQUIRED", "品牌只能引用已审核知识库")
        result.append({"id": r.id, "title": r.data.get("name", ""), "body": r.data.get("body", ""), "version": r.version})
    return result


def validate_profile(s, tid, profile):
    facts(s, tid, profile)
    for aid in profile.asset_ids:
        a = own(s, Asset, tid, aid)
        if not a.consent or not a.object_key.startswith(tid + "/content/") or a.mime not in ("image/png", "image/jpeg", "image/webp", "video/mp4"):
            fail("ASSET_CONSENT_REQUIRED", "品牌素材须为已授权内容素材")


def targets(s, tid, profile_id, spec):
    ids = list(spec.get("account_ids", []))
    for gid in spec.get("group_ids", []):
        group = own(s, AccountGroup, tid, gid)
        if group.profile_id != profile_id:
            fail("PROFILE_MISMATCH", "计划和分组必须属于同一品牌")
        ids += [m.account_id for m in s.exec(query(s, AccountGroupMember, tid).where(AccountGroupMember.group_id == gid)).all()]
    accounts = [own(s, SocialAccount, tid, aid) for aid in sorted(set(ids))]
    if any(a.profile_id != profile_id for a in accounts):
        fail("PROFILE_MISMATCH", "目标账号必须属于计划品牌")
    return accounts


def snapshot(s, plan):
    profile = own(s, MediaProfile, plan.tenant_id, plan.profile_id)
    validate_profile(s, plan.tenant_id, profile)
    accounts = targets(s, plan.tenant_id, profile.id, plan.spec)
    return {"name": plan.name, "spec": plan.spec, "profile": {k: getattr(profile, k) for k in ("id", "name", "audience", "style", "knowledge_ids", "asset_ids", "version", "rubrics")}, "facts": facts(s, plan.tenant_id, profile), "accounts": [{"id": a.id, "platform": a.platform, "name": a.name, "identity_key": a.identity_key, "positioning": a.config.get("matrix", {}).get("positioning", ""), "call_to_action": a.config.get("matrix", {}).get("call_to_action", ""), "form": a.config.get("matrix", {}).get("form") or ("image_text" if a.platform == "xiaohongshu" else "video")} for a in accounts]}


def check_ready(s, tenant, plan):
    snap = snapshot(s, plan)
    if not snap["facts"] or not snap["accounts"]:
        fail("MATRIX_SETUP_REQUIRED", "请配置已审核知识库和目标账号")
    spec = plan.spec
    if not spec.get("run_budget_fen") or not spec.get("daily_budget_fen") or not tenant.settings.get("matrix_monthly_budget_fen"):
        fail("BUDGET_REQUIRED", "请配置机构月预算、计划日预算及单次预算")
    from .integrations import aliyun
    aliyun.config(s, tenant.id, spec["funding"])
    if spec.get("review") == "auto" and not tenant.settings.get("publishing_enabled"):
        fail("PUBLISHING_NOT_AUTHORIZED", "请先完成机构发布授权")
    for item in snap["accounts"]:
        a = own(s, SocialAccount, tenant.id, item["id"])
        if not a.identity_key or a.status != "connected" or a.paused:
            fail("IDENTITY_REQUIRED", "目标账号需完成身份核验并解除暂停")
        capability = "publish_image" if item["form"] == "image_text" else "publish_video"
        if not a.config.get("verified_capabilities", {}).get(capability):
            fail("CAPABILITY_UNVERIFIED", "目标账号发布能力尚未验证")
        if not a.config.get("matrix", {}).get("monthly_budget_fen"):
            fail("BUDGET_REQUIRED", "请设置每个账号的月预算")
    previous = s.exec(query(s, AutomationRun, tenant.id).where(AutomationRun.plan_id == plan.id, AutomationRun.plan_version == plan.version, AutomationRun.trial == True)).all()
    passed = False
    for run in previous:
        tasks = s.exec(query(s, AutomationAccountTask, tenant.id).where(AutomationAccountTask.run_id == run.id)).all()
        passed |= run.snapshot == snap and bool(tasks) and all(t.version_id and t.status == "trial_ready" for t in tasks)
    if not passed:
        fail("TRIAL_REQUIRED", "请先让当前计划版本完成一次成品与盲评试运行")
    return snap


def create_run(s, tid, actor, plan, request_id, trial=True, slot=None):
    lock_tenant(s, tid)
    previous = s.exec(query(s, AutomationRun, tid).where(AutomationRun.request_id == request_id)).first()
    if previous:
        if previous.plan_id != plan.id or previous.trial != trial:
            fail("IDEMPOTENCY_CONFLICT", "重复请求参数不同", 409)
        return previous
    tenant = s.get(Tenant, tid)
    if not entitlement(s, tenant)["active"]:
        fail("ENTITLEMENT_EXPIRED", "使用期已结束", 402)
    identity = identity_for(s, tenant, actor)
    permit(identity, "campaign.write")
    if not plan.authorized_by or "owner" not in identity_for(s, tenant, plan.authorized_by).roles:
        fail("BUDGET_AUTHORIZATION_REQUIRED", "请负责人先授权当前计划版本的预算", 403)
    if not trial:
        permit(identity, "publish.write")
        if not plan.enabled:
            fail("PLAN_DISABLED", "计划尚未获得负责人启用")
    snap = snapshot(s, plan)
    if not snap["facts"] or not snap["accounts"]:
        fail("MATRIX_SETUP_REQUIRED", "请先配置品牌知识库和明确账号")
    if not plan.spec.get("run_budget_fen") or not plan.spec.get("daily_budget_fen"):
        fail("BUDGET_REQUIRED", "试运行也需要配置预算")
    run = AutomationRun(tenant_id=tid, plan_id=plan.id, plan_version=plan.version, request_id=request_id, actor_id=actor, trial=trial, slot=slot or now(), snapshot=snap)
    s.add(run)
    s.flush()
    for account in snap["accounts"]:
        s.add(AutomationAccountTask(tenant_id=tid, run_id=run.id, account_id=account["id"]))
    audit(s, tid, actor, "matrix.run.created", run.id, plan_id=plan.id, account_ids=[a["id"] for a in snap["accounts"]], trial=trial)
    s.flush()
    return run


def guard(s, tid, task_id, publishing=False):
    task = own(s, AutomationAccountTask, tid, task_id)
    run = own(s, AutomationRun, tid, task.run_id)
    s.refresh(run)
    tenant = s.get(Tenant, tid)
    s.refresh(tenant)
    actor = identity_for(s, tenant, run.actor_id)
    permit(actor, "publish.write" if publishing else "content.write")
    if not entitlement(s, tenant)["active"]:
        fail("ENTITLEMENT_EXPIRED", "使用期已结束", 402)
    plan = own(s, AutomationPlan, tid, run.plan_id)
    s.refresh(plan)
    account = own(s, SocialAccount, tid, task.account_id)
    s.refresh(account)
    if run.paused or account.paused or tenant.settings.get("matrix_paused"):
        fail("MATRIX_PAUSED", "运行或账号已暂停", 409)
    if plan.version != run.plan_version:
        fail("PLAN_VERSION_CHANGED", "计划已发布新版本，请新建运行", 409)
    if not plan.authorized_by or "owner" not in identity_for(s, tenant, plan.authorized_by).roles:
        fail("ROLE_REVOKED", "计划预算授权已失效", 403)
    if not run.trial:
        if not plan.enabled or plan.version != run.plan_version:
            fail("PLAN_DISABLED", "计划已暂停或版本已变更", 409)
        owner = identity_for(s, tenant, plan.authorized_by)
        if "owner" not in owner.roles:
            fail("ROLE_REVOKED", "计划授权负责人已失效", 403)
    profile = own(s, MediaProfile, tid, run.snapshot["profile"]["id"])
    if account.profile_id != profile.id or profile.version != run.snapshot["profile"]["version"]:
        fail("PROFILE_CHANGED", "品牌或账号归属已变更，请新建运行", 409)
    for fact in run.snapshot["facts"]:
        record = own(s, Record, tid, fact["id"])
        if not record.data.get("approved") or record.version != fact["version"]:
            fail("FACTS_CHANGED", "知识库资料已变更，请重新确认计划", 409)
    if publishing:
        if task.version_id:
            final = own(s, ContentVersion, tid, task.version_id)
            content = own(s, Content, tid, final.content_id)
            if content.current_version != final.version:
                fail("CONTENT_VERSION_CHANGED", "成品已修改，请为新版本重新盲评", 409)
        selected = next(a for a in run.snapshot["accounts"] if a["id"] == account.id)
        if not account.identity_key or account.identity_key != selected["identity_key"]:
            fail("IDENTITY_REQUIRED", "账号身份尚未验证或已改变", 409)
        if run.trial:
            fail("TRIAL_PUBLISH_FORBIDDEN", "试运行仅生成成品，不发布")
    return task, run, account


def observed_identity(s, tid, account, result):
    """Only connector-observed identities, never a user-entered verification flag."""
    ext = result.get("external_user_id")
    namespace = result.get("identity_namespace")
    if result.get("status") != "connected":
        account.status = result.get("status", "waiting_authorization")
        account.identity_key = None
    elif ext and namespace in ("public", "creator") and result.get("identity_verified") is True:
        key = account.platform + ":" + namespace + ":" + str(ext)
        duplicate = s.exec(query(s, SocialAccount, tid).where(SocialAccount.identity_key == key, SocialAccount.id != account.id)).first()
        if duplicate:
            fail("ACCOUNT_ALREADY_BOUND", "该平台账号已绑定，请使用已有账号", 409)
        if account.identity_key and account.identity_key != key:
            account.paused = True
            account.identity_key = None
            account.config = {**account.config, "identity_error": "检测到登录身份变化，请负责人重新核验"}
        else:
            account.identity_key = key
        account.status = "connected"
        account.config = {**account.config, "external_user_id": str(ext), "identity_namespace": namespace, "identity_checked_at": now().isoformat()}
    else:
        account.status = result.get("status", "waiting_authorization")
        account.identity_key = None
    s.add(account)


def charge(s, tid, task, request_id, resource, units, funding, shared=False, purpose="text"):
    from .worker import reserve_job, price
    tenant = lock_tenant(s, tid)
    prior = s.exec(query(s, MatrixCharge, tid).where(MatrixCharge.request_id == request_id, MatrixCharge.resource == resource)).first()
    if prior:
        return
    _, run, account = guard(s, tid, task.id)
    estimate = price(s, resource, units, tid, funding, purpose)
    local = now().astimezone(TZ)
    month, day = local.strftime("%Y-%m"), local.strftime("%Y-%m-%d")
    charges = s.exec(query(s, MatrixCharge, tid)).all()
    cost = lambda c: c.reserved_fen if c.state == "reserved" else c.actual_fen
    checks = [
        (int(tenant.settings.get("matrix_monthly_budget_fen", 0)), sum(cost(c) for c in charges if c.period == month)),
        (int(account.config.get("matrix", {}).get("monthly_budget_fen", 0)), sum(cost(c) for c in charges if c.period == month and c.account_id == account.id) if not shared else 0),
        (int(run.snapshot["spec"]["daily_budget_fen"]), sum(cost(c) for c in charges if c.day == day and c.plan_id == run.plan_id)),
        (int(run.snapshot["spec"]["run_budget_fen"]), sum(cost(c) for c in charges if c.run_id == run.id)),
    ]
    if any(limit <= 0 or used + estimate > limit for limit, used in checks):
        fail("MATRIX_BUDGET_EXCEEDED", "机构、账号、计划日预算或单次预算不足", 402)
    reserve_job(s, tid, request_id, resource, units, funding, purpose=purpose)
    s.add(MatrixCharge(tenant_id=tid, request_id=request_id, resource=resource, plan_id=run.plan_id, run_id=run.id, account_id="" if shared else account.id, profile_id=account.profile_id, reserved_fen=estimate, period=month, day=day))
    s.flush()


def sync_charges(s, tid):
    for c in s.exec(query(s, MatrixCharge, tid).where(MatrixCharge.state == "reserved")).all():
        u = s.exec(query(s, UsageRecord, tid).where(UsageRecord.request_id == c.request_id, UsageRecord.resource == c.resource)).first()
        if u and u.state == "settled":
            c.actual_fen = u.cost_fen
            c.state = "settled"
            s.add(c)


def cost_view(charges):
    return {"actual_fen": sum(c.actual_fen for c in charges if c.state == "settled"), "reserved_fen": sum(c.reserved_fen for c in charges if c.state == "reserved"), "shared": bool(charges) and all(not c.account_id for c in charges)}


def task_view(s, tid, task):
    steps = s.exec(query(s, AutomationStep, tid).where(AutomationStep.task_id == task.id)).all()
    charges = s.exec(query(s, MatrixCharge, tid).where(MatrixCharge.run_id == task.run_id)).all()
    rows = []
    for st in steps:
        model = MediaJob if st.key in ("image", "speech") or st.key.startswith("clip-") else AgentRun
        obj = s.exec(query(s, model, tid).where(model.id == st.object_id)).first() if st.object_id else None
        related = [c for c in charges if obj and obj.tenant_id == tid and c.request_id == obj.request_id]
        rows.append({**st.model_dump(mode="json"), "cost": cost_view(related)})
    return {**task.model_dump(mode="json"), "steps": rows, "cost": cost_view([c for c in charges if c.account_id == task.account_id])}


def run_view(s, run):
    tasks = s.exec(query(s, AutomationAccountTask, run.tenant_id).where(AutomationAccountTask.run_id == run.id)).all()
    charges = s.exec(query(s, MatrixCharge, run.tenant_id).where(MatrixCharge.run_id == run.id)).all()
    return {**run.model_dump(mode="json", exclude={"lease_token", "lease_until"}), "tasks": [task_view(s, run.tenant_id, t) for t in tasks], "cost": cost_view(charges), "shared_cost": cost_view([c for c in charges if not c.account_id])}


def next_slot(spec, after=None):
    current = (after or now()).astimezone(TZ)
    for offset in range(9):
        day = current.date() + timedelta(days=offset)
        if day.weekday() not in spec["weekdays"]:
            continue
        for t in sorted(set(spec["times"])):
            hh, mm = map(int, t.split(":"))
            slot = datetime.combine(day, datetime.min.time(), TZ).replace(hour=hh, minute=mm)
            if slot > current:
                return slot
    return None



def run_summary(s, run):
    tasks = s.exec(query(s, AutomationAccountTask, run.tenant_id).where(AutomationAccountTask.run_id == run.id)).all()
    return {**run.model_dump(mode="json", exclude={"snapshot", "lease_token", "lease_until"}), "snapshot": {"name": run.snapshot["name"], "profile": {"id": run.snapshot["profile"]["id"]}}, "tasks": [{k: getattr(t, k) for k in ("id", "account_id", "status", "stage", "version_id", "error")} for t in tasks]}



def budget_context(s, run, account):
    from .worker import price
    tenant = s.get(Tenant, run.tenant_id)
    local = now().astimezone(TZ)
    month, day = local.strftime("%Y-%m"), local.strftime("%Y-%m-%d")
    rows = s.exec(query(s, MatrixCharge, run.tenant_id)).all()
    cost = lambda c: c.reserved_fen if c.state == "reserved" else c.actual_fen
    remaining = [
        int(tenant.settings.get("matrix_monthly_budget_fen", 0))-sum(cost(c) for c in rows if c.period == month),
        int(account.config.get("matrix", {}).get("monthly_budget_fen", 0))-sum(cost(c) for c in rows if c.period == month and c.account_id == account.id),
        int(run.snapshot["spec"]["run_budget_fen"])-sum(cost(c) for c in rows if c.run_id == run.id),
        int(run.snapshot["spec"]["daily_budget_fen"])-sum(cost(c) for c in rows if c.day == day and c.plan_id == run.plan_id),
    ]
    cfg = s.get(PlatformSettings, 1)
    rates = cfg.plans.get("prices", {}) if cfg else {}
    return {"available_fen": max(0, min(remaining)), "prices": rates, "note": "金额单位分；还需预留盲评和复盘各20000Token。AIGC按每片段10秒计价；程序合成仍需配音。报价是配置单价估算。"}

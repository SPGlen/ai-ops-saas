import json, base64, secrets
from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import Field
from sqlmodel import select
from .models import *
from . import schemas as S
from .auth import Identity, scoped, current, require, writable
from .permissions import (
    Scope,
    permit,
    has,
    check_run,
    run_permission,
    check_asset,
    asset_allowed,
    check_job,
)
from .domain import *
from .security import fail, encrypt
from .worker import dispatch, reserve_job
from . import model_router
from .integrations.storage import Storage, save_asset, upload_mime
from .integrations import publishing, aliyun

router = APIRouter(prefix="/api/v1", tags=["智能体、内容与发布"])


class AccountInput(S.Strict):
    platform: S.Literal["xiaohongshu", "douyin", "channels"]
    name: str = Field(min_length=1, max_length=80)


def content_view(session, content):
    versions = session.exec(
        query(session, ContentVersion, content.tenant_id)
        .where(ContentVersion.content_id == content.id)
        .order_by(ContentVersion.version.desc())
    ).all()
    predictions = session.exec(
        query(session, Prediction, content.tenant_id).where(
            Prediction.version_id.in_([v.id for v in versions])
        )
    ).all()
    return {
        **content.model_dump(),
        "versions": [v.model_dump() for v in versions],
        "predictions": [p.model_dump() for p in predictions],
    }


@router.get("/contents")
def contents(i: Identity = Depends(scoped)):
    permit(i, "content.read")
    items = i.session.exec(
        query(i.session, Content, i.tenant.id)
        .order_by(Content.created_at.desc())
        .limit(100)
    ).all()
    return [content_view(i.session, c) for c in items]


@router.post("/contents", status_code=201)
def add_content(body: S.ContentInput, i: Identity = Depends(scoped)):
    permit(i, "content.write")
    writable(i)
    content, version = save_content(i.session, i.tenant.id, i.user.id, body)
    i.session.commit()
    return content_view(i.session, content)


@router.patch("/contents/{content_id}")
def edit_content(content_id: str, body: S.ContentInput, i: Identity = Depends(scoped)):
    permit(i, "content.write")
    writable(i)
    content, version = save_content(i.session, i.tenant.id, i.user.id, body, content_id)
    i.session.commit()
    return content_view(i.session, content)


@router.post("/runs", status_code=202, response_model=S.AgentRunView)
def new_run(body: S.RunInput, i: Identity = Depends(scoped)):
    if body.funding is None:
        body.funding = model_router.default_funding(i.session, i.tenant.id, body.kind)
    allowed = (
        {"owner", "operator"}
        if body.kind
        in ("content", "predict", "knowledge_index", "retro", "rubric_review")
        else (
            {"owner", "finance"}
            if body.kind == "ocr"
            else {"owner", "operator", "teacher"}
        )
    )
    permit(i, run_permission(body.kind))
    writable(i)
    if len(json.dumps(body.input)) > 50000:
        fail("INPUT_TOO_LARGE", "输入资料过长")
    prior = i.session.exec(
        query(i.session, AgentRun, i.tenant.id).where(
            AgentRun.request_id == body.request_id
        )
    ).first()
    if prior:
        if (
            prior.kind != body.kind
            or prior.input != body.input
            or prior.funding != body.funding
        ):
            fail("IDEMPOTENCY_CONFLICT", "请求编号已用于其他任务", 409)
        return prior
    if body.kind == "report_summary":
        own(i.session, ReportSnapshot, i.tenant.id, body.input.get("report_id", ""))
    if body.kind == "predict":
        own(i.session, ContentVersion, i.tenant.id, body.input.get("version_id", ""))
    if body.kind == "ocr":
        from .config import settings

        if not settings().ocr_enabled:
            fail("OCR_UNCONFIGURED", "尚未启用专用OCR Worker，请先完成部署配置", 503)
        asset = own(i.session, Asset, i.tenant.id, body.input.get("asset_id", ""))
        if "/receipt/" not in asset.object_key:
            fail("ASSET_PURPOSE_INVALID", "请上传财务票据素材")
    if body.kind == "feedback":
        Scope(i).own(body.input.get("feedback_id", ""), "feedback", "write")
    if body.kind == "retro":
        own(i.session, MetricSnapshot, i.tenant.id, body.input.get("metric_id", ""))
    if body.kind == "rubric_review":
        fail("RUBRIC_CANDIDATE_REQUIRED", "请从评分规则页面提交完整候选公式")
    reserve_job(
        i.session, i.tenant.id, body.request_id, "text_tokens", 20000, body.funding,
        purpose=model_router.purpose_for(body.kind),
    )
    run = AgentRun(
        tenant_id=i.tenant.id,
        kind=body.kind,
        request_id=body.request_id,
        actor_id=i.user.id,
        input=body.input,
        funding=body.funding,
    )
    i.session.add(run)
    i.session.commit()
    dispatch("ocr" if body.kind == "ocr" else "agent", i.tenant.id, run.id)
    return run


@router.get("/runs", response_model=list[S.AgentRunView])
def runs(i: Identity = Depends(scoped)):
    from fastapi import HTTPException

    rows = i.session.exec(
        query(i.session, AgentRun, i.tenant.id).order_by(AgentRun.created_at.desc())
    ).all()
    out = []
    for r in rows:
        try:
            check_run(i, r)
        except HTTPException:
            continue
        out.append({k: v for k, v in r.model_dump().items() if k != "input"})
        if len(out) >= 100:
            break
    return out


@router.get("/runs/{run_id}", response_model=S.AgentRunView)
def run_details(run_id: str, i: Identity = Depends(scoped)):
    row = own(i.session, AgentRun, i.tenant.id, run_id)
    check_run(i, row)
    return row


@router.post("/media-jobs", status_code=202, response_model=MediaJob)
def media_create(body: S.MediaInput, i: Identity = Depends(scoped)):
    if body.funding is None:
        body.funding = i.tenant.settings.get("funding", "platform")
    permit(i, "content.write")
    writable(i)
    old = i.session.exec(
        query(i.session, MediaJob, i.tenant.id).where(
            MediaJob.request_id == body.request_id
        )
    ).first()
    parameters = {
        "duration": body.duration,
        "ratio": body.ratio,
        "content_id": body.content_id,
        "narration": body.narration,
    }
    if old:
        if (
            old.kind != body.kind
            or old.prompt != body.prompt
            or any(old.parameters.get(k) != v for k, v in parameters.items())
            or old.funding != body.funding
        ):
            fail("IDEMPOTENCY_CONFLICT", "请求编号已用于其他媒体任务", 409)
        return old
    if body.content_id:
        own(i.session, Content, i.tenant.id, body.content_id)
    reserve_job(
        i.session,
        i.tenant.id,
        body.request_id,
        "images" if body.kind == "image" else "video_seconds",
        1 if body.kind == "image" else body.duration,
        body.funding,
    )
    if body.kind == "video" and body.narration:
        reserve_job(
            i.session,
            i.tenant.id,
            body.request_id + ":speech",
            "speech_characters",
            len(body.narration),
            body.funding,
        )
    job = MediaJob(
        tenant_id=i.tenant.id,
        kind=body.kind,
        prompt=body.prompt,
        request_id=body.request_id,
        actor_id=i.user.id,
        funding=body.funding,
        parameters=parameters,
    )
    i.session.add(job)
    i.session.commit()
    dispatch("media", i.tenant.id, job.id)
    return job


@router.get("/media-jobs", response_model=list[MediaJob])
def media_list(i: Identity = Depends(scoped)):
    permit(i, "content.read")
    rows = i.session.exec(
        query(i.session, MediaJob, i.tenant.id)
        .order_by(MediaJob.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            **j.model_dump(),
            "parameters": {
                k: v
                for k, v in j.parameters.items()
                if k not in ("result_urls", "audio_url", "result_url")
            },
        }
        for j in rows
    ]


@router.post("/jobs/{kind}/{job_id}/cancel")
def cancel(kind: str, job_id: str, i: Identity = Depends(scoped)):
    writable(i)
    model = {"agent": AgentRun, "media": MediaJob, "publish": PublishJob}.get(kind)
    if not model:
        fail("NOT_FOUND", "任务类型不存在", 404)
    obj = own(i.session, model, i.tenant.id, job_id)
    check_job(i, kind, obj)
    if (
        "owner" not in i.roles
        and not has(i, "content.write")
        and getattr(obj, "actor_id", None) != i.user.id
    ):
        fail("ROLE_FORBIDDEN", "只能取消自己发起的任务", 403)
    if kind == "media" and obj.provider_task_id:
        fail("CANCEL_NOT_SAFE", "已提交供应商的视频需要先核实结果")
    if obj.status not in (
        "retrying",
        "queued",
        "scheduled",
        "waiting_authorization",
        "failed",
    ):
        fail("CANCEL_NOT_SAFE", "任务已提交供应商或结果待核实，不能直接撤销")
    obj.status = "cancelled"
    if kind != "publish":
        release_reservations(i.session, i.tenant.id, obj.request_id)
        if kind == "media":
            release_reservations(i.session, i.tenant.id, obj.request_id + ":speech")
    i.session.add(obj)
    i.session.commit()
    return {"status": "cancelled"}


@router.get("/assets")
def assets(purpose: str = "content", i: Identity = Depends(scoped)):
    rows = i.session.exec(
        query(i.session, Asset, i.tenant.id)
        .order_by(Asset.created_at.desc())
        .limit(200)
    ).all()
    if purpose not in ("content", "receipt", "document"):
        fail("PURPOSE_INVALID", "素材用途无效")
    return [
        a for a in rows if "/" + purpose + "/" in a.object_key and asset_allowed(i, a)
    ]


@router.post("/assets", status_code=201)
async def upload(
    file: UploadFile = File(...),
    consent: bool = Form(False),
    purpose: str = Form("content"),
    i: Identity = Depends(scoped),
):
    if not any(
        has(i, p)
        for p in (
            "content.write",
            "finance.write",
            "feedback.write",
            "knowledge.write",
            "lead.write",
            "student.write",
        )
    ):
        fail("ROLE_FORBIDDEN", "当前岗位无法上传附件", 403)
    writable(i)
    if purpose == "receipt":
        permit(i, "finance.write")
    if purpose == "content":
        permit(i, "content.write")
    from .config import settings

    raw = await file.read(settings().max_upload_mb * 1024 * 1024 + 1)
    if len(raw) > settings().max_upload_mb * 1024 * 1024:
        fail("FILE_TOO_LARGE", "文件过大")
    mime = upload_mime(raw, file.filename or "file")
    asset = save_asset(
        i.session, i.tenant.id, file.filename or "file", raw, mime, consent, purpose
    )
    asset.uploaded_by = i.user.id
    i.session.add(asset)
    audit(i.session, i.tenant.id, i.user.id, "asset.upload", asset.id, purpose=purpose)
    i.session.commit()
    return asset


@router.get("/assets/{asset_id}/download")
def download(asset_id: str, i: Identity = Depends(scoped)):
    asset = own(i.session, Asset, i.tenant.id, asset_id)
    check_asset(i, asset)
    return Response(
        Storage().read(asset.object_key),
        media_type=asset.mime,
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/integrations")
def integrations(i: Identity = Depends(scoped)):
    permit(i, "integration.manage")
    rows = i.session.exec(query(i.session, Integration, i.tenant.id)).all()
    return [
        {
            "provider": r.provider,
            "active": r.active,
            "configured": bool(r.secret_cipher),
            "config": r.config,
        }
        for r in rows
    ]


@router.put("/integrations/{provider}")
def set_integration(provider: str, body: S.SecretInput, i: Identity = Depends(scoped)):
    permit(i, "integration.manage")
    writable(i)
    if provider not in ("aliyun", "deepseek", "wecom"):
        fail("PROVIDER_UNSUPPORTED", "不支持的供应商")
    config = dict(body.config)
    secret = body.secret
    if provider == "wecom":
        required = ("corpid", "token", "encoding_aes_key", "open_kfid")
        if not all(config.get(k) for k in required):
            fail(
                "WECOM_CONFIG_INVALID", "需要企业ID、Token、EncodingAESKey和客服账号ID"
            )
        secret = {
            "secret": body.secret,
            "token": config.pop("token"),
            "encoding_aes_key": config.pop("encoding_aes_key"),
        }
        config = {k: config[k] for k in ("corpid", "open_kfid") if k in config}
    elif provider == "deepseek":
        if config:
            fail("MODEL_CONFIG_INVALID", "DeepSeek 使用固定官方地址，模型请在 AI 配置中选择")
    else:
        config = {
            k: config[k]
            for k in ("base_url", "text_base_url")
            if k in config and config[k]
        }
        for field in ("base_url", "text_base_url"):
            if not config.get(field):
                continue
            from urllib.parse import urlparse

            host = urlparse(config[field]).hostname or ""
            if not config[field].startswith("https://") or not (
                host in ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com")
                or host.endswith(".maas.aliyuncs.com")
            ):
                fail("MODEL_HOST_INVALID", "请使用百炼官方地域域名")
    old = i.session.exec(
        query(i.session, Integration, i.tenant.id).where(
            Integration.provider == provider
        )
    ).first()
    integration = old or Integration(tenant_id=i.tenant.id, provider=provider)
    integration.secret_cipher = encrypt(i.tenant.id, secret)
    integration.config = config
    integration.active = True
    i.session.add(integration)
    audit(
        i.session,
        i.tenant.id,
        i.user.id,
        "integration.replace",
        integration.id,
        provider=provider,
    )
    i.session.commit()
    return {"configured": True}


@router.delete("/integrations/{provider}")
def revoke(provider: str, i: Identity = Depends(current)):
    permit(i, "integration.manage")
    row = i.session.exec(
        query(i.session, Integration, i.tenant.id).where(
            Integration.provider == provider
        )
    ).first()
    if row:
        row.active = False
        row.secret_cipher = ""
        i.session.add(row)
        i.session.commit()
    return {"message": "凭证已撤销"}


class AISettingsView(S.Strict):
    settings: model_router.TextModelSettings
    credential_configured: bool
    endpoint: str
    media_provider: str = "aliyun"


def ai_configuration(i):
    cfg = model_router.configuration(i.session, i.tenant.id)
    try:
        model_router.credentials(i.session, i.tenant.id, cfg.funding, {"provider": cfg.provider})
        configured = True
    except __import__("fastapi").HTTPException:
        configured = False
    return {"settings": cfg, "credential_configured": configured,
            "endpoint": "https://api.deepseek.com" if cfg.provider == "deepseek" else "百炼官方地域地址"}


@router.get("/ai-settings", response_model=AISettingsView)
def ai_settings(i: Identity = Depends(scoped)):
    permit(i, "integration.manage")
    return ai_configuration(i)


@router.put("/ai-settings", response_model=AISettingsView)
def update_ai_settings(body: model_router.TextModelSettings, i: Identity = Depends(scoped)):
    permit(i, "integration.manage")
    writable(i)
    if body.provider == "deepseek":
        if body.model not in model_router.DEEPSEEK_MODELS:
            fail("MODEL_UNSUPPORTED", "请选择已接通的 DeepSeek 模型")
        if min(body.input_million_fen, body.output_million_fen) <= 0 or body.cached_million_fen > body.input_million_fen:
            fail("PRICE_UNCONFIGURED", "输入和输出单价须大于0，缓存单价不得高于输入单价")
    else:
        body.model = __import__("app.config", fromlist=["settings"]).settings().text_model
    i.tenant.settings = {**i.tenant.settings, "ai_text": body.model_dump()}
    i.session.add(i.tenant)
    audit(i.session, i.tenant.id, i.user.id, "ai.settings", i.tenant.id,
          provider=body.provider, model=body.model, funding=body.funding)
    i.session.commit()
    return ai_configuration(i)


class ConnectionTestInput(S.Strict):
    request_id: str = Field(min_length=8, max_length=100)


@router.post("/ai-settings/test", status_code=202, response_model=S.AgentRunView)
def test_ai_connection(body: ConnectionTestInput, i: Identity = Depends(scoped)):
    permit(i, "integration.manage")
    writable(i)
    previous = i.session.exec(query(i.session, AgentRun, i.tenant.id).where(AgentRun.request_id == body.request_id)).first()
    if previous:
        if previous.kind != "connection_test":
            fail("IDEMPOTENCY_CONFLICT", "请求编号已用于其他任务", 409)
        return previous
    from .security import limit
    limit(i.session, "model-probe:" + i.tenant.id, 5)
    funding = model_router.configuration(i.session, i.tenant.id).funding
    reserve_job(i.session, i.tenant.id, body.request_id, "text_tokens", 20000, funding)
    row = AgentRun(tenant_id=i.tenant.id, kind="connection_test", request_id=body.request_id, actor_id=i.user.id, funding=funding)
    i.session.add(row)
    i.session.commit()
    dispatch("agent", i.tenant.id, row.id)
    return row


@router.get("/social-accounts")
def accounts(i: Identity = Depends(scoped)):
    permit(i, "social.read")
    return i.session.exec(query(i.session, SocialAccount, i.tenant.id)).all()


@router.post("/social-accounts")
def account_add(body: AccountInput, i: Identity = Depends(scoped)):
    permit(i, "social.manage")
    writable(i)
    count = len(i.session.exec(query(i.session, SocialAccount, i.tenant.id)).all())
    from .matrix import account_limit, lock_tenant
    tenant = lock_tenant(i.session, i.tenant.id)
    count = len(i.session.exec(query(i.session, SocialAccount, tenant.id)).all())
    if count >= account_limit(i.session, tenant):
        fail("ACCOUNT_LIMIT", "已达到机构套餐的账号数量上限")
    account = SocialAccount(
        tenant_id=i.tenant.id, platform=body.platform, name=body.name
    )
    i.session.add(account)
    i.session.commit()
    return account


@router.post("/social-accounts/{account_id}/{operation}")
def account_action(account_id: str, operation: str, i: Identity = Depends(scoped)):
    permit(i, "social.manage")
    writable(i)
    account = own(i.session, SocialAccount, i.tenant.id, account_id)
    if operation == "login":
        result = publishing.start_login(i.tenant.id, account)
    elif operation == "login-image":
        return publishing.login_image(i.tenant.id, account)
    elif operation == "status":
        result = publishing.check_login(i.tenant.id, account)
    else:
        fail("OPERATION_INVALID", "不支持的操作")
    from .matrix import observed_identity
    observed_identity(i.session, i.tenant.id, account, result)
    i.session.commit()
    return result


@router.post("/contents/{content_id}/publish", status_code=202)
def publish_content(
    content_id: str, body: S.PublishInput, i: Identity = Depends(scoped)
):
    permit(i, "publish.write")
    writable(i)
    content = own(i.session, Content, i.tenant.id, content_id)
    account = own(i.session, SocialAccount, i.tenant.id, body.account_id)
    version = i.session.exec(
        query(i.session, ContentVersion, i.tenant.id).where(
            ContentVersion.content_id == content.id,
            ContentVersion.version == content.current_version,
        )
    ).one()
    prediction = i.session.exec(
        query(i.session, Prediction, i.tenant.id).where(
            Prediction.version_id == version.id
        )
    ).first()
    if not prediction:
        fail("PREDICTION_REQUIRED", "请先完成当前成品版本的盲预测")
    if not version.policy_checked:
        fail("CONTENT_REVIEW_REQUIRED", "请处理内容检查提示")
    if not version.assets:
        fail("ASSET_REQUIRED", "请先生成或上传素材")
    prior = i.session.exec(
        query(i.session, PublishJob, i.tenant.id).where(
            PublishJob.version_id == version.id, PublishJob.account_id == account.id
        )
    ).first()
    if prior:
        return prior
    date = as_utc(body.scheduled_at)
    job = PublishJob(
        tenant_id=i.tenant.id,
        version_id=version.id,
        account_id=account.id,
        request_id=body.request_id,
        actor_id=i.user.id,
        scheduled_at=date,
    )
    i.session.add(job)
    i.session.commit()
    if date <= now():
        dispatch("publish", i.tenant.id, job.id)
    return job


@router.get("/publish-jobs", response_model=list[PublishJob])
def publish_jobs(i: Identity = Depends(scoped)):
    permit(i, "publish.read")
    return i.session.exec(
        query(i.session, PublishJob, i.tenant.id)
        .order_by(PublishJob.scheduled_at.desc())
        .limit(200)
    ).all()


@router.post("/publish-jobs/{job_id}/reconcile")
def reconcile(job_id: str, i: Identity = Depends(scoped)):
    permit(i, "publish.read")
    writable(i)
    job = own(i.session, PublishJob, i.tenant.id, job_id)
    account = own(i.session, SocialAccount, i.tenant.id, job.account_id)
    result = publishing.query_result(i.tenant.id, account, job)
    if (
        result.get("status") == "succeeded"
        and result.get("external_id")
        and result.get("external_url")
    ):
        was_confirmed = job.status == "succeeded"
        job.status = "succeeded"
        job.external_id = result["external_id"]
        job.external_url = result["external_url"]
        if not was_confirmed:
            job.retro_due_at = now() + __import__("datetime").timedelta(days=3)
        version = own(i.session, ContentVersion, i.tenant.id, job.version_id)
        content = own(i.session, Content, i.tenant.id, version.content_id)
        key = "publish_video" if content.form == "video" else "publish_image"
        account.config = {**account.config, "inflight_publish_id": None, "verified_capabilities": {**account.config.get("verified_capabilities", {}), key: True}}
        i.session.add(account)
        i.session.add(job)
        i.session.commit()
    return {"job": job, "result": result}


@router.get("/metrics")
def metrics(i: Identity = Depends(scoped)):
    permit(i, "publish.read")
    return i.session.exec(
        query(i.session, MetricSnapshot, i.tenant.id)
        .order_by(MetricSnapshot.created_at.desc())
        .limit(200)
    ).all()


@router.post("/publish-jobs/{job_id}/metrics")
def add_metric(job_id: str, body: S.MetricInput, i: Identity = Depends(scoped)):
    permit(i, "publish.write")
    writable(i)
    job = own(i.session, PublishJob, i.tenant.id, job_id)
    if job.status != "succeeded":
        fail("NOT_PUBLISHED", "请先核实发布结果")
    snapshot = MetricSnapshot(
        tenant_id=i.tenant.id,
        publish_job_id=job.id,
        metrics=body.model_dump(),
        source="manual",
        eligible=bool(
            job.submitted_at
            and job.submitted_at <= now() - __import__("datetime").timedelta(days=3)
        ),
    )
    i.session.add(snapshot)
    i.session.commit()
    return snapshot


class RubricInput(S.Strict):
    profile_id: str | None = None
    form: S.Literal["image_text", "video"]
    weights: dict[str, int]
    notes: str = Field(min_length=20, max_length=3000)
    funding: S.Literal["platform", "byok"] = "platform"
    request_id: str = Field(min_length=8, max_length=100)


@router.get("/rubrics")
def rubrics(i: Identity = Depends(scoped), profile_id: str | None = None):
    permit(i, "content.read")
    from .rubrics import rubric

    return {
        "active": {
            f: rubric(i.session, i.tenant.id, f, profile_id) for f in ("image_text", "video")
        },
        "candidates": i.session.exec(
            query(i.session, RubricCandidate, i.tenant.id).where(RubricCandidate.profile_id == profile_id).order_by(
                RubricCandidate.created_at.desc()
            )
        ).all(),
    }


@router.post("/rubrics", status_code=202)
def propose_rubric(body: RubricInput, i: Identity = Depends(scoped)):
    permit(i, "rubric.manage")
    writable(i)
    from .rubrics import DIMENSIONS, corpus

    if set(body.weights) != set(DIMENSIONS) or any(
        x < 1 or x > 10 for x in body.weights.values()
    ):
        fail("WEIGHTS_INVALID", "七个维度的权重均需为1至10")
    prior = i.session.exec(
        query(i.session, AgentRun, i.tenant.id).where(
            AgentRun.request_id == body.request_id
        )
    ).first()
    if prior:
        candidate = own(
            i.session, RubricCandidate, i.tenant.id, prior.input.get("candidate_id", "")
        )
        if (
            candidate.profile_id != body.profile_id
            or candidate.form != body.form
            or candidate.weights != body.weights
            or candidate.notes != body.notes
            or prior.funding != body.funding
        ):
            fail("IDEMPOTENCY_CONFLICT", "请求参数不同", 409)
        return candidate
    versions, metrics, checksum = corpus(i.session, i.tenant.id, body.form, body.profile_id)
    if len(versions) < 5 or len(metrics) < 5:
        fail(
            "CALIBRATION_SAMPLES_REQUIRED",
            "规则升级至少需要5个成品版本和5条T+3实绩样本",
        )
    if len(versions) > 100:
        fail("CORPUS_TOO_LARGE", "请联系管理员安排大规模离线重算")
    reserve_job(
        i.session,
        i.tenant.id,
        body.request_id,
        "text_tokens",
        20000 * (len(versions) + 1),
        body.funding,
        purpose="review",
    )
    candidate = RubricCandidate(
        tenant_id=i.tenant.id,
        form=body.form,
        profile_id=body.profile_id,
        weights=body.weights,
        notes=body.notes,
        corpus_hash=checksum,
    )
    i.session.add(candidate)
    i.session.flush()
    run = AgentRun(
        tenant_id=i.tenant.id,
        kind="rubric_review",
        request_id=body.request_id,
        actor_id=i.user.id,
        funding=body.funding,
        input={"candidate_id": candidate.id},
    )
    i.session.add(run)
    i.session.commit()
    dispatch("agent", i.tenant.id, run.id)
    return candidate


@router.post("/rubrics/{candidate_id}/activate")
def activate_rubric(candidate_id: str, i: Identity = Depends(scoped)):
    permit(i, "rubric.manage")
    writable(i)
    from .rubrics import corpus

    candidate = own(i.session, RubricCandidate, i.tenant.id, candidate_id)
    versions, metrics, checksum = corpus(i.session, i.tenant.id, candidate.form, candidate.profile_id)
    if candidate.status != "reviewed" or checksum != candidate.corpus_hash:
        fail("RUBRIC_NOT_READY", "需先通过当前完整样本集重算与独立模型复核")
    if candidate.profile_id:
        profile = own(i.session, MediaProfile, i.tenant.id, candidate.profile_id)
        profile.rubrics = {**profile.rubrics, candidate.form: candidate.id}
        profile.version += 1
        i.session.add(profile)
        from .routes_matrix import disable_plans
        disable_plans(i.session, i.tenant.id, profile.id)
    else:
        i.tenant.settings = {**i.tenant.settings, "rubrics": {**i.tenant.settings.get("rubrics", {}), candidate.form: candidate.id}}
    audit(i.session, i.tenant.id, i.user.id, "rubric.activate", candidate.id)
    i.session.add(i.tenant)
    i.session.commit()
    return {"active": candidate.id}


@router.post("/publish-jobs/{job_id}/retry")
def retry_publish(job_id: str, i: Identity = Depends(scoped)):
    permit(i, "publish.write")
    writable(i)
    job = own(i.session, PublishJob, i.tenant.id, job_id)
    if job.submitted_at or job.status not in ("failed", "waiting_authorization"):
        fail("RETRY_NOT_SAFE", "只有尚未提交平台的任务可以重试；其余请先核实")
    job.status = "scheduled"
    job.scheduled_at = now()
    job.error = ""
    job.error_code = ""
    i.session.add(job)
    audit(i.session, i.tenant.id, i.user.id, "publish.retry_preflight", job.id)
    i.session.commit()
    dispatch("publish", i.tenant.id, job.id)
    return job


@router.post("/media-jobs/{job_id}/resume")
def resume_media(job_id: str, i: Identity = Depends(scoped)):
    permit(i, "content.write")
    writable(i)
    job = own(i.session, MediaJob, i.tenant.id, job_id)
    if job.status not in ("failed", "unknown", "waiting_authorization"):
        fail("NOT_RESUMABLE", "任务正在执行或已经结束")
    if job.parameters.get("voice_state") == "submitting" and not job.parameters.get(
        "audio_url"
    ):
        fail("RESUME_NOT_SAFE", "配音结果未知，需要先向供应商核实，不能重复创建")
    if job.kind == "speech" and job.parameters.get("result_url"):
        job.status = "finishing"
    elif job.provider_task_id:
        job.status = "polling"
    elif job.parameters.get("result_urls") and not job.parameters.get("raw_assets"):
        job.status = "queued"
    elif (
        job.parameters.get("raw_assets")
        and job.parameters.get("voice_state") != "submitting"
    ):
        job.status = "finishing"
    else:
        fail("RESUME_NOT_SAFE", "缺少明确的供应商结果，不能自动重新创建付费任务")
    job.error = ""
    job.error_code = ""
    job.updated_at = now()
    i.session.add(job)
    audit(i.session, i.tenant.id, i.user.id, "media.resume_existing", job.id)
    i.session.commit()
    dispatch("media", i.tenant.id, job.id)
    return job


@router.get("/contents/{content_id}")
def content_detail(content_id: str, i: Identity = Depends(scoped)):
    permit(i, "content.read")
    return content_view(i.session, own(i.session, Content, i.tenant.id, content_id))

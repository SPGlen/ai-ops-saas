from .permissions import identity_for, permit, check_run, run_permission
import json, math, base64, hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, datetime
from fastapi import HTTPException
from sqlalchemy import update
from sqlmodel import Session, select
from celery import Celery
from .config import settings
from .db import engine, set_scope
from .models import *
from .domain import *
from .security import fail, redact_error
from .auth import entitlement
from .schemas import ContentInput, Expense
from .agents import *
from .integrations import aliyun, publishing
from .integrations.storage import save_asset, Storage, download_result

celery = Celery("care_ops", broker=settings().broker_url)
celery.conf.update(
    task_default_queue="ops",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={"tick": {"task": "ops.tick", "schedule": 15.0}},
)
pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ops-worker")


def dispatch(kind, tenant_id, object_id):
    if settings().task_mode == "celery":
        celery.send_task(
            "ops.execute",
            args=["agent" if kind == "ocr" else kind, tenant_id, object_id],
            queue="ocr" if kind == "ocr" else "ops",
        )
    elif settings().task_mode == "local":
        pool.submit(execute, "agent" if kind == "ocr" else kind, tenant_id, object_id)


def price(session, resource, units, tenant_id=None, funding="platform", purpose="text"):
    if resource == "text_tokens" and tenant_id:
        from .model_router import snapshot
        route = snapshot(session, tenant_id, funding, purpose)
        if route["provider"] == "deepseek":
            return math.ceil(units * max(route["rates"].values()) / 1000000)
    cfg = session.get(PlatformSettings, 1)
    prices = cfg.plans.get("prices", {}) if cfg else {}
    key = {
        "text_tokens": "text_million_fen",
        "images": "image_fen",
        "video_seconds": "video_second_fen",
        "speech_characters": "speech_thousand_fen",
    }[resource]
    rate = int(prices.get(key, 0))
    if rate <= 0:
        fail(
            "PRICE_UNCONFIGURED",
            "平台尚未配置模型计价参数，请先配置或使用自带 Key",
            503,
        )
    return math.ceil(
        units
        * rate
        / (
            1000000
            if resource == "text_tokens"
            else 1000
            if resource == "speech_characters"
            else 1
        )
    )


def reserve_job(session, tenant_id, request_id, resource, units, funding, purpose="text"):
    from .model_router import reservation, credentials
    route = reservation(session, tenant_id, request_id, funding, purpose) if resource == "text_tokens" else None
    if route:
        credentials(session, tenant_id, funding, route)
    else:
        aliyun.config(session, tenant_id, funding)
    usage = reserve(session, tenant_id, request_id, resource, units, funding)
    cfg = session.get(PlatformSettings, 1)
    key = {
        "text_tokens": "text_million_fen",
        "images": "image_fen",
        "video_seconds": "video_second_fen",
        "speech_characters": "speech_thousand_fen",
    }[resource]
    if not usage.unit_rate_fen:
        usage.unit_rate_fen = int(
            (cfg.plans.get("prices", {}) if cfg else {}).get(key, 0)
        )
        usage.unit_scale = (
            1000000
            if resource == "text_tokens"
            else 1000
            if resource == "speech_characters"
            else 1
        )
        session.add(usage)
    if route and not usage.model_usage:
        usage.model_usage = {"route": route, "calls": []}
        if route["provider"] == "deepseek":
            usage.unit_rate_fen = max(route["rates"].values())
            usage.unit_scale = 1000000
        session.add(usage)
    estimated = math.ceil(units * usage.unit_rate_fen / usage.unit_scale)
    if funding == "platform" and usage.unit_rate_fen <= 0:
        fail(
            "PRICE_UNCONFIGURED",
            "Model prices must be configured before using platform quota",
            503,
        )
    if funding == "platform":
        reserve(session, tenant_id, request_id, "cost_fen", estimated, funding)
    return estimated


def finish_usage(session, tenant_id, request_id, resource, actual, funding):
    if actual is None:
        return
    usage = session.exec(
        query(session, UsageRecord, tenant_id).where(
            UsageRecord.request_id == request_id, UsageRecord.resource == resource
        )
    ).first()
    from .model_router import actual_cost
    cost = actual_cost(usage, actual) if usage and actual else 0
    settle(session, tenant_id, request_id, resource, actual, cost)
    if funding == "platform":
        settle(session, tenant_id, request_id, "cost_fen", cost)
    from .matrix import sync_charges
    sync_charges(session, tenant_id)


def agent_call(session, tenant_id, run, instructions, prompt, output_type, **kwargs):
    from .model_router import reservation, credentials, purpose_for
    kind = getattr(run, "kind", "chat")
    route = reservation(session, tenant_id, run.request_id, run.funding, purpose_for(kind))
    recorded = False

    def meter(used, stats=None):
        nonlocal recorded
        record_consumption(session, tenant_id, run.request_id, "text_tokens", used, additive=True)
        usage = session.exec(query(session, UsageRecord, tenant_id).where(
            UsageRecord.request_id == run.request_id, UsageRecord.resource == "text_tokens")).first()
        if usage:
            meta = dict(usage.model_usage or {})
            meta.setdefault("route", route)
            meta["calls"] = [*meta.get("calls", []), stats or {"provider": "aliyun", "model": kwargs.get("model_name", route["model"]), "total_tokens": used, "metered": used is not None}]
            usage.model_usage = meta
            session.add(usage)
        session.commit()
        recorded = True

    if route["provider"] == "deepseek":
        from .integrations import deepseek
        if kwargs.get("media") or kwargs.get("model_name"):
            fail("MODEL_ROUTE_MISMATCH", "视觉评分和独立复核使用各自固定模型")
        key = credentials(session, tenant_id, run.funding, route)
        probe_route = {**route, "thinking": False, "max_tokens": 256} if kind == "connection_test" else route
        output, used = deepseek.text_agent(key, probe_route, instructions, prompt, output_type, meter)
    else:
        kwargs["model_name"] = (route.get("score_model", settings().score_model) if kwargs.get("media") else route.get("review_model", route["model"])) if kind == "rubric_review" else route["model"]
        output, used = aliyun.text_agent(session, tenant_id, run.funding, instructions, prompt, output_type, **kwargs)
    if not recorded:
        meter(used)
    return output, used if used is not None else 20000


def authorize_actor(session, tenant_id, actor_id, roles, permission=None):
    tenant = session.get(Tenant, tenant_id)
    if not tenant or not entitlement(session, tenant)["active"]:
        fail("ENTITLEMENT_EXPIRED", "使用期已结束", 402)
    if actor_id in ("public", "webhook"):
        return tenant
    if actor_id == "scheduler":
        if not tenant.settings.get("publishing_enabled") or not tenant.settings.get(
            "auto_publish"
        ):
            fail("ROLE_REVOKED", "机构自动化授权已撤销", 403)
        return tenant
    i = identity_for(session, tenant, actor_id)
    if permission is None:
        permission = (
            "finance.write"
            if "finance" in roles
            else "feedback.write"
            if "teacher" in roles
            else "content.write"
        )
    from .permissions import has

    if not has(i, permission):
        fail("ROLE_REVOKED", "任务发起人的权限已失效", 403)
    return tenant


def claim(session, model, tenant_id, object_id, states):
    obj = own(session, model, tenant_id, object_id)
    old = obj.status
    if old not in states:
        return None
    changed = session.exec(
        update(model)
        .where(model.id == object_id, model.tenant_id == tenant_id, model.status == old)
        .values(status="processing", updated_at=now())
    )
    session.commit()
    if changed.rowcount != 1:
        return None
    session.expire_all()
    return own(session, model, tenant_id, object_id)


@celery.task(name="ops.execute")
def execute(kind, tenant_id, object_id):
    with Session(engine(), expire_on_commit=False) as session:
        set_scope(session, tenant_id)
        model = {"agent": AgentRun, "media": MediaJob, "publish": PublishJob}.get(kind)
        if not model:
            return
        try:
            if kind == "agent":
                process_agent(session, tenant_id, object_id)
            elif kind == "media":
                process_media(session, tenant_id, object_id)
            else:
                process_publish(session, tenant_id, object_id)
        except Exception as error:
            session.rollback()
            obj = own(session, model, tenant_id, object_id)
            detail = (
                error.detail
                if isinstance(error, HTTPException) and isinstance(error.detail, dict)
                else {}
            )
            code = detail.get("code", "EXECUTION_ERROR")
            if getattr(error, "status_code", None) == 429:
                code = "MODEL_RATE_LIMITED"
            if (code == "MODEL_RATE_LIMITED" and kind != "publish") or (
                kind == "agent"
                and obj.kind == "wecom_event"
                and code not in ("WECOM_AUTH_FAILED", "WECOM_UNCONFIGURED")
            ):
                retry_data = dict(obj.parameters if kind == "media" else obj.output)
                count = retry_data.get("_retry_count", 0) + 1
                retry_data["_retry_count"] = count
                if kind == "media":
                    obj.parameters = retry_data
                else:
                    obj.output = retry_data
                if count <= 4:
                    obj.status = "retrying"
                    obj.error_code = code
                    obj.error = "供应商限流，保留预占额度并等待重试"
                    obj.updated_at = now() + timedelta(seconds=30 * 2**count)
                    session.add(obj)
                    session.commit()
                    return
            unknown = not isinstance(error, HTTPException)
            if kind == "publish":
                unknown = bool(obj.submitted_at)
            if kind == "media" and obj.status == "submitting":
                unknown = True
            if code in (
                "MODEL_RATE_LIMITED",
                "MODEL_REQUEST_REJECTED",
                "MODEL_KEY_REJECTED",
            ):
                unknown = False
            if (
                kind == "media"
                and obj.provider_task_id
                and code == "MODEL_KEY_REJECTED"
            ):
                code = "KEY_REQUIRED"
            obj.status = (
                "unknown"
                if unknown
                else (
                    "waiting_authorization"
                    if code
                    in (
                        "KEY_REQUIRED",
                        "MODEL_UNCONFIGURED",
                        "PUBLISHER_UNCONFIGURED",
                        "LIVE_PUBLISH_DISABLED",
                        "LOGIN_REQUIRED",
                    )
                    else "failed"
                )
            )
            obj.error_code = code
            obj.error = (
                detail.get("message", "执行异常，已保留任务以便核实")
                if unknown
                else detail.get("message", redact_error(error))
            )
            obj.updated_at = now()
            session.add(obj)
            if kind == "agent" and obj.kind == "chat":
                conversation = own(
                    session, Conversation, tenant_id, obj.input["conversation_id"]
                )
                if conversation.state == "bot":
                    conversation.state = "waiting_human"
                    session.add(conversation)
            if not unknown and kind != "publish":
                if (
                    kind != "media"
                    or not obj.provider_task_id
                    or code == "MEDIA_PROVIDER_FAILED"
                ):
                    release_reservations(session, tenant_id, obj.request_id)
                    if kind == "media":
                        release_reservations(
                            session, tenant_id, obj.request_id + ":speech"
                        )
            audit(session, tenant_id, "worker", "job." + obj.status, obj.id, code=code)
            session.commit()


def process_agent(session, tenant_id, run_id):
    candidate = own(session, AgentRun, tenant_id, run_id)
    if candidate.request_id.startswith("campaign:") and candidate.status == "queued":
        candidate.status = "cancelled"
        candidate.error_code = "LEGACY_CAMPAIGN_PAUSED"
        candidate.error = "旧计划已暂停，请在矩阵中心确认明确账号和预算"
        release_reservations(session, tenant_id, candidate.request_id)
        session.add(candidate)
        session.commit()
        return
    if candidate.input.get("_matrix_task_id"):
        from .matrix_execution import may_start
        if not may_start(session, tenant_id, candidate.input["_matrix_task_id"]):
            return
    run = claim(session, AgentRun, tenant_id, run_id, ("queued",))
    if not run:
        return
    roles = (
        {"owner", "finance"}
        if run.kind == "ocr"
        else {"owner", "operator", "teacher"}
        if run.kind == "feedback"
        else {"owner", "operator"}
    )
    tenant = authorize_actor(
        session, tenant_id, run.actor_id, roles, run_permission(run.kind)
    )
    if run.kind in ("chat", "wecom_event"):
        from .operations import consultation

        consultation(tenant)
    if run.kind == "feedback" and not tenant.settings.get("legacy_maintenance", False):
        fail("FEATURE_RETIRED", "课返内容生成已停用")
    if run.actor_id not in ("public", "webhook", "scheduler"):
        check_run(identity_for(session, tenant, run.actor_id), run)
    if run.kind == "wecom_event":
        from .integrations.wecom import sync_messages

        sync_messages(session, tenant_id, run.input)
        run.output = {"synced": True}
    else:
        if run.kind == "connection_test":
            output, used = agent_call(session, tenant_id, run, "仅返回连接测试 JSON，不访问任何业务资料。", "返回 {\"ok\": true}", ConnectionProbe)
            run.output = {**output.model_dump(), "message": "模型调用及结构化输出验证通过"}
        elif run.kind == "report_summary":
            report = own(session, ReportSnapshot, tenant_id, run.input["report_id"])
            output, used = agent_call(session, tenant_id, run,
                "只依据给出的经营汇总数据解释周报或月报。金额单位分；缺失或待校准的指标明确说明，不编造精确数字，不直接修改账务，不把相关性当因果。",
                json.dumps(report_model_input(report), ensure_ascii=False), ReportAnalysis)
            run.output = {**output.model_dump(), "report_id": report.id, "report_version": report.version}
        elif run.kind in ("matrix_topic", "matrix_content"):
            from .matrix_execution import agent
            run.output, used = agent(session, tenant_id, run)
        elif run.kind == "content":
            sources = knowledge(session, tenant_id, run.input.get("topic", ""))
            if not sources:
                fail("KNOWLEDGE_REQUIRED", "请先发布机构课程知识库")
            prompt = json.dumps(
                {
                    "topic": str(run.input.get("topic", ""))[:3000],
                    "form": run.input.get("form", "image_text"),
                    "brand": tenant.settings.get("brand", tenant.name),
                    "audience": tenant.settings.get("audience", "小学家长"),
                    "sources": sources,
                },
                ensure_ascii=False,
            )
            output, used = agent_call(
                session, tenant_id, run, CONTENT_INSTRUCTIONS, prompt, ContentDraft
            )
            allowed = {s["id"] for s in sources}
            if not output.source_ids or not set(output.source_ids) <= allowed:
                fail("SOURCE_INVALID", "生成内容缺少可靠课程来源")
            content, version = save_content(
                session,
                tenant_id,
                run.actor_id,
                ContentInput(
                    title=output.title,
                    body=output.body,
                    form=run.input.get("form", "image_text"),
                ),
            )
            run.output = {
                **output.model_dump(),
                "content_id": content.id,
                "version_id": version.id,
            }
        elif run.kind == "predict":
            data = blind_input(session, tenant_id, run.input["version_id"])
            previous = session.exec(
                query(session, Prediction, tenant_id).where(
                    Prediction.version_id == run.input["version_id"]
                )
            ).first()
            if previous:
                run.output = previous.payload
                run.status = "succeeded"
                release_reservations(session, tenant_id, run.request_id)
                session.add(run)
                session.commit()
                return
            version = own(session, ContentVersion, tenant_id, run.input["version_id"])
            published = session.exec(
                query(session, PublishJob, tenant_id).where(
                    PublishJob.version_id == version.id, PublishJob.submitted_at != None
                )
            ).first()
            if published:
                fail("BLIND_PREDICTION_CLOSED", "内容已进入发布阶段，不能补写盲预测")
            from .blind_media import attachments

            media = attachments(session, tenant_id, version.id)
            output, used = agent_call(
                session,
                tenant_id,
                run,
                BLIND_INSTRUCTIONS,
                json.dumps(data, ensure_ascii=False),
                RubricScore,
                model_name=settings().score_model,
                media=media,
            )
            payload = output.model_dump()
            payload["composite"] = __import__("app.rubrics", fromlist=["score"]).score(
                payload, data["rubric"]["weights"]
            )
            payload["calibrated"] = False
            prediction = Prediction(
                tenant_id=tenant_id,
                version_id=version.id,
                content_hash=version.content_hash,
                rubric_version=data["rubric"]["version"],
                payload=payload,
            )
            session.add(prediction)
            run.output = payload
        elif run.kind == "feedback":
            record = ref(session, tenant_id, run.input["feedback_id"], "feedback")
            output, used = agent_call(
                session,
                tenant_id,
                run,
                "根据老师记录写家长反馈。只写观察和下一步建议，不推测儿童智力或承诺提分。",
                record.data["teacher_note"],
                FeedbackDraft,
            )
            record.data = {**record.data, "body": output.body, "status": "draft"}
            record.version += 1
            session.add(record)
            run.output = output.model_dump()
        elif run.kind == "ocr":
            from .integrations.ocr import extract

            asset = own(session, Asset, tenant_id, run.input["asset_id"])
            text = extract(asset)
            output, used = agent_call(
                session,
                tenant_id,
                run,
                "把票据文字提取为待核对费用草稿，金额单位为分。不清楚金额时填0并在notes说明，不编造。",
                text,
                ExpenseDraft,
            )
            record = create_record(
                session,
                tenant_id,
                run.actor_id,
                "expense",
                {**output.model_dump(), "asset_id": asset.id, "status": "draft"},
            )
            run.output = {
                "expense_id": record.id,
                **output.model_dump(),
                "requires_confirmation": True,
            }
        elif run.kind == "chat":
            conversation = own(
                session, Conversation, tenant_id, run.input["conversation_id"]
            )
            if conversation.state != "bot":
                release_reservations(session, tenant_id, run.request_id)
                run.status = "cancelled"
                session.add(run)
                session.commit()
                return
            indexed = session.exec(
                query(session, KnowledgeChunk, tenant_id).where(
                    KnowledgeChunk.embedding.is_not(None)
                )
            ).first()
            embedding = None
            embedding_used = 0
            if indexed and session.bind.dialect.name == "postgresql":
                vectors, embedding_used = aliyun.embed(
                    session,
                    tenant_id,
                    run.funding,
                    [run.input["question"]],
                    return_usage=True,
                )
                record_consumption(
                    session,
                    tenant_id,
                    run.request_id,
                    "text_tokens",
                    embedding_used,
                    additive=True,
                )
                session.commit()
                embedding = vectors[0]
                embedding_used = embedding_used or 20000
            sources = knowledge(
                session, tenant_id, run.input["question"], embedding=embedding
            )
            output, used = agent_call(
                session,
                tenant_id,
                run,
                CHAT_INSTRUCTIONS,
                json.dumps(
                    {"question": run.input["question"], "sources": sources},
                    ensure_ascii=False,
                ),
                ChatAnswer,
            )
            used += embedding_used
            valid = {x["id"] for x in sources}
            if not set(output.source_ids) <= valid or (
                not output.needs_human and not output.source_ids
            ):
                fail("SOURCE_INVALID", "回答缺少有效资料依据")
            session.exec(
                query(session, Conversation, tenant_id)
                .where(Conversation.id == conversation.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            ).first()
            session.refresh(conversation)
            if conversation.state == "bot":
                if output.needs_human:
                    conversation.state = "waiting_human"
                message = Message(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    role="assistant",
                    body=output.answer,
                    sources=[x for x in sources if x["id"] in output.source_ids],
                )
                session.add(message)
                session.add(conversation)
                if conversation.channel == "wecom":
                    from .integrations.wecom import send_reply

                    send_reply(session, tenant_id, conversation, output.answer)
            run.output = output.model_dump()
        elif run.kind == "knowledge_index":
            chunks = session.exec(query(session, KnowledgeChunk, tenant_id)).all()
            chunks = [
                c
                for c in chunks
                if c.embedding is None
                and (
                    not run.input.get("record_id")
                    or c.record_id == run.input["record_id"]
                )
            ][:5]
            used = 0
            if chunks:
                embeddings, used = aliyun.embed(
                    session,
                    tenant_id,
                    run.funding,
                    [x.body for x in chunks],
                    return_usage=True,
                )
                record_consumption(
                    session,
                    tenant_id,
                    run.request_id,
                    "text_tokens",
                    used,
                    additive=True,
                )
                session.commit()
                used = used or 20000
                for chunk, embedding in zip(chunks, embeddings, strict=True):
                    chunk.embedding = embedding
                    session.add(chunk)
            run.output = {
                "indexed": len(chunks),
                "batch_limit": 5,
                "repeat_for_remaining": True,
            }
        elif run.kind == "rubric_review":
            from .rubrics import process

            run.output, used = process(session, tenant_id, run, tenant)
        elif run.kind == "retro":
            metric = own(session, MetricSnapshot, tenant_id, run.input["metric_id"])
            job = own(session, PublishJob, tenant_id, metric.publish_job_id)
            version = own(session, ContentVersion, tenant_id, job.version_id)
            output, used = agent_call(
                session,
                tenant_id,
                run,
                "根据发布前稿件和实绩数据复盘。缺失指标明确写缺失，不把相关性当因果；不改写原预测。",
                json.dumps(
                    {
                        "title": version.title,
                        "body": version.body,
                        "metrics": metric.metrics,
                    },
                    ensure_ascii=False,
                ),
                RetroAnswer,
            )
            metric.summary = output.summary
            session.add(metric)
            run.output = output.model_dump()
        else:
            fail("CAPABILITY_UNAVAILABLE", "该智能体尚未启用", 503)
        finish_usage(
            session, tenant_id, run.request_id, "text_tokens", used, run.funding
        )
    run.status = "succeeded"
    run.updated_at = now()
    session.add(run)
    audit(session, tenant_id, run.actor_id, "agent.completed", run.id, kind=run.kind)
    session.commit()


def attach_media(session, tenant_id, job):
    content_id = job.parameters.get("content_id")
    if not content_id:
        return
    content = own(session, Content, tenant_id, content_id)
    latest = session.exec(
        query(session, ContentVersion, tenant_id).where(
            ContentVersion.content_id == content.id,
            ContentVersion.version == content.current_version,
        )
    ).one()
    if not set(job.asset_ids) <= set(latest.assets):
        save_content(
            session,
            tenant_id,
            job.actor_id,
            ContentInput(
                title=latest.title,
                body=latest.body,
                assets=list(dict.fromkeys(latest.assets + job.asset_ids)),
                form=content.form,
                version=content.current_version,
            ),
            content.id,
        )


def process_media(session, tenant_id, job_id):
    candidate = own(session, MediaJob, tenant_id, job_id)
    if candidate.request_id.startswith("campaign:") and candidate.status == "queued" and not (candidate.provider_task_id or candidate.parameters.get("result_urls") or candidate.parameters.get("raw_assets")):
        candidate.status = "cancelled"
        candidate.error_code = "LEGACY_CAMPAIGN_PAUSED"
        candidate.error = "旧计划尚未提交的调用已停止"
        release_reservations(session, tenant_id, candidate.request_id)
        release_reservations(session, tenant_id, candidate.request_id + ":speech")
        session.add(candidate)
        session.commit()
        return
    if candidate.parameters.get("_matrix_task_id") and not (candidate.provider_task_id or candidate.parameters.get("result_urls") or candidate.parameters.get("raw_assets") or candidate.parameters.get("result_url")):
        from .matrix_execution import may_start
        if not may_start(session, tenant_id, candidate.parameters["_matrix_task_id"]):
            return
    job = claim(
        session, MediaJob, tenant_id, job_id, ("queued", "polling", "finishing")
    )
    if not job:
        return
    tenant = session.get(Tenant, tenant_id)
    if job.kind == "speech":
        from .matrix_execution import speech
        speech(session, tenant_id, job)
        return
    raw_ids = job.parameters.get("raw_assets", [])
    if not raw_ids:
        if not job.provider_task_id and not job.parameters.get("result_urls"):
            authorize_actor(session, tenant_id, job.actor_id, {"owner", "operator"})
        if job.kind == "image":
            urls = job.parameters.get("result_urls")
            if not urls:
                job.status = "submitting"
                session.add(job)
                session.commit()
                urls, request_id = aliyun.create_image(
                    session,
                    tenant_id,
                    job.funding,
                    job.prompt,
                    job.parameters.get("ratio", "3:4"),
                )
                record_consumption(
                    session, tenant_id, job.request_id, "images", len(urls)
                )
                job.parameters = {**job.parameters, "result_urls": urls}
                job.provider_request_id = request_id
                job.status = "processing"
                session.add(job)
                session.commit()
            for url in urls:
                raw = download_result(url)
                asset = save_asset(
                    session, tenant_id, "AI原始配图.png", raw, "image/png", True
                )
                raw_ids.append(asset.id)
            finish_usage(
                session, tenant_id, job.request_id, "images", len(urls), job.funding
            )
        else:
            if not job.provider_task_id:
                job.status = "submitting"
                session.add(job)
                session.commit()
                task_id, request_id = aliyun.submit_video(
                    session, tenant_id, job.funding, job.prompt, job.parameters
                )
                job.provider_task_id = task_id
                job.provider_request_id = request_id
                job.status = "polling"
                job.updated_at = now()
                session.add(job)
                session.commit()
                return
            result = aliyun.video_status(
                session, tenant_id, job.funding, job.provider_task_id
            )
            status = result.get("output", {}).get("task_status")
            if status in ("PENDING", "RUNNING"):
                job.status = "polling"
                job.updated_at = now()
                session.add(job)
                session.commit()
                return
            if status != "SUCCEEDED":
                fail("MEDIA_PROVIDER_FAILED", "视频生成未成功，请核对供应商任务")
            url = result["output"].get("video_url")
            if not url:
                fail("VIDEO_RESULT_INVALID", "供应商未返回视频地址", 502)
            seconds = math.ceil(
                result.get("usage", {}).get(
                    "duration", job.parameters.get("duration", 10)
                )
            )
            record_consumption(
                session, tenant_id, job.request_id, "video_seconds", seconds
            )
            session.commit()
            raw_ids.append(
                save_asset(
                    session,
                    tenant_id,
                    "AI原始视频.mp4",
                    download_result(url),
                    "video/mp4",
                    True,
                ).id
            )
            finish_usage(
                session,
                tenant_id,
                job.request_id,
                "video_seconds",
                seconds,
                job.funding,
            )
        job.parameters = {**job.parameters, "raw_assets": raw_ids}
        job.status = "finishing"
        job.updated_at = now()
        session.add(job)
        session.commit()
    if job.parameters.get("raw_only"):
        job.asset_ids = list(raw_ids)
        job.status = "succeeded"
        job.updated_at = now()
        session.add(job)
        session.commit()
        return
    from .integrations.rendering import cards, video

    original = own(session, Asset, tenant_id, raw_ids[0])
    raw = Storage().read(original.object_key)
    content_id = job.parameters.get("content_id")
    title = "一起探索 AI"
    body = job.prompt
    if content_id:
        content = own(session, Content, tenant_id, content_id)
        version = session.exec(
            query(session, ContentVersion, tenant_id).where(
                ContentVersion.content_id == content_id,
                ContentVersion.version == content.current_version,
            )
        ).one()
        title = version.title
        body = version.body
    if job.kind == "image":
        if content_id:
            job.asset_ids = [
                save_asset(
                    session,
                    tenant_id,
                    "图文卡片-" + str(i + 1) + ".png",
                    data,
                    "image/png",
                    True,
                ).id
                for i, data in enumerate(cards(raw, title, body, tenant.name))
            ]
        else:
            job.asset_ids = list(raw_ids)
    else:
        audio = None
        narration = job.parameters.get("narration", "")
        if narration:
            audio_url = job.parameters.get("audio_url")
            if not audio_url:
                if job.request_id.startswith("campaign:"):
                    fail("LEGACY_CAMPAIGN_PAUSED", "已有片段已保留，新增配音需在矩阵计划重新授权", 409)
                authorize_actor(session, tenant_id, job.actor_id, {"owner", "operator"})
                if job.parameters.get("voice_state") == "submitting":
                    fail("SPEECH_RESULT_UNKNOWN", "配音结果待核实，请勿重复提交", 409)
                job.parameters = {**job.parameters, "voice_state": "submitting"}
                job.status = "submitting"
                session.add(job)
                session.commit()
                audio_url, chars = aliyun.speech(
                    session, tenant_id, job.funding, narration
                )
                job.parameters = {
                    **job.parameters,
                    "audio_url": audio_url,
                    "voice_state": "completed",
                }
                finish_usage(
                    session,
                    tenant_id,
                    job.request_id + ":speech",
                    "speech_characters",
                    chars,
                    job.funding,
                )
                job.status = "finishing"
                session.add(job)
                session.commit()
            audio = download_result(audio_url)
        final, cover = video(raw, title, narration or title, tenant.name, audio)
        job.asset_ids = [
            save_asset(session, tenant_id, "AI成片.mp4", final, "video/mp4", True).id,
            save_asset(session, tenant_id, "视频封面.png", cover, "image/png", True).id,
        ]
    job.status = "succeeded"
    job.updated_at = now()
    session.add(job)
    attach_media(session, tenant_id, job)
    session.commit()


def process_publish(session, tenant_id, job_id):
    from .matrix import guard as matrix_guard, lock_tenant, observed_identity
    matrix_task = session.exec(query(session, AutomationAccountTask, tenant_id).where(AutomationAccountTask.publish_job_id == job_id)).first()
    if matrix_task:
        try:
            matrix_guard(session, tenant_id, matrix_task.id, publishing=True)
        except HTTPException:
            return
    lock_tenant(session, tenant_id)
    candidate = own(session, PublishJob, tenant_id, job_id)
    if candidate.status != "scheduled" or as_utc(candidate.scheduled_at) > now():
        session.rollback()
        return
    account = own(session, SocialAccount, tenant_id, candidate.account_id)
    session.refresh(account)
    if account.paused:
        session.rollback()
        return
    active_id = account.config.get("inflight_publish_id")
    if active_id and active_id != job_id:
        active = session.exec(query(session, PublishJob, tenant_id).where(PublishJob.id == active_id)).first()
        if active and active.status not in ("succeeded", "cancelled") and (active.submitted_at or active.status in ("processing", "submitting", "unknown")):
            candidate.error_code = "ACCOUNT_BUSY"
            candidate.error = "同账号有执行中或待核实的发布任务，请先核实结果"
            session.add(candidate)
            session.commit()
            return
    candidate.error, candidate.error_code = "", ""
    account.config = {**account.config, "inflight_publish_id": job_id}
    session.add(account)
    job = claim(session, PublishJob, tenant_id, job_id, ("scheduled",))
    if not job:
        return
    if job.scheduled_at > now():
        job.status = "scheduled"
        session.add(job)
        session.commit()
        return
    tenant = authorize_actor(
        session, tenant_id, job.actor_id, {"owner", "operator"}, "publish.write"
    )
    if not settings().allow_live_publish:
        fail("LIVE_PUBLISH_DISABLED", "部署管理员尚未启用真实发布", 503)
    if not tenant.settings.get("publishing_enabled"):
        fail("PUBLISHING_NOT_AUTHORIZED", "机构尚未启用发布授权")
    version = own(session, ContentVersion, tenant_id, job.version_id)
    if (
        policy_notes(session, tenant_id, version.title, version.body, version.assets)
        or not version.policy_checked
    ):
        fail("CONTENT_REVIEW_REQUIRED", "内容检查未通过，请处理提示")
    prediction = session.exec(
        query(session, Prediction, tenant_id).where(Prediction.version_id == version.id)
    ).first()
    if not prediction or prediction.content_hash != version.content_hash:
        fail("PREDICTION_REQUIRED", "当前成品版本尚未完成盲预测")
    if prediction.payload.get("credibility", 0) < 3:
        fail("CONTENT_REVIEW_REQUIRED", "盲评可信度低于3分，需要核对事实并更新成品")
    if not version.assets:
        fail("ASSET_REQUIRED", "请先生成或上传内容素材")
    account = own(session, SocialAccount, tenant_id, job.account_id)
    login = publishing.check_login(tenant_id, account)
    if login.get("status") != "connected":
        fail("LOGIN_REQUIRED", "账号需要扫码登录", 503)
    if matrix_task:
        expected = account.identity_key
        observed_identity(session, tenant_id, account, login)
        session.flush()
        if not expected or account.identity_key != expected:
            session.commit()
            fail("IDENTITY_REQUIRED", "发布前无法核实目标账号身份", 409)
        matrix_guard(session, tenant_id, matrix_task.id, publishing=True)
    assets = []
    for asset_id in version.assets:
        asset = own(session, Asset, tenant_id, asset_id)
        if not asset.consent:
            fail("ASSET_CONSENT_REQUIRED", "素材尚未确认使用授权")
        assets.append(
            {
                "name": asset.name,
                "mime": asset.mime,
                "data": base64.b64encode(Storage().read(asset.object_key)).decode(),
            }
        )
    job.status = "submitting"
    job.submitted_at = now()
    session.add(job)
    session.commit()
    result = publishing.publish(tenant_id, account, job, version, assets)
    if (
        result.get("status") == "succeeded"
        and result.get("external_id")
        and result.get("external_url")
    ):
        job.status = "succeeded"
        form = own(session, Content, tenant_id, version.content_id).form
        capability = "publish_video" if form == "video" else "publish_image"
        account.config = {
            **account.config,
            "inflight_publish_id": None,
            "verified_capabilities": {
                **account.config.get("verified_capabilities", {}),
                capability: True,
            },
        }
        session.add(account)
        job.external_id = result["external_id"]
        job.external_url = result["external_url"]
        job.retro_due_at = now() + timedelta(days=3)
    else:
        job.status = "unknown"
        job.error_code = "PUBLISH_RESULT_UNCONFIRMED"
        job.error = "发布结果待核实，系统不会再次点击发布"
    job.updated_at = now()
    session.add(job)
    session.commit()


def schedule_campaign(session, tenant, campaign):
    # Platform-only routing is retired; history and explicit PublishJobs are retained.
    if campaign.data.get("enabled"):
        campaign.data = {**campaign.data, "enabled": False, "matrix_migration": "请使用明确账号的矩阵计划"}
        session.add(campaign)
        session.commit()


@celery.task(name="ops.tick")
def tick():
    with Session(engine(), expire_on_commit=False) as session:
        tenants = session.exec(select(Tenant)).all()
        for tenant in tenants:
            set_scope(session, tenant.id)
            from .social import tick_social
            from .reports import tick as tick_reports
            from .operations import capture_rosters

            try:
                capture_rosters(session, tenant.id)
                session.commit()
                tick_reports(session, tenant)
                for interrupted in session.exec(
                    query(session, AdmissionImport, tenant.id).where(
                        AdmissionImport.status == "processing",
                        AdmissionImport.updated_at < now() - timedelta(minutes=15),
                    )
                ).all():
                    interrupted.status = "failed"
                    interrupted.error = "识别期间服务中断，可重新识别；已确认行仍保留"
                    interrupted.version += 1
                    session.add(interrupted)
                session.commit()
                for batch in session.exec(
                    query(session, AdmissionImport, tenant.id).where(
                        AdmissionImport.status == "queued"
                    )
                ).all():
                    from .routes_operations import dispatch_import

                    dispatch_import(tenant.id, batch.id)
            except Exception:
                session.rollback()

            try:
                from .matrix_worker import tick_matrix
                tick_matrix(session, tenant)
            except Exception:
                session.rollback()
            try:
                tick_social(session, tenant)
            except Exception:
                session.rollback()
            for model, kind in ((AgentRun, "agent"), (MediaJob, "media")):
                retries = session.exec(
                    query(session, model, tenant.id).where(
                        model.status == "retrying", model.updated_at <= now()
                    )
                ).all()
                for pending in retries:
                    if entitlement(session, tenant)["active"] or (
                        kind == "media" and pending.provider_task_id
                    ):
                        pending.status = (
                            "polling"
                            if kind == "media" and pending.provider_task_id
                            else "queued"
                        )
                        session.add(pending)
                session.commit()
            if entitlement(session, tenant)["active"]:
                campaigns = session.exec(
                    query(session, Record, tenant.id).where(Record.kind == "campaign")
                ).all()
                for campaign in campaigns:
                    try:
                        schedule_campaign(session, tenant, campaign)
                    except Exception:
                        session.rollback()
                queued = session.exec(
                    query(session, AgentRun, tenant.id).where(
                        AgentRun.status == "queued"
                    )
                ).all()
                for run in queued:
                    dispatch("ocr" if run.kind == "ocr" else "agent", tenant.id, run.id)
                publish_jobs = session.exec(
                    query(session, PublishJob, tenant.id).where(
                        PublishJob.status == "scheduled",
                        PublishJob.scheduled_at <= now(),
                    )
                ).all()
                for job in publish_jobs:
                    dispatch("publish", tenant.id, job.id)
            media = session.exec(
                query(session, MediaJob, tenant.id).where(
                    MediaJob.status.in_(["queued", "polling", "finishing"])
                )
            ).all()
            for job in media:
                if (
                    job.provider_task_id
                    or job.parameters.get("raw_assets")
                    or job.parameters.get("result_urls")
                    or entitlement(session, tenant)["active"]
                ):
                    dispatch("media", tenant.id, job.id)
            for model, kind in (
                (AgentRun, "agent"),
                (MediaJob, "media"),
                (PublishJob, "publish"),
            ):
                stale = session.exec(
                    query(session, model, tenant.id).where(
                        model.status.in_(["processing", "submitting"]),
                        model.updated_at < now() - timedelta(minutes=15),
                    )
                ).all()
                for job in stale:
                    if kind == "media" and job.provider_task_id:
                        job.status = "polling"
                    else:
                        job.status = "unknown"
                        job.error_code = "WORKER_INTERRUPTED"
                        job.error = "执行中断，结果需要核实"
                    session.add(job)
            due = session.exec(
                query(session, PublishJob, tenant.id).where(
                    PublishJob.status == "succeeded",
                    PublishJob.retro_due_at != None,
                    PublishJob.retro_due_at <= now(),
                )
            ).all()
            for job in due:
                try:
                    account = own(session, SocialAccount, tenant.id, job.account_id)
                    result = publishing.collect_metrics(tenant.id, account, job)
                    if result.get("available"):
                        session.add(
                            MetricSnapshot(
                                tenant_id=tenant.id,
                                publish_job_id=job.id,
                                metrics=result.get("metrics", {}),
                                source="platform",
                            )
                        )
                        account.config = {**account.config, "verified_capabilities": {**account.config.get("verified_capabilities", {}), "metrics": True}}
                        session.add(account)
                        job.retro_due_at = None
                    else:
                        job.error_code = "METRICS_UNAVAILABLE"
                        job.error = "平台暂未返回指标，可补录"
                        job.retro_due_at = now() + timedelta(hours=12)
                    session.add(job)
                except Exception:
                    job.retro_due_at = now() + timedelta(hours=12)
                    session.add(job)
            session.commit()


@celery.task(name="ops.admission_import")
def admission_import_task(batch_id, tenant_id):
    from .admission_import import execute

    execute(batch_id, tenant_id)


@celery.task(name="ops.matrix")
def matrix_task(tenant_id, run_id):
    from .matrix_worker import execute_run
    execute_run(tenant_id, run_id)

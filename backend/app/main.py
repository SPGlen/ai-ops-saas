from .permissions import check_job, identity_for
import asyncio, json, logging, threading
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, Depends
from fastapi.responses import (
    JSONResponse,
    FileResponse,
    StreamingResponse,
    PlainTextResponse,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from sqlmodel import Session, select
from .config import settings, ROOT
from .db import engine, initialize, check_runtime_role, set_scope, session_dep
from .models import *
from .security import fail, digest, encrypt
from .auth import Identity, scoped, require
from .domain import own, query
from .routes_auth import router as auth_router
from .routes_business import router as business_router
from .routes_ai import router as ai_router
from .routes_public import router as public_router
from .routes_staff import router as staff_router
from .routes_social import router as social_router
from .routes_operations import router as operations_router
from .routes_matrix import router as matrix_router

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
stop = threading.Event()


def scheduler():
    from .worker import tick

    while not stop.wait(15):
        try:
            tick()
        except Exception:
            logging.getLogger("ops.scheduler").warning(
                "Scheduler tick failed; will retry without resubmitting in-flight jobs"
            )


@asynccontextmanager
async def lifespan(app):
    cfg = settings()
    cfg.validate_runtime()
    if not cfg.production and engine().dialect.name == "sqlite":
        initialize()
    if cfg.demo_mode:
        from .demo_runtime import check_demo_database
        check_demo_database()
    if cfg.production:
        check_runtime_role()
    stop.clear()
    if cfg.task_mode == "local":
        threading.Thread(target=scheduler, daemon=True, name="ops-scheduler").start()
    yield
    stop.set()


app = FastAPI(
    title="知营 · 教育机构运营 API",
    version="0.4.0-rc2",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
)
from .body_limit import BoundedBody
from .demo_runtime import DemoMiddleware, router as demo_router
app.include_router(demo_router)

app.add_middleware(BoundedBody)
origin = settings().public_url.rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=[
        "Content-Type",
        "X-CSRF-Token",
        "X-Public-Token",
        "Last-Event-ID",
        "X-Tenant-ID",
    ],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(
        set(
            [urlparse(origin).hostname, "localhost", "127.0.0.1"]
            + ([] if settings().production else ["testserver"])
        )
    ),
)
for router in (
    auth_router,
    business_router,
    operations_router,
    matrix_router,
    staff_router,
    social_router,
    ai_router,
    public_router,
):
    app.include_router(router)


@app.exception_handler(IntegrityError)
async def integrity_error(request, error):
    return JSONResponse(
        {
            "detail": {
                "code": "CONSTRAINT_CONFLICT",
                "message": "操作与已有记录冲突，请刷新后核对",
            }
        },
        409,
    )


@app.exception_handler(ValidationError)
async def model_validation(request, error):
    return JSONResponse(
        {
            "detail": {
                "code": "VALIDATION_ERROR",
                "message": "输入字段不符合要求",
                "fields": [
                    {"field": ".".join(map(str, e["loc"])), "message": e["msg"]}
                    for e in error.errors()
                ],
            }
        },
        422,
    )


@app.exception_handler(RequestValidationError)
async def request_validation(request, error):
    return JSONResponse(
        {
            "detail": {
                "code": "VALIDATION_ERROR",
                "message": "请检查必填字段和格式",
                "fields": [
                    {"field": ".".join(map(str, e["loc"])), "message": e["msg"]}
                    for e in error.errors()
                ],
            }
        },
        422,
    )


@app.middleware("http")
async def security_headers(request, call_next):
    try:
        size = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse(
            {"detail": {"code": "INVALID_LENGTH", "message": "请求格式错误"}}, 400
        )
    if size > settings().max_upload_mb * 1024 * 1024 + 1024 * 1024:
        return JSONResponse(
            {"detail": {"code": "BODY_TOO_LARGE", "message": "请求内容过大"}}, 413
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    if settings().production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/v1/health", tags=["运行状态"])
def health():
    from sqlalchemy import text

    with engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "environment": settings().environment,
        "database": engine().dialect.name,
        "tasks": settings().task_mode,
        "live_publish": settings().allow_live_publish,
        "text_provider": settings().text_provider,
        "model_configured": bool(settings().deepseek_api_key if settings().text_provider == "deepseek" else settings().aliyun_api_key),
        "publisher_configured": bool(settings().publisher_url),
        "payment_enabled": False,
        "ocr_enabled": settings().ocr_enabled,
    }


@app.get("/api/v1/jobs/{kind}/{job_id}/events", tags=["任务事件"])
async def events(kind: str, job_id: str, i: Identity = Depends(scoped)):
    model = {"agent": AgentRun, "media": MediaJob, "publish": PublishJob}.get(kind)
    if not model:
        fail("NOT_FOUND", "任务不存在", 404)
    obj = own(i.session, model, i.tenant.id, job_id)
    check_job(i, kind, obj)
    tenant_id, user_id = i.tenant.id, i.user.id

    async def stream():
        previous = None
        for seq in range(60):
            with Session(engine()) as session:
                set_scope(session, tenant_id, user_id)
                member = session.exec(
                    select(Membership).where(
                        Membership.user_id == user_id, Membership.tenant_id == tenant_id
                    )
                ).first()
                if not member or member.status != "active":
                    return
                auth = session.get(AuthSession, i.auth.id)
                user = session.get(User, user_id)
                if not auth or auth.expires_at < now() or not user or user.disabled:
                    return
                job = own(session, model, tenant_id, job_id)
                try:
                    check_job(
                        identity_for(session, session.get(Tenant, tenant_id), user_id),
                        kind,
                        job,
                    )
                except Exception:
                    return
                data = {
                    "id": job.id,
                    "status": job.status,
                    "error_code": job.error_code,
                    "error": job.error,
                }
                encoded = json.dumps(data, ensure_ascii=False)
                if encoded != previous:
                    yield (
                        "id: " + str(seq) + "\nevent: status\ndata: " + encoded + "\n\n"
                    )
                    previous = encoded
                else:
                    yield ": heartbeat\n\n"
                if job.status in (
                    "succeeded",
                    "failed",
                    "cancelled",
                    "unknown",
                    "waiting_authorization",
                ):
                    return
            await asyncio.sleep(2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@app.get("/api/v1/webhooks/wecom/{tenant_id}", tags=["企微回调"])
def wecom_verify(
    tenant_id: str,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str,
    session: Session = Depends(session_dep),
):
    from .integrations.wecom import integration, verify_signature, decrypt_message

    set_scope(session, tenant_id)
    row, secret = integration(session, tenant_id)
    verify_signature(secret["token"], timestamp, nonce, echostr, msg_signature)
    return PlainTextResponse(
        decrypt_message(secret["encoding_aes_key"], echostr, row.config["corpid"])
    )


@app.post("/api/v1/webhooks/wecom/{tenant_id}", tags=["企微回调"])
async def wecom_event(
    tenant_id: str,
    request: Request,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    session: Session = Depends(session_dep),
):
    from .integrations.wecom import integration, verify_signature, decrypt_message, ET
    from .worker import dispatch

    set_scope(session, tenant_id)
    row, secret = integration(session, tenant_id)
    raw = await request.body()
    if len(raw) > 65536:
        fail("CALLBACK_TOO_LARGE", "回调过大", 413)
    try:
        root = ET.fromstring(raw)
        encrypted = root.findtext("Encrypt")
        if not encrypted:
            fail("CALLBACK_INVALID", "回调缺少密文")
        verify_signature(secret["token"], timestamp, nonce, encrypted, msg_signature)
        text = decrypt_message(
            secret["encoding_aes_key"], encrypted, row.config["corpid"]
        )
        event = ET.fromstring(text)
    except (DefusedXmlException, ParseError, ValueError):
        fail("CALLBACK_INVALID", "XML格式无效")
    from .operations import enabled

    if not enabled(session.get(Tenant, tenant_id)):
        return PlainTextResponse("success")
    event_type = event.findtext("Event", "")
    if event_type != "kf_msg_or_event":
        return PlainTextResponse("success")
    token = event.findtext("Token", "")
    open_kfid = event.findtext("OpenKfId", "")
    if open_kfid != row.config["open_kfid"]:
        fail("CALLBACK_ACCOUNT_INVALID", "客服账号不匹配", 403)
    external_id = digest(text)
    prior = session.exec(
        query(session, WebhookReceipt, tenant_id).where(
            WebhookReceipt.external_id == external_id
        )
    ).first()
    if not prior:
        session.add(
            WebhookReceipt(
                tenant_id=tenant_id,
                external_id=external_id,
                body_hash=digest(raw.decode()),
            )
        )
        run = AgentRun(
            tenant_id=tenant_id,
            kind="wecom_event",
            request_id="wecom-event:" + external_id,
            actor_id="webhook",
            input={
                "event_cipher": encrypt(
                    tenant_id, {"token": token, "open_kfid": open_kfid}
                )
            },
        )
        session.add(run)
        session.commit()
        dispatch("agent", tenant_id, run.id)
    return PlainTextResponse("success")


@app.get("/api/docs", include_in_schema=False)
def api_docs():
    return FileResponse(Path(__file__).parent / "static" / "docs.html")


@app.get("/api/docs-assets/{name}", include_in_schema=False)
def api_docs_asset(name: str):
    if name not in ("swagger-ui.css", "swagger-ui-bundle.js", "swagger-init.js"):
        fail("NOT_FOUND", "资源不存在", 404)
    return FileResponse(Path(__file__).parent / "static" / name)


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path.startswith("api/"):
        fail("NOT_FOUND", "接口不存在", 404)
    root = (ROOT / "frontend" / "dist").resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        fail("NOT_FOUND", "页面不存在", 404)
    if target.is_file():
        return FileResponse(target)
    if Path(path).suffix:
        fail("NOT_FOUND", "资源不存在", 404)
    if (root / "index.html").exists():
        return FileResponse(root / "index.html")
    return JSONResponse(
        {"message": "前端尚未构建；开发预览使用 http://127.0.0.1:5188"}, 503
    )


@app.middleware("http")
async def paused_consultation(request: Request, call_next):
    path = request.url.path
    private = path.startswith(("/api/v1/conversations", "/api/v1/social-replies")) or (
        path.startswith("/api/v1/social-accounts/")
        and any(
            x in path
            for x in ("/manual-interactions", "/poll-interactions", "/replies")
        )
    )
    public = path.startswith("/api/v1/public/") and (
        "/chat" in path or "/conversations" in path
    )
    if private or public:
        with Session(engine()) as session:
            tenant = None
            if public:
                slug = path.split("/")[4]
                tenant = session.exec(select(Tenant).where(Tenant.slug == slug)).first()
            else:
                raw = request.cookies.get("ops_session", "")
                auth = session.get(AuthSession, digest(raw)) if raw else None
                if auth and auth.tenant_id:
                    tenant = session.get(Tenant, auth.tenant_id)
            if tenant and not tenant.settings.get("consultation_enabled", False):
                return JSONResponse(
                    {
                        "detail": {
                            "code": "FEATURE_PAUSED",
                            "message": "咨询接待本期暂停，历史资料保留",
                        }
                    },
                    403,
                )
    return await call_next(request)

# Presentation access validation wraps all HTTP routes, including early-return middleware.
app.add_middleware(DemoMiddleware)

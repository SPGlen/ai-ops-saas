"""An isolated presentation environment; regular authentication and permissions still apply."""
import re
from collections import Counter
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Scope, Receive, Send
from sqlmodel import select, Session
from .config import settings
from .auth import scoped, Identity
from .permissions import Scope as BusinessScope, has
from .models import Asset, AutomationPlan, BusinessEvent, Record, SocialAccount, MediaProfile, Tenant, Integration, now
from .security import fail
from .reports import build, TZ

router = APIRouter(prefix="/api/v1/demo", tags=["独立企业演示"])

# No exception here grants business permission: the original endpoint checks still run.
SAFE_WRITES = [
    r"/auth/(login|logout|switch-tenant)", r"/records/[^/]+(?:/[^/]+)?",
    r"/orders/[^/]+/(payments|refunds)", r"/ledger/[^/]+/reverse",
    r"/enrollments/[^/]+/(attendance|adjust|transfer)", r"/education/feedback-kpis/[^/]+",
    r"/contents(?:/[^/]+)?", r"/assets", r"/finance/receipt-links",
    r"/admissions/imports(?:/[^/]+/(confirm|retry))?",
    r"/report-snapshots/(weekly|monthly)", r"/operations/alerts/[^/]+",
    r"/studio/(definitions(?:/[^/]+(?:/publish|/restore/\d+|/preview)?)?|forms/[^/]+/submissions|workflows/[^/]+/instances|instances/[^/]+/(apply|withdraw|resubmit)|tasks/[^/]+/(decision|assign))",
    r"/media-profiles(?:/[^/]+)?", r"/account-groups(?:/[^/]+)?",
    r"/social-accounts", r"/social-accounts/[^/]+/matrix", r"/automation-plans(?:/[^/]+)?",
    r"/members/[^/]+", r"/addons/digital-human/requests", r"/settlement-statements",
    r"/public/[^/]+/leads",
]

class DemoMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        cfg = settings()
        if scope["type"] != "http" or not cfg.demo_mode:
            await self.app(scope, receive, send)
            return
        if cfg.demo_expires_at:
            try:
                expiry = datetime.fromisoformat(cfg.demo_expires_at).astimezone(timezone.utc)
            except ValueError:
                expiry = datetime.min.replace(tzinfo=timezone.utc)
            if now() >= expiry:
                await PlainTextResponse("临时演示链接已到期，请联系演示负责人重新开启。", status_code=410, headers={"Cache-Control":"no-store"})(scope, receive, send)
                return
        if cfg.demo_access_code:
            from .demo_access import gate
            response = await gate(scope, receive, cfg)
            if response is not None:
                await response(scope, receive, send)
                return
        path = scope.get("path", "")
        method = scope.get("method", "GET")
        if path.startswith("/api/v1/") and method not in ("GET", "HEAD", "OPTIONS"):
            tail = path.removeprefix("/api/v1")
            if not any(re.fullmatch(pattern, tail) for pattern in SAFE_WRITES):
                response = JSONResponse({"detail": {"code": "DEMO_EXTERNAL_DISABLED", "message": "演示环境仅操作虚构业务数据；真实 AI 调用、账号登录、发布、通知及凭证配置暂不开放。"}}, status_code=409)
                await response(scope, receive, send)
                return
        async def demo_send(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).extend([(b"cache-control", b"no-store"), (b"x-robots-tag", b"noindex, nofollow")])
            await send(message)
        await self.app(scope, receive, demo_send)


def check_demo_database():
    from .db import engine
    with Session(engine()) as s:
        tenants = s.exec(select(Tenant)).all()
        if not tenants or any(t.settings.get("showcase", {}).get("version") != "enterprise-demo-1" for t in tenants):
            raise RuntimeError("Refusing to serve non-showcase data in enterprise demo mode; prepare a dedicated demo database")
        if any(row.secret_cipher for row in s.exec(select(Integration)).all()):
            raise RuntimeError("A showcase database must not contain supplier credentials")

@router.get("/info")
def info():
    return {"enabled": settings().demo_mode, "label": "企业演示环境", "synthetic_data": True, "external_calls": False} if settings().demo_mode else {"enabled": False}

@router.get("/showcase")
def showcase(i: Identity = Depends(scoped)):
    if not settings().demo_mode:
        fail("NOT_FOUND", "演示入口未启用", 404)
    scope = BusinessScope(i)
    counts = {k: len(scope.list(k)) for k, permission in {"lead":"lead.read", "student":"student.read", "class":"class.read", "order":"order.read"}.items() if has(i, permission)}
    local = now().astimezone(TZ)
    result = {"counts": counts, "as_of": now(), "seeded_at": i.tenant.settings.get("showcase", {}).get("seeded_at"), "synthetic_data": True, "external_calls": False}
    if has(i, "reports.read"):
        result["monthly"] = build(i, "monthly", local.strftime("%Y-%m"))
        result["weekly"] = build(i, "weekly", local.date().isoformat())
    if has(i, "content.read"):
        assets = []
        for aid in i.tenant.settings.get("showcase", {}).get("asset_ids", []):
            asset = i.session.get(Asset, aid)
            if asset and asset.tenant_id == i.tenant.id:
                assets.append({"id":asset.id, "name":asset.name, "mime":asset.mime})
        result["assets"] = assets
        result["matrix"] = {"accounts": len(i.session.exec(select(SocialAccount).where(SocialAccount.tenant_id == i.tenant.id)).all()), "brands": len(i.session.exec(select(MediaProfile).where(MediaProfile.tenant_id == i.tenant.id)).all()), "plans": len(i.session.exec(select(AutomationPlan).where(AutomationPlan.tenant_id == i.tenant.id)).all()), "live_publishing": False}
    return result

import json, hmac, smtplib
from email.message import EmailMessage
from datetime import timedelta
from dataclasses import dataclass
from fastapi import Depends, Request, Response
from sqlmodel import Session, select
from .models import (
    User,
    Tenant,
    Membership,
    AuthSession,
    EmailToken,
    PlatformSettings,
    now,
    uid,
    as_utc,
)
from .security import digest, random_token, fail, password_hash
from .config import settings
from .db import session_dep, set_scope


@dataclass
class Identity:
    user: User
    auth: AuthSession
    tenant: Tenant | None
    role: str
    session: Session
    roles: set[str]
    authz_version: int = 0


def current(request: Request, session: Session = Depends(session_dep)):
    raw = request.cookies.get("ops_session", "")
    auth = session.get(AuthSession, digest(raw)) if raw else None
    if not auth or auth.expires_at < now():
        fail("AUTH_REQUIRED", "请先登录", 401)
    user = session.get(User, auth.user_id)
    if not user or user.disabled or not user.verified:
        fail("AUTH_REQUIRED", "账户尚未验证或已停用", 401)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not hmac.compare_digest(digest(csrf), auth.csrf_hash):
            fail("CSRF_INVALID", "请求校验失败，请刷新后重试", 403)
    tenant = None
    role = ""
    roles = set()
    authz_version = 0
    if auth.tenant_id:
        membership = session.exec(
            select(Membership).where(
                Membership.user_id == user.id, Membership.tenant_id == auth.tenant_id
            )
        ).first()
        if not membership or membership.status != "active":
            if request.url.path not in (
                "/api/v1/auth/me",
                "/api/v1/auth/logout",
                "/api/v1/auth/switch-tenant",
            ):
                fail("TENANT_FORBIDDEN", "机构访问权限已失效", 403)
            auth.tenant_id = None
        else:
            tenant = session.get(Tenant, auth.tenant_id)
            role = membership.role
            from .permissions import member_roles

            roles = member_roles(membership)
            authz_version = membership.authz_version
    requested_tenant = request.headers.get("X-Tenant-ID")
    if (
        requested_tenant
        and requested_tenant != auth.tenant_id
        and not request.url.path.startswith("/api/v1/auth/")
    ):
        fail("CLIENT_TENANT_CHANGED", "当前机构已变更，请刷新页面", 409)
    set_scope(session, auth.tenant_id or "", user.id)
    return Identity(user, auth, tenant, role, session, roles, authz_version)


def scoped(identity: Identity = Depends(current)):
    if not identity.tenant:
        fail("TENANT_REQUIRED", "请先选择机构", 403)
    if identity.tenant.status != "active":
        fail("TENANT_SUSPENDED", "机构已暂停，请联系平台管理员", 403)
    return identity


def require(identity, roles):
    from .permissions import member_roles, LEGACY

    accepted = set().union(*(set(LEGACY.get(r, [r])) for r in roles))
    if not identity.roles.intersection(accepted):
        fail("ROLE_FORBIDDEN", "当前角色无权执行此操作", 403)


def platform(identity: Identity = Depends(current)):
    if not identity.user.platform_admin:
        fail("PLATFORM_FORBIDDEN", "需要平台管理员权限", 403)
    return identity


def entitlement(session, tenant):
    global_settings = session.get(PlatformSettings, 1)
    dates = [
        d
        for d in [
            tenant.free_until,
            global_settings.free_until if global_settings else None,
        ]
        if d
    ]
    until = max(dates) if dates else None
    paid = tenant.settings.get("paid_until")
    if paid:
        from datetime import datetime

        date = as_utc(datetime.fromisoformat(paid))
        until = max(until, date) if until else date
    return {
        "active": tenant.status == "active" and bool(until and until > now()),
        "until": until,
        "payment_enabled": False,
    }


def writable(identity):
    if not entitlement(identity.session, identity.tenant)["active"]:
        fail("ENTITLEMENT_EXPIRED", "使用期已结束，可查看与导出，请联系管理员延期", 402)


def create_session(session, user, response, tenant_id=None):
    token, csrf = random_token(), random_token()
    session.add(
        AuthSession(
            id=digest(token),
            user_id=user.id,
            csrf_hash=digest(csrf),
            tenant_id=tenant_id,
            expires_at=now() + timedelta(hours=settings().session_hours),
        )
    )
    session.commit()
    response.set_cookie(
        "ops_session",
        token,
        httponly=True,
        secure=settings().production or (settings().demo_mode and settings().public_url.startswith("https://")),
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    response.set_cookie(
        "ops_csrf",
        csrf,
        httponly=False,
        secure=settings().production or (settings().demo_mode and settings().public_url.startswith("https://")),
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    return csrf


def send_mail(session, user, purpose):
    raw = random_token()
    session.add(
        EmailToken(
            id=digest(raw),
            user_id=user.id,
            purpose=purpose,
            expires_at=now() + timedelta(hours=1),
        )
    )
    session.commit()
    url = (
        settings().public_url.rstrip("/")
        + ("/verify?token=" if purpose == "verify" else "/reset?token=")
        + raw
    )
    if settings().smtp_host:
        mail = EmailMessage()
        mail["Subject"] = "知营 · " + (
            "验证邮箱" if purpose == "verify" else "重置密码"
        )
        mail["From"] = settings().smtp_from
        mail["To"] = user.email
        mail.set_content("请在一小时内打开以下链接完成操作：\n" + url)
        try:
            with smtplib.SMTP(
                settings().smtp_host, settings().smtp_port, timeout=15
            ) as smtp:
                if settings().smtp_tls:
                    smtp.starttls()
                if settings().smtp_user:
                    smtp.login(settings().smtp_user, settings().smtp_password)
                smtp.send_message(mail)
        except (smtplib.SMTPException, OSError):
            fail("MAIL_UNAVAILABLE", "邮件暂未送达，请稍后重发验证邮件", 503)
    elif not settings().production:
        outbox = settings().data_dir / "outbox"
        outbox.mkdir(parents=True, exist_ok=True)
        (outbox / (uid() + ".json")).write_text(
            json.dumps(
                {"email": user.email, "purpose": purpose, "url": url},
                ensure_ascii=False,
            ),
            encoding="utf8",
        )
    else:
        fail("MAIL_UNAVAILABLE", "邮件服务暂不可用", 503)

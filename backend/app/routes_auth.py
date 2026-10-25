from .config import settings
from datetime import datetime, timedelta
import secrets, re
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, EmailStr
from sqlmodel import Session, select, delete
from sqlalchemy import update
from . import schemas as S
from .models import *
from .db import session_dep, set_scope
from .auth import (
    current,
    scoped,
    platform,
    Identity,
    create_session,
    send_mail,
    require,
    entitlement,
    writable,
)
from .security import fail, limit, digest, password_hash, password_valid
from .domain import audit
from .permissions import member_roles, permissions, validate_roles, LEGACY

router = APIRouter(prefix="/api/v1", tags=["账户与机构"])


class TokenInput(S.Strict):
    token: str


class ResetInput(TokenInput):
    password: str = Field(min_length=12, max_length=128)


class EmailInput(S.Strict):
    email: EmailStr


class SwitchInput(S.Strict):
    tenant_id: str


class TenantInput(S.Strict):
    name: str = Field(min_length=2, max_length=80)


class MemberInput(S.Strict):
    email: EmailStr
    role: str | None = None
    roles: list[str] | None = None


class MemberRole(S.Strict):
    authz_version: int | None = Field(default=None, ge=1)
    role: str | None = None
    roles: list[str] | None = None
    status: S.Literal["active", "disabled"] | None = None


class TenantConfig(S.Strict):
    brand: str = Field(default="", max_length=2000)
    audience: str = Field(default="", max_length=2000)
    tone: str = Field(default="清楚、真实、有用", max_length=1000)
    publishing_enabled: bool = False
    funding: S.Literal["platform", "byok"] = "platform"
    auto_publish: bool = False


class PlatformConfig(S.Strict):
    free_until: datetime | None = None
    registration_open: bool = True
    prices: dict[str, int] = Field(default_factory=dict)
    catalog: list[S.Plan] | None = None


class TenantAdmin(S.Strict):
    account_limit: int | None = Field(default=None, ge=0, le=500)
    plan_id: str = ""
    status: S.Literal["active", "suspended"] = "active"
    free_until: datetime | None = None
    quotas: dict[str, int] = Field(default_factory=dict)


@router.post("/auth/register", status_code=202)
def register(
    body: S.Register, request: Request, session: Session = Depends(session_dep)
):
    limit(session, "register:" + request.client.host, 5, 3600)
    config = session.get(PlatformSettings, 1)
    if config and not config.registration_open:
        fail("REGISTRATION_CLOSED", "暂未开放新机构注册", 403)
    existing = session.exec(
        select(User).where(User.email == str(body.email).lower())
    ).first()
    if not existing:
        user = User(
            email=str(body.email).lower(),
            name=body.name,
            password_hash=password_hash(body.password),
        )
        tenant = Tenant(
            name=body.tenant_name,
            slug="org-" + secrets.token_hex(5),
            settings={
                "brand": body.tenant_name,
                "quotas": {},
                "funding": "platform",
                "publishing_enabled": False,
                "auto_publish": False,
                "authorization_schema_version": 1,
            },
        )
        session.add(user)
        session.add(tenant)
        session.flush()
        session.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))
        session.commit()
        send_mail(session, user, "verify")
    return {"message": "如该邮箱可以注册，验证邮件已发送。请验证后登录。"}


@router.post("/auth/verify")
def verify(body: TokenInput, session: Session = Depends(session_dep)):
    token = session.get(EmailToken, digest(body.token))
    if (
        not token
        or token.purpose != "verify"
        or token.used_at
        or token.expires_at < now()
    ):
        fail("TOKEN_INVALID", "链接无效或已过期")
    user = session.get(User, token.user_id)
    user.verified = True
    token.used_at = now()
    session.add(user)
    session.add(token)
    session.commit()
    return {"message": "邮箱验证成功，请登录"}


@router.post("/auth/forgot")
def forgot(body: EmailInput, request: Request, session: Session = Depends(session_dep)):
    limit(session, "forgot:" + request.client.host, 5, 3600)
    user = session.exec(
        select(User).where(User.email == str(body.email).lower(), User.verified == True)
    ).first()
    if user:
        send_mail(session, user, "reset")
    return {"message": "如账户存在，重置邮件已发送"}


@router.post("/auth/reset")
def reset(body: ResetInput, session: Session = Depends(session_dep)):
    token = session.get(EmailToken, digest(body.token))
    if (
        not token
        or token.purpose != "reset"
        or token.used_at
        or token.expires_at < now()
    ):
        fail("TOKEN_INVALID", "链接无效或已过期")
    user = session.get(User, token.user_id)
    user.password_hash = password_hash(body.password)
    token.used_at = now()
    session.add(user)
    session.add(token)
    session.exec(delete(AuthSession).where(AuthSession.user_id == user.id))
    session.commit()
    return {"message": "密码已更新，原会话已退出"}


@router.post("/auth/login")
def login(
    body: S.Login,
    request: Request,
    response: Response,
    session: Session = Depends(session_dep),
):
    if settings().demo_mode:
        limit(session, "showcase-login:" + request.client.host, 60, 60)
    else:
        limit(session, "login:" + request.client.host, 20, 900)
    user = session.exec(
        select(User).where(User.email == str(body.email).lower())
    ).first()
    if (
        not user
        or not password_valid(body.password, user.password_hash)
        or user.disabled
    ):
        fail("LOGIN_FAILED", "邮箱或密码错误", 401)
    if not user.verified:
        fail("EMAIL_UNVERIFIED", "请先完成邮箱验证", 403)
    member = session.exec(
        select(Membership).where(
            Membership.user_id == user.id, Membership.status == "active"
        )
    ).first()
    create_session(session, user, response, member.tenant_id if member else None)
    return {"message": "登录成功"}


@router.post("/auth/logout")
def logout(response: Response, i: Identity = Depends(current)):
    i.session.delete(i.auth)
    i.session.commit()
    response.delete_cookie("ops_session", path="/")
    response.delete_cookie("ops_csrf", path="/")
    return {"message": "已退出"}


@router.get("/auth/me")
def me(i: Identity = Depends(current)):
    memberships = i.session.exec(
        select(Membership).where(
            Membership.user_id == i.user.id, Membership.status == "active"
        )
    ).all()
    tenants = []
    for member in memberships:
        tenant = i.session.get(Tenant, member.tenant_id)
        if tenant:
            tenants.append(
                {
                    "id": tenant.id,
                    "name": tenant.name,
                    "slug": tenant.slug,
                    "role": member.role,
                    "roles": sorted(member_roles(member)),
                    "status": tenant.status,
                }
            )
    return {
        "user": {
            "id": i.user.id,
            "name": i.user.name,
            "email": i.user.email,
            "platform_admin": i.user.platform_admin,
        },
        "tenants": tenants,
        "tenant_id": i.auth.tenant_id,
        "role": i.role,
        "roles": sorted(i.roles),
        "permissions": sorted(permissions(i.roles)),
        "features": {
            "consultation": bool(
                i.tenant and i.tenant.settings.get("consultation_enabled", False)
            ),
            "course_packages": False,
            "demo_mode": settings().demo_mode,
        },
        "authz_version": i.authz_version,
        "entitlement": entitlement(i.session, i.tenant) if i.tenant else None,
    }


@router.post("/auth/switch-tenant")
def switch(body: SwitchInput, i: Identity = Depends(current)):
    member = i.session.exec(
        select(Membership).where(
            Membership.user_id == i.user.id, Membership.tenant_id == body.tenant_id
        )
    ).first()
    if not member or not member_roles(member):
        fail("TENANT_FORBIDDEN", "无权进入该机构", 403)
    i.auth.tenant_id = member.tenant_id
    i.session.add(i.auth)
    i.session.commit()
    return {"tenant_id": member.tenant_id}


@router.post("/tenants", status_code=201)
def new_tenant(body: TenantInput, i: Identity = Depends(current)):
    limit(i.session, "tenant-create:" + i.user.id, 3, 86400)
    tenant = Tenant(
        name=body.name,
        slug="org-" + secrets.token_hex(5),
        settings={"quotas": {}, "authorization_schema_version": 1},
    )
    i.session.add(tenant)
    i.session.flush()
    i.session.add(Membership(tenant_id=tenant.id, user_id=i.user.id, role="owner"))
    i.session.commit()
    return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug}


@router.get("/tenant", response_model=S.TenantView)
def tenant_info(i: Identity = Depends(scoped)):
    return {
        "id": i.tenant.id,
        "name": i.tenant.name,
        "slug": i.tenant.slug,
        "settings": i.tenant.settings,
        "entitlement": entitlement(i.session, i.tenant),
    }


@router.patch("/tenant")
def tenant_settings(body: TenantConfig, i: Identity = Depends(scoped)):
    require(i, {"owner"})
    writable(i)
    i.tenant.settings = {**i.tenant.settings, **body.model_dump(exclude_unset=True)}
    i.session.add(i.tenant)
    audit(i.session, i.tenant.id, i.user.id, "tenant.settings", i.tenant.id)
    i.session.commit()
    return {"message": "机构设置已保存"}


@router.get("/members", response_model=list[S.MembershipView])
def members(i: Identity = Depends(scoped)):
    result = []
    for m in i.session.exec(
        select(Membership).where(Membership.tenant_id == i.tenant.id)
    ).all():
        user = i.session.get(User, m.user_id)
        result.append(
            {
                "id": m.id,
                "user_id": m.user_id,
                "name": user.name,
                "email": user.email if "owner" in i.roles else "",
                "role": m.role,
                "roles": sorted(member_roles(m))
                if m.status == "active"
                else (m.roles or LEGACY.get(m.role, [m.role])),
                "status": m.status,
                "authz_version": m.authz_version,
                "permissions": sorted(permissions(member_roles(m))),
            }
        )
    return result


@router.get("/authorization-catalog")
def get_authorization_catalog(i: Identity = Depends(scoped)):
    require(i, {"owner"})
    from .permissions import authorization_catalog

    return {"items": authorization_catalog(), "managed_by": "owner"}


@router.post("/members")
def member_add(body: MemberInput, i: Identity = Depends(scoped)):
    require(i, {"owner"})
    writable(i)
    user = i.session.exec(
        select(User).where(User.email == str(body.email).lower(), User.verified == True)
    ).first()
    if not user:
        fail("MEMBER_NOT_REGISTERED", "请成员先注册并验证邮箱")
    old = i.session.exec(
        select(Membership).where(
            Membership.tenant_id == i.tenant.id, Membership.user_id == user.id
        )
    ).first()
    if old:
        fail("MEMBER_EXISTS", "该成员已加入", 409)
    chosen = validate_roles(
        body.roles
        if body.roles is not None
        else LEGACY.get(body.role or "operator", [body.role])
    )
    member = Membership(
        tenant_id=i.tenant.id, user_id=user.id, role=chosen[0], roles=chosen
    )
    i.session.add(member)
    audit(i.session, i.tenant.id, i.user.id, "member.add", user.id, role=body.role)
    i.session.commit()
    return {"id": member.id}


@router.patch("/members/{member_id}")
def member_role(member_id: str, body: MemberRole, i: Identity = Depends(scoped)):
    require(i, {"owner"})
    writable(i)
    i.session.exec(
        select(Tenant).where(Tenant.id == i.tenant.id).with_for_update()
    ).one()
    actor = i.session.exec(
        select(Membership)
        .where(Membership.tenant_id == i.tenant.id, Membership.user_id == i.user.id)
        .execution_options(populate_existing=True)
    ).first()
    if "owner" not in member_roles(actor):
        fail("ROLE_FORBIDDEN", "负责人权限已变更", 403)
    m = i.session.exec(
        select(Membership).where(
            Membership.id == member_id, Membership.tenant_id == i.tenant.id
        )
    ).first()
    if not m:
        fail("NOT_FOUND", "成员不存在", 404)
    if body.authz_version is not None and body.authz_version != m.authz_version:
        fail("VERSION_CONFLICT", "员工授权已更新，请刷新后重新设置", 409)
    chosen = validate_roles(
        body.roles
        if body.roles is not None
        else LEGACY.get(body.role, [body.role])
        if body.role
        else (m.roles or LEGACY.get(m.role, [m.role]))
    )
    status = body.status or m.status
    owners = [
        x
        for x in i.session.exec(
            select(Membership).where(Membership.tenant_id == i.tenant.id)
        ).all()
        if "owner" in member_roles(x)
        and (u := i.session.get(User, x.user_id))
        and u.verified
        and not u.disabled
    ]
    if (
        "owner" in member_roles(m)
        and ("owner" not in chosen or status != "active")
        and len(owners) <= 1
    ):
        fail("LAST_OWNER", "请保留至少一位有效负责人")
    changed = i.session.exec(
        update(Membership)
        .where(
            Membership.id == m.id,
            Membership.tenant_id == i.tenant.id,
            Membership.authz_version == m.authz_version,
        )
        .values(
            roles=chosen,
            role=chosen[0],
            status=status,
            authz_version=m.authz_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        fail("VERSION_CONFLICT", "员工授权已更新，请刷新后重新设置", 409)
    i.session.refresh(m)
    audit(
        i.session,
        i.tenant.id,
        i.user.id,
        "member.permissions",
        m.user_id,
        roles=chosen,
        status=status,
    )
    i.session.commit()
    return {
        "message": "岗位和状态已更新",
        "authz_version": m.authz_version,
        "permissions": sorted(permissions(member_roles(m))),
    }


@router.get("/platform")
def platform_info(i: Identity = Depends(platform)):
    config = i.session.get(PlatformSettings, 1)
    tenants = i.session.exec(select(Tenant).order_by(Tenant.created_at.desc())).all()
    return {
        "settings": config,
        "tenants": [
            {
                "id": t.id,
                "slug": t.slug,
                "name": t.name,
                "status": t.status,
                "free_until": t.free_until,
                "quotas": t.settings.get("quotas", {}),
                "plan_id": t.settings.get("plan_id", ""),
                "account_limit": __import__("app.matrix", fromlist=["account_limit"]).account_limit(i.session, t),
            }
            for t in tenants
        ],
    }


@router.patch("/platform")
def platform_update(body: PlatformConfig, i: Identity = Depends(platform)):
    if any(v < 0 for v in body.prices.values()):
        fail("PRICE_INVALID", "计价参数不能为负数")
    config = i.session.get(PlatformSettings, 1) or PlatformSettings()
    if "free_until" in body.model_fields_set:
        config.free_until = as_utc(body.free_until) if body.free_until else None
    if "registration_open" in body.model_fields_set:
        config.registration_open = body.registration_open
    if "prices" in body.model_fields_set:
        config.plans = {**config.plans, "prices": body.prices}
    if body.catalog is not None:
        if (
            len({p.id for p in body.catalog}) != len(body.catalog)
            or len(body.catalog) > 20
        ):
            fail("PLAN_INVALID", "套餐ID不能重复，最多20个套餐")
        for plan in body.catalog:
            if not set(plan.quotas) <= {
                "text_tokens",
                "images",
                "video_seconds",
                "speech_characters",
                "cost_fen",
            } or any(v < 0 for v in plan.quotas.values()):
                fail("PLAN_QUOTA_INVALID", "套餐额度无效")
        config.plans = {
            **config.plans,
            "catalog": [p.model_dump() for p in body.catalog],
        }
    i.session.add(config)
    i.session.commit()
    return {"message": "平台开放期与计价参数已保存"}


@router.patch("/platform/tenants/{tenant_id}")
def platform_tenant(tenant_id: str, body: TenantAdmin, i: Identity = Depends(platform)):
    tenant = i.session.get(Tenant, tenant_id)
    if not tenant:
        fail("NOT_FOUND", "机构不存在", 404)
    allowed = {
        "text_tokens",
        "images",
        "video_seconds",
        "speech_characters",
        "cost_fen",
    }
    if not set(body.quotas) <= allowed or any(
        v < 0 or v > 1000000000 for v in body.quotas.values()
    ):
        fail("QUOTA_INVALID", "额度配置无效")
    config = i.session.get(PlatformSettings, 1)
    if body.plan_id and not any(
        p["id"] == body.plan_id
        for p in (config.plans.get("catalog", []) if config else [])
    ):
        fail("PLAN_NOT_FOUND", "套餐不存在")
    if "status" in body.model_fields_set:
        tenant.status = body.status
    if "free_until" in body.model_fields_set:
        tenant.free_until = as_utc(body.free_until) if body.free_until else None
    tenant.settings = {
        **tenant.settings,
        **({"quotas": body.quotas} if "quotas" in body.model_fields_set else {}),
        **({"plan_id": body.plan_id} if "plan_id" in body.model_fields_set else {}),
        **({"matrix_account_limit": body.account_limit} if body.account_limit is not None else {}),
    }
    i.session.add(tenant)
    set_scope(i.session, tenant.id, i.user.id)
    audit(
        i.session,
        tenant.id,
        i.user.id,
        "platform.entitlement",
        tenant.id,
        status=tenant.status,
    )
    i.session.commit()
    return {"message": "机构权益已更新"}


@router.post("/auth/resend-verification", status_code=202)
def resend_verification(
    body: EmailInput, request: Request, session: Session = Depends(session_dep)
):
    limit(session, "resend-ip:" + request.client.host, 5, 3600)
    limit(session, "resend-email:" + str(body.email).lower(), 3, 3600)
    user = session.exec(
        select(User).where(
            User.email == str(body.email).lower(), User.verified == False
        )
    ).first()
    if user:
        send_mail(session, user, "verify")
    return {"message": "如该邮箱有待验证账户，验证邮件已重新发送"}

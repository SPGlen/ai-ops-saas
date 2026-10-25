"""Email-bound staff invitations; accepting never creates an institution."""

import json, smtplib
from datetime import timedelta
from email.message import EmailMessage
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import update
from sqlmodel import Session, select
from pydantic import EmailStr, Field
from .models import MemberInvitation, Tenant, Membership, User, now
from .schemas import Strict
from .auth import Identity, scoped, require, writable, create_session
from .db import session_dep, set_scope
from .security import fail, random_token, digest, password_hash, password_valid, limit
from .config import settings
from .domain import audit
from .permissions import validate_roles, member_roles, ROLE_LABELS

router = APIRouter(prefix="/api/v1", tags=["员工邀请"])


class InviteInput(Strict):
    email: EmailStr
    roles: list[str] = Field(min_length=1, max_length=6)


class AcceptInput(Strict):
    token: str = Field(min_length=20, max_length=300)
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(default="", max_length=50)


def resolve(s, raw):
    slug = raw.split(".", 1)[0]
    t = s.exec(select(Tenant).where(Tenant.slug == slug)).first()
    if not t:
        fail("INVITATION_INVALID", "邀请无效或已过期", 400)
    set_scope(s, t.id)
    inv = s.exec(
        select(MemberInvitation).where(
            MemberInvitation.id == digest(raw), MemberInvitation.tenant_id == t.id
        )
    ).first()
    if (
        not inv
        or inv.revoked
        or inv.used_at
        or inv.expires_at <= now()
        or t.status != "active"
    ):
        fail("INVITATION_INVALID", "邀请无效或已过期", 400)
    issuer = s.exec(
        select(Membership).where(
            Membership.tenant_id == t.id, Membership.user_id == inv.inviter_id
        )
    ).first()
    issuer_user = s.get(User, inv.inviter_id)
    if (
        not issuer_user
        or issuer_user.disabled
        or not issuer_user.verified
        or "owner" not in member_roles(issuer)
    ):
        fail("INVITATION_INVALID", "邀请人权限已变更", 400)
    return inv, t


@router.get("/roles")
def role_catalog(i: Identity = Depends(scoped)):
    return ROLE_LABELS


@router.post("/member-invitations", status_code=201)
def invite(body: InviteInput, i: Identity = Depends(scoped)):
    require(i, {"owner"})
    writable(i)
    limit(i.session, "invite:" + i.tenant.id, 30, 3600)
    chosen = validate_roles(body.roles)
    raw = i.tenant.slug + "." + random_token()
    inv = MemberInvitation(
        id=digest(raw),
        tenant_id=i.tenant.id,
        email=str(body.email).lower(),
        roles=chosen,
        inviter_id=i.user.id,
        expires_at=now() + timedelta(hours=24),
    )
    url = settings().public_url.rstrip("/") + "/invite?token=" + raw
    cfg = settings()
    if cfg.smtp_host:
        mail = EmailMessage()
        mail["Subject"] = "知营 · " + i.tenant.name + "邀请您加入"
        mail["From"] = cfg.smtp_from
        mail["To"] = inv.email
        mail.set_content("请在24小时内打开链接接受邀请：\n" + url)
        try:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as smtp:
                if cfg.smtp_tls:
                    smtp.starttls()
                if cfg.smtp_user:
                    smtp.login(cfg.smtp_user, cfg.smtp_password)
                smtp.send_message(mail)
        except (OSError, smtplib.SMTPException):
            fail("MAIL_UNAVAILABLE", "邀请邮件暂未送达，请重试", 503)
    elif cfg.production:
        fail("MAIL_UNAVAILABLE", "请先配置邮件服务", 503)
    else:
        out = cfg.data_dir / "outbox"
        out.mkdir(parents=True, exist_ok=True)
        (out / (inv.id + ".json")).write_text(
            json.dumps(
                {"email": inv.email, "purpose": "invitation", "url": url},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    i.session.add(inv)
    audit(i.session, i.tenant.id, i.user.id, "member.invite", inv.id, roles=chosen)
    i.session.commit()
    return {
        "id": inv.id,
        "expires_at": inv.expires_at,
        "message": "邀请已发送",
        **({"development_link": url} if not cfg.production else {}),
    }


@router.get("/member-invitations")
def invitations(i: Identity = Depends(scoped)):
    require(i, {"owner"})
    return i.session.exec(
        select(MemberInvitation)
        .where(MemberInvitation.tenant_id == i.tenant.id)
        .order_by(MemberInvitation.created_at.desc())
    ).all()


@router.delete("/member-invitations/{invitation_id}")
def revoke(invitation_id: str, i: Identity = Depends(scoped)):
    require(i, {"owner"})
    writable(i)
    inv = i.session.exec(
        select(MemberInvitation).where(
            MemberInvitation.id == invitation_id,
            MemberInvitation.tenant_id == i.tenant.id,
        )
    ).first()
    if not inv:
        fail("NOT_FOUND", "邀请不存在", 404)
    inv.revoked = True
    i.session.add(inv)
    audit(i.session, i.tenant.id, i.user.id, "member.invite.revoke", inv.id)
    i.session.commit()
    return {"message": "邀请已撤销"}


@router.get("/auth/invitation")
def inspect_invitation(token: str, session: Session = Depends(session_dep)):
    inv, t = resolve(session, token)
    return {
        "tenant_name": t.name,
        "email": inv.email,
        "roles": inv.roles,
        "expires_at": inv.expires_at,
    }


@router.post("/auth/accept-invitation")
def accept(
    body: AcceptInput,
    request: Request,
    response: Response,
    session: Session = Depends(session_dep),
):
    limit(session, "accept-invite:" + request.client.host, 10, 3600)
    inv, t = resolve(session, body.token)
    user = session.exec(select(User).where(User.email == inv.email)).first()
    if user:
        if user.disabled or not password_valid(body.password, user.password_hash):
            fail("LOGIN_FAILED", "已有账号请填写当前密码", 401)
    else:
        if not body.name.strip():
            fail("NAME_REQUIRED", "请填写姓名")
        user = User(
            email=inv.email,
            name=body.name,
            password_hash=password_hash(body.password),
            verified=True,
        )
        session.add(user)
        session.flush()
    existing = session.exec(
        select(Membership).where(
            Membership.user_id == user.id, Membership.tenant_id == t.id
        )
    ).first()
    if existing and existing.status == "active":
        fail("MEMBER_EXISTS", "您已加入该机构，请直接登录", 409)
    claimed = session.exec(
        update(MemberInvitation)
        .where(
            MemberInvitation.id == inv.id,
            MemberInvitation.used_at.is_(None),
            MemberInvitation.revoked == False,
        )
        .values(used_at=now())
    )
    if claimed.rowcount != 1:
        fail("INVITATION_INVALID", "邀请已被使用", 409)
    user.verified = True
    session.add(user)
    member = existing or Membership(tenant_id=t.id, user_id=user.id)
    member.roles = validate_roles(inv.roles)
    member.role = member.roles[0]
    member.status = "active"
    member.authz_version += 1
    session.add(member)
    audit(session, t.id, user.id, "member.invite.accept", inv.id)
    session.commit()
    create_session(session, user, response, t.id)
    return {"message": "已加入机构", "tenant_id": t.id}


@router.get("/auth/demo-accounts")
def demo_accounts(session: Session = Depends(session_dep)):
    if settings().production:
        fail("NOT_FOUND", "入口不存在", 404)
    out = []
    for u in session.exec(
        select(User).where(User.email.like("%@zhiying.example"))
    ).all():
        memberships = session.exec(
            select(Membership).where(
                Membership.user_id == u.id, Membership.status == "active"
            )
        ).all()
        for m in memberships:
            t = session.get(Tenant, m.tenant_id)
            if t and t.slug in ("qinghe-demo", "xingguang-demo"):
                out.append(
                    {
                        "email": u.email,
                        "name": u.name,
                        "tenant_name": t.name,
                        "roles": sorted(member_roles(m)),
                        "password": "Demo-Zhiying-2026!"
                        if u.email == "demo@zhiying.example"
                        else "Demo-Staff-2026!",
                        "platform_admin": u.platform_admin,
                    }
                )
    return out

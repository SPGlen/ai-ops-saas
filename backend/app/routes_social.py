from typing import Literal
from datetime import timedelta
import json
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlmodel import select, Session
from .models import *
from .auth import Identity, scoped, writable, require
from .db import session_dep, set_scope
from .schemas import Strict
from .domain import own, query, audit, create_record
from .permissions import permit, has, check_conversation, Scope, member_roles
from .security import fail, encrypt
from . import social
from .integrations import publishing

router = APIRouter(prefix="/api/v1", tags=["自媒体账号与互动"])


class Policy(Strict):
    auto_reply: bool = False
    assignee_id: str = ""


class ReplyInput(Strict):
    body: str = Field(min_length=1, max_length=2000)
    request_id: str = Field(min_length=8, max_length=100)


class OfficialCredential(Strict):
    access_token: str = Field(min_length=8, max_length=4000)
    client_key: str = Field(min_length=1, max_length=200)
    client_secret: str = Field(min_length=8, max_length=1000)
    open_id: str = Field(min_length=1, max_length=300)


@router.get("/social-accounts/{account_id}/capabilities")
def caps(account_id: str, i: Identity = Depends(scoped)):
    permit(i, "social.read")
    a = own(i.session, SocialAccount, i.tenant.id, account_id)
    return {
        "account_id": a.id,
        "platform": a.platform,
        "capabilities": social.capabilities(a),
        "official_url": social.LINKS[a.platform],
        "policy": {
            "auto_reply": a.config.get("auto_reply", False),
            "assignee_id": a.config.get("assignee_id", ""),
        },
        "live_replies": __import__("app.config", fromlist=["settings"])
        .settings()
        .allow_live_replies,
    }


@router.patch("/social-accounts/{account_id}/policy")
def policy(account_id: str, body: Policy, i: Identity = Depends(scoped)):
    permit(i, "social.manage")
    writable(i)
    a = own(i.session, SocialAccount, i.tenant.id, account_id)
    if body.assignee_id:
        member = i.session.exec(
            select(Membership).where(
                Membership.tenant_id == i.tenant.id,
                Membership.user_id == body.assignee_id,
            )
        ).first()
        if not member_roles(member) & {"owner", "admissions"}:
            fail("ASSIGNEE_INVALID", "请选择本机构有效招生人员")
    a.config = {
        **a.config,
        "auto_reply": body.auto_reply,
        "assignee_id": body.assignee_id,
        "policy_actor_id": i.user.id,
    }
    i.session.add(a)
    audit(
        i.session,
        i.tenant.id,
        i.user.id,
        "social.policy",
        a.id,
        enabled=body.auto_reply,
    )
    i.session.commit()
    return {"message": "策略已保存；未验证的能力仍会转人工"}


@router.post("/social-accounts/{account_id}/probe")
def probe(account_id: str, i: Identity = Depends(scoped)):
    permit(i, "social.manage")
    writable(i)
    a = own(i.session, SocialAccount, i.tenant.id, account_id)
    status = publishing.check_login(i.tenant.id, a)
    a.status = status.get("status", "waiting_authorization")
    verified = dict(a.config.get("verified_capabilities", {}))
    if a.status == "connected":
        verified["login"] = True
    if a.status == "connected" and a.platform == "xiaohongshu":
        out = publishing.call(
            i.tenant.id, a.id, "comments-list", {"platform": a.platform}, 120
        )
        if out.get("available"):
            verified["comment_read"] = True
        if out.get("external_user_id"):
            a.config = {**a.config, "external_user_id": out["external_user_id"]}
        for event in out.get("events", []):
            social.ingest(i.session, a, event)
    a.config = {**a.config, "verified_capabilities": verified}
    i.session.add(a)
    i.session.commit()
    return caps(account_id, i)


@router.put("/social-accounts/{account_id}/douyin-credentials")
def douyin_credentials(
    account_id: str, body: OfficialCredential, i: Identity = Depends(scoped)
):
    permit(i, "social.manage")
    writable(i)
    a = own(i.session, SocialAccount, i.tenant.id, account_id)
    if a.platform != "douyin":
        fail("PLATFORM_INVALID", "仅支持抖音官方授权")
    from .integrations.douyin import api

    secret = body.model_dump()
    user = api(
        secret,
        "/oauth/userinfo/",
        {"open_id": body.open_id, "access_token": body.access_token},
    )
    if user.get("open_id") != body.open_id:
        fail("ACCOUNT_MISMATCH", "官方授权账号不匹配", 403)
    row = i.session.exec(
        query(i.session, Integration, i.tenant.id).where(
            Integration.provider == "douyin:" + a.id
        )
    ).first() or Integration(tenant_id=i.tenant.id, provider="douyin:" + a.id)
    a.config = {**a.config, "external_user_id": body.open_id}
    i.session.add(a)
    row.secret_cipher = encrypt(i.tenant.id, secret)
    row.config = {"open_id": body.open_id, "client_key": body.client_key}
    row.active = True
    i.session.add(row)
    audit(i.session, i.tenant.id, i.user.id, "social.official.replace", a.id)
    i.session.commit()
    return {"configured": True, "message": "授权身份已核对，评论与私信权限仍需分别验证"}


@router.post("/social-accounts/{account_id}/poll")
def poll(account_id: str, i: Identity = Depends(scoped)):
    permit(i, "social.reply")
    writable(i)
    a = own(i.session, SocialAccount, i.tenant.id, account_id)
    if a.platform == "douyin":
        from .integrations.douyin import poll_comments

        events = poll_comments(i.session, a)
    elif a.platform == "xiaohongshu":
        events = publishing.call(
            i.tenant.id, a.id, "comments-list", {"platform": a.platform}, 120
        ).get("events", [])
    else:
        fail("CAPABILITY_UNSUPPORTED", "视频号互动尚未接通，请使用官方后台", 409)
    for event in events:
        social.ingest(i.session, a, event)
    a.config = {
        **a.config,
        "verified_capabilities": {
            **a.config.get("verified_capabilities", {}),
            "comment_read": True,
        },
    }
    i.session.add(a)
    i.session.commit()
    return {"received": len(events)}


@router.get("/social-replies")
def replies(i: Identity = Depends(scoped)):
    permit(i, "conversation.read")
    rows = i.session.exec(
        query(i.session, SocialReply, i.tenant.id).order_by(
            SocialReply.created_at.desc()
        )
    ).all()
    out = []
    for r in rows:
        c = own(i.session, Conversation, i.tenant.id, r.conversation_id)
        if social_conversation_visible(i, c):
            out.append(r)
    return out[:200]


def social_conversation_visible(i, c):
    from .permissions import conversation_visible

    return conversation_visible(i, c)


@router.post("/conversations/{conversation_id}/social-reply", status_code=202)
def reply(conversation_id: str, body: ReplyInput, i: Identity = Depends(scoped)):
    permit(i, "conversation.write")
    writable(i)
    c = check_conversation(
        i, own(i.session, Conversation, i.tenant.id, conversation_id)
    )
    if not c.account_id:
        fail("CHANNEL_INVALID", "该会话不是自媒体互动")
    if c.state not in ("human", "waiting_human"):
        fail("TAKEOVER_REQUIRED", "请先接管会话")
    prior = i.session.exec(
        query(i.session, SocialReply, i.tenant.id).where(
            SocialReply.request_id == body.request_id
        )
    ).first()
    if prior:
        if prior.body != body.body or prior.conversation_id != c.id:
            fail("IDEMPOTENCY_CONFLICT", "请求编号已用于其他回复", 409)
        return prior
    event = i.session.exec(
        query(i.session, SocialEvent, i.tenant.id)
        .where(SocialEvent.conversation_id == c.id)
        .order_by(SocialEvent.created_at.desc())
    ).first()
    if not event:
        fail("EVENT_REQUIRED", "请先采集收到的互动")
    r = SocialReply(
        tenant_id=i.tenant.id,
        account_id=c.account_id,
        event_id=event.id,
        conversation_id=c.id,
        request_id=body.request_id,
        actor_id=i.user.id,
        body=body.body,
    )
    i.session.add(r)
    i.session.commit()
    return r


@router.post("/conversations/{conversation_id}/convert-lead")
def convert(conversation_id: str, i: Identity = Depends(scoped)):
    permit(i, "conversation.write")
    writable(i)
    c = check_conversation(
        i, own(i.session, Conversation, i.tenant.id, conversation_id)
    )
    if c.lead_id:
        return {"lead_id": c.lead_id}
    account = (
        own(i.session, SocialAccount, i.tenant.id, c.account_id)
        if c.account_id
        else None
    )
    assignee = social.active_assignee(i.session, account) if account else c.owner_id
    # Platform user IDs are channel contacts, never invented telephone numbers.
    lead = create_record(
        i.session,
        i.tenant.id,
        i.user.id,
        "lead",
        {
            "name": c.title,
            "contact": "平台咨询：" + c.channel,
            "source": c.channel + ":" + c.source_work_id,
            "owner_id": assignee,
            "notes": "会话编号：" + c.id,
        },
    )
    c.lead_id = lead.id
    c.owner_id = assignee
    i.session.add(c)
    i.session.commit()
    return {"lead_id": lead.id}


@router.post("/webhooks/douyin/{tenant_id}/{account_id}")
async def douyin_callback(
    tenant_id: str,
    account_id: str,
    request: Request,
    session: Session = Depends(session_dep),
):
    from .integrations.douyin import credential, verify_webhook

    set_scope(session, tenant_id)
    a = own(session, SocialAccount, tenant_id, account_id)
    if a.platform != "douyin":
        fail("PLATFORM_INVALID", "平台不匹配", 400)
    row, secret = credential(session, a)
    raw = await request.body()
    if len(raw) > 65536:
        fail("BODY_TOO_LARGE", "回调过大", 413)
    verify_webhook(secret, raw, request.headers.get("X-Douyin-Signature", ""))
    data = json.loads(raw)
    if data.get("client_key") != row.config["client_key"]:
        fail("APP_MISMATCH", "回调应用不匹配", 403)
    if data.get("event") == "verify_webhook":
        return {"challenge": data.get("content", {}).get("challenge")}
    # Preserve and deduplicate signed receipts. Unverified event schemas do not fabricate inbox messages.
    event_id = request.headers.get("Msg-Id")
    if data.get("from_user_id") != row.config["open_id"]:
        fail("ACCOUNT_MISMATCH", "回调授权用户不匹配", 403)
    if not event_id or len(event_id) > 200:
        fail("EVENT_ID_REQUIRED", "缺少官方事件编号", 400)
    key = "douyin:" + account_id + ":" + event_id
    prior = session.exec(
        query(session, WebhookReceipt, tenant_id).where(
            WebhookReceipt.external_id == key
        )
    ).first()
    if not prior:
        session.add(
            WebhookReceipt(
                tenant_id=tenant_id,
                external_id=key,
                body_hash=__import__("hashlib").sha256(raw).hexdigest(),
            )
        )
        session.commit()
    return {"received": True, "inbox_delivery": "awaiting_account_schema_verification"}


class DraftInput(Strict):
    request_id: str = Field(min_length=8, max_length=100)


class ManualInteraction(Strict):
    kind: Literal["comment", "private_message"] = "private_message"
    sender_name: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1, max_length=5000)
    work_id: str = Field(default="", max_length=300)


class Outcome(Strict):
    note: str = Field(min_length=5, max_length=1000)


@router.post("/social-accounts/{account_id}/manual-interactions", status_code=201)
def manual_interaction(
    account_id: str, body: ManualInteraction, i: Identity = Depends(scoped)
):
    permit(i, "social.reply")
    writable(i)
    a = own(i.session, SocialAccount, i.tenant.id, account_id)
    marker = "manual:" + uid()
    event = social.ingest(
        i.session,
        a,
        {
            "external_id": marker,
            "kind": body.kind,
            "thread_id": marker,
            "sender_id": marker,
            "sender_name": body.sender_name,
            "body": body.body,
            "work_id": body.work_id,
            "metadata": {"manual": True, "recorded_by": i.user.id},
        },
    )
    audit(i.session, i.tenant.id, i.user.id, "social.manual.record", event.id)
    i.session.commit()
    return {"conversation_id": event.conversation_id, "source": "manual"}


@router.post("/conversations/{conversation_id}/reply-draft", status_code=202)
def draft_reply(conversation_id: str, body: DraftInput, i: Identity = Depends(scoped)):
    permit(i, "conversation.write")
    writable(i)
    c = check_conversation(
        i, own(i.session, Conversation, i.tenant.id, conversation_id)
    )
    event = i.session.exec(
        query(i.session, SocialEvent, i.tenant.id)
        .where(SocialEvent.conversation_id == c.id)
        .order_by(SocialEvent.created_at.desc())
    ).first()
    if not event:
        fail("EVENT_REQUIRED", "请先记录收到的互动")
    old = i.session.exec(
        query(i.session, SocialReply, i.tenant.id).where(
            SocialReply.request_id == body.request_id
        )
    ).first()
    if old:
        if old.conversation_id != c.id or not old.draft_only:
            fail("IDEMPOTENCY_CONFLICT", "请求编号已使用", 409)
        return old
    r = SocialReply(
        tenant_id=i.tenant.id,
        account_id=c.account_id,
        event_id=event.id,
        conversation_id=c.id,
        request_id=body.request_id,
        actor_id=i.user.id,
        draft_only=True,
    )
    i.session.add(r)
    i.session.commit()
    return r


@router.post("/social-replies/{reply_id}/mark-handled")
def mark_handled(reply_id: str, body: Outcome, i: Identity = Depends(scoped)):
    permit(i, "conversation.write")
    writable(i)
    r = own(i.session, SocialReply, i.tenant.id, reply_id)
    c = check_conversation(
        i, own(i.session, Conversation, i.tenant.id, r.conversation_id)
    )
    if r.status not in ("draft", "unknown"):
        fail("STATE_INVALID", "请先核对待处理的回复记录", 409)
    r.status = "handled_externally"
    i.session.add(r)
    audit(
        i.session,
        i.tenant.id,
        i.user.id,
        "social.handled.externally",
        r.id,
        note=body.note,
    )
    i.session.commit()
    return {"status": r.status}


@router.post("/conversations/{conversation_id}/handled-externally")
def conversation_handled(
    conversation_id: str, body: Outcome, i: Identity = Depends(scoped)
):
    permit(i, "conversation.write")
    writable(i)
    from .social import LOCKS, cancel_pending
    import threading

    with LOCKS.setdefault((i.tenant.id, conversation_id), threading.RLock()):
        c = i.session.exec(
            query(i.session, Conversation, i.tenant.id)
            .where(Conversation.id == conversation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if not c:
            fail("NOT_FOUND", "会话不存在", 404)
        check_conversation(i, c)
        if not c.account_id:
            fail("CHANNEL_INVALID", "该会话不是自媒体互动")
        cancel_pending(i.session, i.tenant.id, c.id)
        c.state = "human"
        i.session.add(c)
        i.session.add(
            Message(
                tenant_id=i.tenant.id,
                conversation_id=c.id,
                role="staff",
                body="外部处理登记：" + body.note,
                delivery_state="handled_externally",
            )
        )
        audit(
            i.session,
            i.tenant.id,
            i.user.id,
            "social.conversation.handled.externally",
            c.id,
            note=body.note,
        )
        i.session.commit()
    return {"status": "handled_externally"}

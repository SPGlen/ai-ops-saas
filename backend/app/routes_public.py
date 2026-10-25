from .permissions import permit, check_conversation, conversation_visible, Scope
import hmac
from datetime import timedelta
from fastapi import APIRouter, Depends, Request, Header
from sqlmodel import Session, select
from .models import *
from .db import session_dep, set_scope
from .security import fail, digest, random_token, limit
from .domain import *
from .auth import scoped, Identity, require, writable, entitlement
from . import schemas as S

router = APIRouter(prefix="/api/v1", tags=["公开预约与客服"])


def public_tenant(session, slug, write=False):
    tenant = session.exec(
        select(Tenant).where(Tenant.slug == slug, Tenant.status == "active")
    ).first()
    if not tenant:
        fail("NOT_FOUND", "机构入口不存在", 404)
    set_scope(session, tenant.id)
    if write and not entitlement(session, tenant)["active"]:
        fail("ENTITLEMENT_EXPIRED", "机构入口暂不可用，请直接联系机构", 402)
    return tenant


def public_conversation(session, tenant_id, conversation_id, token):
    conversation = own(session, Conversation, tenant_id, conversation_id)
    if (
        conversation.channel != "web"
        or not token
        or not hmac.compare_digest(conversation.token_hash, digest(token))
    ):
        fail("CONVERSATION_FORBIDDEN", "咨询会话无效", 403)
    return conversation


def messages(session, tenant_id, conversation_id):
    rows = session.exec(
        query(session, Message, tenant_id)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
        .limit(200)
    ).all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "body": m.body,
            "sources": [{"id": s["id"], "title": s["title"]} for s in m.sources],
            "created_at": m.created_at,
            "delivery_state": m.delivery_state,
        }
        for m in rows
    ]


@router.get("/public/{slug}")
def public_info(slug: str, session: Session = Depends(session_dep)):
    tenant = public_tenant(session, slug)
    courses = session.exec(
        query(session, Record, tenant.id).where(Record.kind == "knowledge")
    ).all()
    return {
        "name": tenant.name,
        "slug": tenant.slug,
        "brand": tenant.settings.get("brand", tenant.name),
        "available": entitlement(session, tenant)["active"],
        "consultation_enabled": bool(
            tenant.settings.get("consultation_enabled", False)
        ),
        "courses": [
            {"id": r.id, "name": r.data["name"], "description": r.data.get("body", "")}
            for r in courses
            if r.data.get("approved")
        ],
    }


@router.post("/public/{slug}/leads", status_code=201)
def public_lead(
    slug: str,
    body: S.PublicLead,
    request: Request,
    session: Session = Depends(session_dep),
):
    tenant = public_tenant(session, slug, True)
    limit(session, "booking:" + slug + ":" + request.client.host, 5, 3600)
    if body.website:
        return {"message": "预约已受理"}
    values = body.model_dump(exclude={"consent", "website"})
    lead = create_record(session, tenant.id, "public", "lead", values)
    session.commit()
    return {"id": lead.id, "message": "已收到预约，机构老师将按您方便的时间联系"}


@router.post("/public/{slug}/chat", status_code=201)
def chat_start(slug: str, request: Request, session: Session = Depends(session_dep)):
    tenant = public_tenant(session, slug, True)
    limit(session, "chat-start:" + slug + ":" + request.client.host, 10, 3600)
    token = random_token()
    conversation = Conversation(tenant_id=tenant.id, token_hash=digest(token))
    session.add(conversation)
    session.flush()
    session.add(
        Message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            role="assistant",
            body="您好，欢迎了解课程。可以咨询课程内容、适合年级或试听安排。",
        )
    )
    session.commit()
    return {"id": conversation.id, "token": token}


@router.get("/public/{slug}/chat/{conversation_id}")
def chat_read(
    slug: str,
    conversation_id: str,
    x_public_token: str = Header(default=""),
    session: Session = Depends(session_dep),
):
    tenant = public_tenant(session, slug)
    conversation = public_conversation(
        session, tenant.id, conversation_id, x_public_token
    )
    return {
        "id": conversation.id,
        "state": conversation.state,
        "messages": messages(session, tenant.id, conversation.id),
    }


def queue_chat(session, tenant, conversation, question, request_id, actor="public"):
    from .worker import reserve_job, dispatch

    funding = tenant.settings.get("funding", "platform")
    try:
        reserve_job(session, tenant.id, request_id, "text_tokens", 20000, funding)
        run = AgentRun(
            tenant_id=tenant.id,
            kind="chat",
            request_id=request_id,
            actor_id=actor,
            funding=funding,
            input={"conversation_id": conversation.id, "question": question},
        )
        session.add(run)
        session.commit()
        dispatch("agent", tenant.id, run.id)
        return run
    except Exception:
        session.rollback()
        conversation = own(session, Conversation, tenant.id, conversation.id)
        conversation.state = "waiting_human"
        session.add(conversation)
        session.add(
            Message(
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                role="assistant",
                body="已收到您的问题，我会交给机构同事确认。您也可以通过预约表留下联系方式。",
            )
        )
        session.commit()
        return None


@router.post("/public/{slug}/chat/{conversation_id}")
def chat_send(
    slug: str,
    conversation_id: str,
    body: S.ChatInput,
    request: Request,
    x_public_token: str = Header(default=""),
    session: Session = Depends(session_dep),
):
    tenant = public_tenant(session, slug, True)
    limit(session, "chat-message:" + slug + ":" + request.client.host, 20, 60)
    conversation = public_conversation(
        session, tenant.id, conversation_id, x_public_token
    )
    count = session.exec(
        select(func.count())
        .select_from(Message)
        .where(
            Message.tenant_id == tenant.id, Message.conversation_id == conversation.id
        )
    ).one()
    if count >= 100:
        fail("CONVERSATION_LIMIT", "本次会话已达到上限，请联系机构")
    session.add(
        Message(
            tenant_id=tenant.id,
            conversation_id=conversation.id,
            role="user",
            body=body.body,
        )
    )
    if conversation.title == "新咨询":
        conversation.title = body.body[:40]
        session.add(conversation)
    if "人工" in body.body:
        conversation.state = "waiting_human"
        session.add(conversation)
    session.commit()
    if conversation.state == "bot":
        queue_chat(session, tenant, conversation, body.body, "chat:" + uid())
    return {
        "state": conversation.state,
        "messages": messages(session, tenant.id, conversation.id),
    }


@router.get("/conversations")
def conversations(i: Identity = Depends(scoped)):
    permit(i, "conversation.write")
    rows = i.session.exec(
        query(i.session, Conversation, i.tenant.id)
        .order_by(Conversation.created_at.desc())
        .limit(100)
    ).all()
    return [
        {
            k: v
            for k, v in c.model_dump().items()
            if k not in ("token_hash", "external_user")
        }
        for c in rows
        if conversation_visible(i, c)
    ]


@router.get("/conversations/{conversation_id}")
def conversation_detail(conversation_id: str, i: Identity = Depends(scoped)):
    permit(i, "conversation.write")
    conversation = check_conversation(
        i, own(i.session, Conversation, i.tenant.id, conversation_id)
    )
    reply_capability = None
    if conversation.account_id:
        from .social import capabilities

        account = own(i.session, SocialAccount, i.tenant.id, conversation.account_id)
        reply_capability = capabilities(account)[
            "comment_reply"
            if conversation.interaction_kind == "comment"
            else "message_reply"
        ]
    from .config import settings

    return {
        "id": conversation.id,
        "state": conversation.state,
        "channel": conversation.channel,
        "account_id": conversation.account_id,
        "reply_capability": reply_capability,
        "live_replies": settings().allow_live_replies,
        "source_work_id": conversation.source_work_id,
        "interaction_kind": conversation.interaction_kind,
        "owner_id": conversation.owner_id,
        "tags": conversation.tags,
        "lead_id": conversation.lead_id,
        "messages": messages(i.session, i.tenant.id, conversation.id),
    }


@router.post("/conversations/{conversation_id}/takeover")
def takeover(conversation_id: str, i: Identity = Depends(scoped)):
    from .social import LOCKS, cancel_pending
    import threading

    permit(i, "conversation.write")
    writable(i)
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
        c.state = "human"
        cancel_pending(i.session, i.tenant.id, c.id)
        i.session.add(c)
        audit(i.session, i.tenant.id, i.user.id, "chat.takeover", c.id)
        i.session.commit()
    return {"state": "human"}


@router.post("/conversations/{conversation_id}/resume")
def resume(conversation_id: str, i: Identity = Depends(scoped)):
    permit(i, "conversation.write")
    writable(i)
    conversation = check_conversation(
        i, own(i.session, Conversation, i.tenant.id, conversation_id)
    )
    conversation.state = "bot"
    i.session.add(conversation)
    i.session.commit()
    return {"state": "bot"}


@router.post("/conversations/{conversation_id}/reply")
def human_reply(conversation_id: str, body: S.ChatInput, i: Identity = Depends(scoped)):
    permit(i, "conversation.write")
    writable(i)
    conversation = check_conversation(
        i, own(i.session, Conversation, i.tenant.id, conversation_id)
    )
    if conversation.account_id:
        fail("SOCIAL_REPLY_REQUIRED", "请使用渠道回复或登记官方后台处理结果", 409)
    if conversation.state not in ("human", "waiting_human"):
        fail("TAKEOVER_REQUIRED", "请先接管会话")
    conversation.state = "human"
    message = Message(
        tenant_id=i.tenant.id,
        conversation_id=conversation.id,
        role="staff",
        body=body.body,
        delivery_state="pending" if conversation.channel == "wecom" else "local",
    )
    i.session.add(conversation)
    i.session.add(message)
    i.session.commit()
    if conversation.channel == "wecom":
        from .integrations.wecom import send_reply

        try:
            send_reply(i.session, i.tenant.id, conversation, body.body, message.id)
            message.delivery_state = "sent"
        except Exception:
            message.delivery_state = "unknown"
            i.session.add(message)
            i.session.commit()
            fail("DELIVERY_UNKNOWN", "发送结果待核实，请勿重复发送", 502)
        i.session.add(message)
        i.session.commit()
    return message


class ConversationEdit(S.Strict):
    owner_id: str | None = None
    tags: list[str] = S.Field(default_factory=list, max_length=20)
    lead_id: str | None = None


@router.patch("/conversations/{conversation_id}")
def edit_conversation(
    conversation_id: str, body: ConversationEdit, i: Identity = Depends(scoped)
):
    permit(i, "conversation.write")
    writable(i)
    conversation = check_conversation(
        i, own(i.session, Conversation, i.tenant.id, conversation_id)
    )
    if any(not t or len(t) > 30 for t in body.tags):
        fail("TAGS_INVALID", "标签需为1至30字")
    if body.owner_id is not None:
        permit(i, "lead.assign")
        if conversation.lead_id:
            fail("LINKED_LEAD_ASSIGNMENT", "关联线索的会话请在线索页转交负责人", 409)
        if body.owner_id:
            from .permissions import member_roles

            m = i.session.exec(
                select(Membership).where(
                    Membership.tenant_id == i.tenant.id,
                    Membership.user_id == body.owner_id,
                )
            ).first()
            if not member_roles(m) & {"owner", "admissions"}:
                fail("ASSIGNEE_INVALID", "请选择本机构有效招生人员")
        conversation.owner_id = body.owner_id
    if body.lead_id:
        Scope(i).own(body.lead_id, "lead")
    conversation.tags = list(dict.fromkeys(body.tags))
    if "lead_id" in body.model_fields_set:
        conversation.lead_id = body.lead_id
    i.session.add(conversation)
    audit(i.session, i.tenant.id, i.user.id, "chat.label", conversation.id)
    i.session.commit()
    return {"tags": conversation.tags, "lead_id": conversation.lead_id}

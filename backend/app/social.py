"""Capability-aware social inbox and at-most-once outbound replies."""

import json, hashlib, threading, re
from decimal import Decimal
from datetime import timedelta
from types import SimpleNamespace
from sqlalchemy import update
from sqlmodel import select
from fastapi import HTTPException
from .models import *
from .domain import query, own, audit, create_record, release_reservations
from .permissions import member_roles, identity_for, permit
from .auth import entitlement
from .config import settings
from .security import fail
from .integrations import publishing, aliyun

LOCKS = {}
LINKS = {
    "xiaohongshu": "https://creator.xiaohongshu.com/",
    "douyin": "https://creator.douyin.com/",
    "channels": "https://channels.weixin.qq.com/",
}
LABELS = {
    "login": "扫码登录",
    "publish_image": "图文发布",
    "publish_video": "视频发布",
    "metrics": "本人作品指标",
    "comment_read": "评论读取",
    "comment_reply": "评论回复",
    "message_read": "私信读取",
    "message_reply": "私信回复",
}


def capabilities(account):
    unsupported = set()
    if account.platform == "channels":
        unsupported = {
            "publish_image",
            "comment_read",
            "comment_reply",
            "message_read",
            "message_reply",
        }
    if account.platform == "xiaohongshu":
        unsupported = {"message_read", "message_reply"}
    out = {}
    for key, label in LABELS.items():
        state = (
            "unsupported"
            if key in unsupported
            else "requires_authorization"
            if account.platform == "douyin" and key.startswith(("comment", "message"))
            else "unverified"
        )
        reason = (
            "当前连接器不支持，请使用官方后台人工处理"
            if state == "unsupported"
            else "需要官方应用权限和账号授权"
            if state == "requires_authorization"
            else "尚未完成真实账号验证"
        )
        if key not in unsupported and account.config.get(
            "verified_capabilities", {}
        ).get(key):
            state = "available"
            reason = "连接器已验证"
        if account.status != "connected" and state == "available":
            state = "requires_authorization"
            reason = "请重新登录或授权"
        out[key] = {"label": label, "state": state, "reason": reason}
    return out


def cancel_pending(s, tenant_id, conversation_id):
    s.exec(
        update(SocialReply)
        .where(
            SocialReply.tenant_id == tenant_id,
            SocialReply.conversation_id == conversation_id,
            SocialReply.status.in_(["queued", "drafting"]),
        )
        .values(status="cancelled", error="人工已接管")
    )


def active_assignee(s, account):
    rid = account.config.get("assignee_id", "")
    m = (
        s.exec(
            select(Membership).where(
                Membership.tenant_id == account.tenant_id, Membership.user_id == rid
            )
        ).first()
        if rid
        else None
    )
    return rid if member_roles(m) & {"owner", "admissions"} else ""


def ingest(s, account, item):
    kind = item.get("kind")
    if (
        kind not in ("comment", "private_message")
        or not item.get("external_id")
        or not item.get("sender_id")
        or not item.get("body")
    ):
        fail("EVENT_INVALID", "互动缺少必要字段")
    if len(item["body"]) > 5000:
        fail("EVENT_INVALID", "消息过长")
    if item["sender_id"] == account.config.get("external_user_id"):
        return None
    prior = s.exec(
        query(s, SocialEvent, account.tenant_id).where(
            SocialEvent.account_id == account.id,
            SocialEvent.external_id == item["external_id"],
        )
    ).first()
    if prior:
        return prior
    thread = str(item.get("thread_id") or item["sender_id"])
    c = s.exec(
        query(s, Conversation, account.tenant_id).where(
            Conversation.account_id == account.id,
            Conversation.external_thread_id == thread,
            Conversation.interaction_kind == kind,
        )
    ).first()
    if not c:
        c = Conversation(
            tenant_id=account.tenant_id,
            token_hash="",
            channel=account.platform,
            account_id=account.id,
            external_thread_id=thread,
            source_work_id=item.get("work_id", ""),
            interaction_kind=kind,
            external_user=item["sender_id"],
            title=item.get("sender_name") or "新互动",
            owner_id=active_assignee(s, account),
        )
        s.add(c)
        s.flush()
    event = SocialEvent(
        tenant_id=account.tenant_id,
        account_id=account.id,
        external_id=str(item["external_id"]),
        kind=kind,
        thread_id=thread,
        work_id=str(item.get("work_id", "")),
        sender_id=str(item["sender_id"]),
        sender_name=str(item.get("sender_name", "")),
        body=item["body"],
        conversation_id=c.id,
        metadata_json=item.get("metadata", {}),
    )
    s.add(event)
    s.flush()
    s.add(
        Message(
            tenant_id=account.tenant_id,
            conversation_id=c.id,
            role="user",
            body=event.body,
            external_id="social:"
            + hashlib.sha256(
                (account.id + ":" + event.external_id).encode()
            ).hexdigest(),
        )
    )
    if (
        account.config.get("auto_reply")
        and c.state == "bot"
        and not event.metadata_json.get("manual")
    ):
        s.add(
            SocialReply(
                tenant_id=account.tenant_id,
                account_id=account.id,
                event_id=event.id,
                conversation_id=c.id,
                request_id="auto:" + event.id,
                actor_id=account.config.get("policy_actor_id", ""),
                automatic=True,
            )
        )
    else:
        c.state = "waiting_human"
        s.add(c)
    return event


def ready_policy(s, t, account):
    actor = account.config.get("policy_actor_id", "")
    if (
        not actor
        or not entitlement(s, t)["active"]
        or not account.config.get("auto_reply")
    ):
        fail("AUTOMATION_REVOKED", "机构自动回复授权不可用", 403)
    permit(identity_for(s, t, actor), "social.manage")


def send(s, account, event, reply):
    cap = "comment_reply" if event.kind == "comment" else "message_reply"
    state = capabilities(account)[cap]["state"]
    if state == "unsupported" or (reply.automatic and state != "available"):
        fail("CAPABILITY_UNAVAILABLE", "渠道未接通，转人工处理", 409)
    if not settings().allow_live_replies:
        fail("LIVE_REPLIES_DISABLED", "当前环境尚未启用真实回复", 503)
    if account.platform == "douyin":
        from .integrations.douyin import send_reply

        return send_reply(s, account, event, reply)
    return publishing.call(
        account.tenant_id,
        account.id,
        "comments-reply" if event.kind == "comment" else "messages-reply",
        {
            "platform": account.platform,
            "job_id": reply.id,
            "event_id": event.external_id,
            "comment_id": event.external_id,
            "thread_id": event.thread_id,
            "body": reply.body,
        },
        180,
    )


def process_reply(s, t, reply_id):
    from .operations import consultation

    consultation(t)
    r = own(s, SocialReply, t.id, reply_id)
    with LOCKS.setdefault((t.id, r.conversation_id), threading.RLock()):
        claimed = s.exec(
            update(SocialReply)
            .where(
                SocialReply.id == r.id,
                SocialReply.tenant_id == t.id,
                SocialReply.status == "queued",
            )
            .values(status="drafting", updated_at=now())
        )
        if claimed.rowcount != 1:
            s.rollback()
            return
        s.commit()
        s.refresh(r)
        account = own(s, SocialAccount, t.id, r.account_id)
        event = own(s, SocialEvent, t.id, r.event_id)
        c = own(s, Conversation, t.id, r.conversation_id)
        attempted = False
        draft_body = None
        draft_sources = []
        try:
            if r.automatic:
                ready_policy(s, t, account)
            else:
                from .permissions import check_conversation

                actor = identity_for(s, t, r.actor_id)
                permit(actor, "conversation.write")
                check_conversation(actor, c)
            if r.automatic and c.state != "bot":
                r.status = "cancelled"
                r.error = "人工已接管"
                s.add(r)
                s.commit()
                return
            if not r.body:
                from .agents import knowledge, ChatAnswer, CHAT_INSTRUCTIONS
                from .worker import reserve_job, agent_call, finish_usage

                sources = [
                    x
                    for x in knowledge(s, t.id, event.body)
                    if (record := s.get(Record, x["id"]))
                    and record.tenant_id == t.id
                    and record.data.get("approved")
                    and record.version == x["version"]
                ]
                if not sources or any(
                    word in event.body for word in ("退款", "投诉", "人工")
                ):
                    fail("HUMAN_REQUIRED", "需要人工核对")
                funding = t.settings.get("funding", "platform")
                key = "reply:" + r.id
                reserve_job(s, t.id, key, "text_tokens", 20000, funding, purpose="legacy")
                output, used = agent_call(
                    s,
                    t.id,
                    SimpleNamespace(funding=funding, request_id=key),
                    CHAT_INSTRUCTIONS,
                    json.dumps(
                        {"question": event.body, "sources": sources}, ensure_ascii=False
                    ),
                    ChatAnswer,
                )
                finish_usage(s, t.id, key, "text_tokens", used, funding)
                s.commit()
                r.body = output.answer
                r.sources = [x for x in sources if x["id"] in output.source_ids]
                draft_body = r.body
                draft_sources = r.sources
                if (
                    output.needs_human
                    or not output.source_ids
                    or not set(output.source_ids) <= {x["id"] for x in sources}
                ):
                    fail("HUMAN_REQUIRED", "回答需要人工核对")
                s.add(r)
                s.commit()
            if r.draft_only or event.metadata_json.get("manual"):
                r.status = "draft"
                s.add(r)
                s.commit()
                return
            # The conversation lock orders takeover against sending. A persisted intent is never replayed.
            c = s.exec(
                query(s, Conversation, t.id)
                .where(Conversation.id == c.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).one()
            s.refresh(r)
            s.refresh(account)
            if r.status != "drafting" or (r.automatic and c.state != "bot"):
                r.status = "cancelled"
                s.add(r)
                s.commit()
                return
            if r.automatic:
                ready_policy(s, t, account)
                from .domain import policy_notes

                if not r.sources or policy_notes(s, t.id, "", r.body, []):
                    fail("FACT_REVIEW_REQUIRED", "回复事实或表述需要人工核对")
                for source in r.sources:
                    record = s.exec(
                        query(s, Record, t.id)
                        .where(Record.id == source["id"])
                        .execution_options(populate_existing=True)
                        .with_for_update()
                    ).first()
                    if (
                        not record
                        or record.tenant_id != t.id
                        or not record.data.get("approved")
                        or record.version != source["version"]
                    ):
                        fail("SOURCE_CHANGED", "资料版本已变更，请人工核对")
                facts = " ".join(x["body"] for x in r.sources)
                allowed = {
                    Decimal(value)
                    for value in re.findall(r"(\d+(?:\.\d+)?)\s*元", facts)
                }
                if any(
                    Decimal(value) not in allowed
                    for value in re.findall(r"(\d+(?:\.\d+)?)\s*元", r.body)
                ):
                    fail("PRICE_CONFLICT", "回复金额与引用资料不一致")
            else:
                from .permissions import check_conversation

                check_conversation(identity_for(s, t, r.actor_id), c)
            r.status = "sending"
            r.updated_at = now()
            s.add(r)
            s.flush()
            # Keep the row lock until delivery finishes; takeover cannot race past this send.
            attempted = True
            result = send(s, account, event, r)
            r.status = (
                "sent"
                if result.get("status") == "succeeded" and result.get("external_id")
                else "unknown"
            )
            r.external_id = str(result.get("external_id", ""))
            r.error = "" if r.status == "sent" else "发送结果待核实，请勿重复发送"
            if r.status == "sent":
                cap = "comment_reply" if event.kind == "comment" else "message_reply"
                account.config = {
                    **account.config,
                    "verified_capabilities": {
                        **account.config.get("verified_capabilities", {}),
                        cap: True,
                    },
                }
                s.add(account)
            else:
                c.state = "waiting_human"
                s.add(c)
            s.add(
                Message(
                    tenant_id=t.id,
                    conversation_id=c.id,
                    role="assistant" if r.automatic else "staff",
                    body=r.body,
                    sources=r.sources,
                    external_id="reply:" + r.id,
                    delivery_state=r.status,
                )
            )
            s.add(r)
            s.commit()
        except Exception as exc:
            s.rollback()
            s.refresh(r)
            s.refresh(c)
            if draft_body is not None:
                r.body = draft_body
                r.sources = draft_sources
            detail = (
                exc.detail
                if isinstance(exc, HTTPException) and isinstance(exc.detail, dict)
                else {}
            )
            r.error = detail.get("message", "回复失败或结果待核实，请人工处理")
            # sending is durable in the connector's journal even if the database transaction is interrupted.
            r.status = "unknown" if attempted else "draft"
            c.state = "waiting_human"
            s.add(c)
            s.add(r)
            s.commit()


def tick_social(s, t):
    from .operations import enabled

    if not enabled(t):
        return
    if not entitlement(s, t)["active"]:
        return
    accounts = s.exec(query(s, SocialAccount, t.id)).all()
    for a in accounts:
        if not a.config.get("auto_reply") or a.status != "connected":
            continue
        due = a.config.get("next_poll_at", "")
        if due and as_utc(__import__("datetime").datetime.fromisoformat(due)) > now():
            continue
        try:
            ready_policy(s, t, a)
            cap = capabilities(a)["comment_read"]["state"]
            if cap != "available":
                continue
            if a.platform == "douyin":
                from .integrations.douyin import poll_comments

                events = poll_comments(s, a)
            else:
                events = publishing.call(
                    t.id, a.id, "comments-list", {"platform": a.platform}, 120
                ).get("events", [])
            for item in events:
                ingest(s, a, item)
            a.config = {
                **a.config,
                "next_poll_at": (now() + timedelta(seconds=60)).isoformat(),
                "poll_failures": 0,
            }
            s.add(a)
            s.commit()
        except Exception:
            s.rollback()
            s.refresh(a)
            attempt = min(int(a.config.get("poll_failures", 0)) + 1, 8)
            if attempt >= 3:
                a.status = "waiting_authorization"
            a.config = {
                **a.config,
                "poll_failures": attempt,
                "next_poll_at": (
                    now() + timedelta(seconds=min(3600, 60 * 2**attempt))
                ).isoformat(),
                "last_poll_error": "连接器需要检查，请验证登录与权限",
            }
            s.add(a)
            s.commit()
    for r in s.exec(
        query(s, SocialReply, t.id).where(SocialReply.status == "queued")
    ).all():
        process_reply(s, t, r.id)
    # A crashed paid draft/send is left for a human, never replayed.
    for r in s.exec(
        query(s, SocialReply, t.id).where(
            SocialReply.status.in_(["drafting", "sending"]),
            SocialReply.updated_at < now() - timedelta(minutes=10),
        )
    ).all():
        r.status = "unknown"
        r.error = "任务中断，请核实生成和发送记录"
        s.add(r)
    s.commit()

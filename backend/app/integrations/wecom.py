"""WeCom Customer Service: authenticated callback, cursor sync and bounded official APIs."""

import base64, hashlib, hmac, struct, time, secrets
from datetime import timedelta
from defusedxml import ElementTree as ET
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import httpx
from sqlmodel import select
from ..models import *
from ..domain import query, own
from ..security import decrypt, encrypt, fail, digest
from ..db import set_scope

_cache = {}


def integration(session, tenant_id):
    row = session.exec(
        query(session, Integration, tenant_id).where(
            Integration.provider == "wecom", Integration.active == True
        )
    ).first()
    if not row:
        fail("WECOM_UNCONFIGURED", "机构尚未配置企业微信客服", 503)
    secret = decrypt(tenant_id, row.secret_cipher)
    if not isinstance(secret, dict):
        fail("WECOM_CONFIG_INVALID", "企微配置需要重新保存")
    return row, secret


def verify_signature(token, timestamp, nonce, encrypted, signature):
    try:
        if abs(time.time() - int(timestamp)) > 600:
            fail("SIGNATURE_EXPIRED", "回调已过期", 403)
    except ValueError:
        fail("SIGNATURE_INVALID", "回调签名无效", 403)
    expected = hashlib.sha1(
        "".join(sorted([token, timestamp, nonce, encrypted])).encode()
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        fail("SIGNATURE_INVALID", "回调签名无效", 403)


def decrypt_message(aes_key, encrypted, corpid):
    try:
        key = base64.b64decode(aes_key + "=")
        if len(key) != 32:
            raise ValueError()
        raw = base64.b64decode(encrypted, validate=True)
        decryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).decryptor()
        data = decryptor.update(raw) + decryptor.finalize()
        padding = data[-1]
        if not 1 <= padding <= 32 or data[-padding:] != bytes([padding]) * padding:
            raise ValueError()
        data = data[:-padding]
        size = struct.unpack("!I", data[16:20])[0]
        body = data[20 : 20 + size]
        receiver = data[20 + size :].decode()
        if not hmac.compare_digest(receiver, corpid):
            raise ValueError()
        return body.decode()
    except Exception:
        fail("CIPHERTEXT_INVALID", "回调密文无效", 403)


def access_token(session, tenant_id):
    row, secret = integration(session, tenant_id)
    key = (tenant_id, digest(row.secret_cipher))
    if key in _cache and _cache[key][1] > time.time():
        return _cache[key][0]
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        response = client.get(
            "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
            params={"corpid": row.config["corpid"], "corpsecret": secret["secret"]},
        )
        response.raise_for_status()
        data = response.json()
    if data.get("errcode", 0) != 0 or not data.get("access_token"):
        fail("WECOM_AUTH_FAILED", "企微授权失败，请检查企业配置", 502)
    _cache[key] = (
        data["access_token"],
        time.time() + min(data.get("expires_in", 7200) - 120, 7000),
    )
    return data["access_token"]


def api(session, tenant_id, path, body):
    token = access_token(session, tenant_id)
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        response = client.post(
            "https://qyapi.weixin.qq.com/cgi-bin/kf/" + path,
            params={"access_token": token},
            json=body,
        )
        response.raise_for_status()
        data = response.json()
    if data.get("errcode", 0) != 0:
        fail("WECOM_API_FAILED", "企微请求未成功，请核对渠道权限与会话状态", 502)
    return data


def send_reply(session, tenant_id, conversation, body, message_id=None):
    open_kfid, external_user = conversation.external_user.split(":", 1)
    result = api(
        session,
        tenant_id,
        "send_msg",
        {
            "touser": external_user,
            "open_kfid": open_kfid,
            "msgid": message_id or uid(),
            "msgtype": "text",
            "text": {"content": body[:2000]},
        },
    )
    return result


def sync_messages(session, tenant_id, event):
    row, secret = integration(session, tenant_id)
    event_data = decrypt(tenant_id, event["event_cipher"])
    token = event_data["token"]
    open_kfid = event_data["open_kfid"]
    cursor = row.config.get("cursor", "")
    tenant = session.get(Tenant, tenant_id)
    for _ in range(10):
        data = api(
            session,
            tenant_id,
            "sync_msg",
            {
                "cursor": cursor,
                "token": token,
                "limit": 100,
                "voice_format": 0,
                "open_kfid": open_kfid,
            },
        )
        for msg in data.get("msg_list", []):
            external_id = str(msg.get("msgid", ""))
            if (
                not external_id
                or msg.get("origin") != 3
                or msg.get("msgtype") != "text"
            ):
                continue
            session.exec(
                select(Tenant)
                .where(Tenant.id == tenant_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            ).one()
            prior = session.exec(
                query(session, Message, tenant_id).where(
                    Message.external_id == external_id
                )
            ).first()
            if prior:
                conversation = own(
                    session, Conversation, tenant_id, prior.conversation_id
                )
                existing_run = session.exec(
                    query(session, AgentRun, tenant_id).where(
                        AgentRun.request_id == "wecom-chat:" + external_id
                    )
                ).first()
                if not existing_run and conversation.state == "bot":
                    from ..routes_public import queue_chat

                    queue_chat(
                        session,
                        tenant,
                        conversation,
                        prior.body,
                        "wecom-chat:" + external_id,
                        "webhook",
                    )
                session.commit()
                continue
            user = msg.get("external_userid", "")
            if not user:
                session.commit()
                continue
            external = open_kfid + ":" + user
            conversation = session.exec(
                query(session, Conversation, tenant_id).where(
                    Conversation.external_user == external,
                    Conversation.channel == "wecom",
                )
            ).first()
            if not conversation:
                conversation = Conversation(
                    tenant_id=tenant_id,
                    token_hash=digest(uid()),
                    channel="wecom",
                    external_user=external,
                    title="企微客户咨询",
                )
                session.add(conversation)
                session.flush()
            body = str(msg.get("text", {}).get("content", ""))[:2000]
            if "人工" in body:
                conversation.state = "waiting_human"
                session.add(conversation)
            session.add(
                Message(
                    tenant_id=tenant_id,
                    conversation_id=conversation.id,
                    role="user",
                    body=body,
                    external_id=external_id,
                )
            )
            session.commit()
            if conversation.state == "bot":
                from ..routes_public import queue_chat

                queue_chat(
                    session,
                    tenant,
                    conversation,
                    body,
                    "wecom-chat:" + external_id,
                    "webhook",
                )
        cursor = data.get("next_cursor", cursor)
        row.config = {**row.config, "cursor": cursor}
        session.add(row)
        session.commit()
        if not data.get("has_more"):
            break

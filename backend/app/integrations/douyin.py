"""Official Douyin adapter; endpoints are fixed and tokens stay server-side."""

import json, hashlib, hmac
import httpx
from sqlmodel import select
from ..models import Integration, PublishJob
from ..domain import query
from ..security import decrypt, fail

BASE = "https://open.douyin.com"


def credential(s, a):
    row = s.exec(
        query(s, Integration, a.tenant_id).where(
            Integration.provider == "douyin:" + a.id, Integration.active == True
        )
    ).first()
    if not row:
        fail("OFFICIAL_AUTH_REQUIRED", "尚未配置本账号的抖音官方授权", 409)
    return row, decrypt(a.tenant_id, row.secret_cipher)


def api(secret, path, params=None, body=None):
    with httpx.Client(timeout=30, follow_redirects=False) as c:
        r = c.request(
            "POST" if body is not None else "GET",
            BASE + path,
            params=params,
            headers={"access-token": secret["access_token"]},
            json=body,
        )
        r.raise_for_status()
        out = r.json()
    data = out.get("data", out)
    if str(data.get("error_code", "0")) != "0":
        fail(
            "OFFICIAL_PERMISSION_REQUIRED",
            "官方接口拒绝访问，请核对账号授权与接口权限",
            409,
        )
    return data


def poll_comments(s, a):
    row, secret = credential(s, a)
    ids = s.exec(
        query(s, PublishJob, a.tenant_id).where(
            PublishJob.account_id == a.id, PublishJob.status == "succeeded"
        )
    ).all()
    events = []
    if not ids:
        fail("WORK_REQUIRED", "请先绑定一条已核实的本人作品，再验证评论读取", 409)
    for job in ids:
        data = api(
            secret,
            "/item/comment/list/",
            {
                "open_id": row.config["open_id"],
                "item_id": job.external_id,
                "count": 50,
                "cursor": 0,
            },
        )
        for item in data.get("list", []):
            user = item.get("user", {})
            events.append(
                {
                    "external_id": str(item["comment_id"]),
                    "kind": "comment",
                    "thread_id": str(item["comment_id"]),
                    "work_id": job.external_id,
                    "sender_id": str(user.get("open_id") or item.get("user_id") or ""),
                    "sender_name": user.get("nickname", ""),
                    "body": item.get("text", ""),
                }
            )
    return events


def send_reply(s, a, event, reply):
    row, secret = credential(s, a)
    if event.kind == "comment":
        job = s.exec(
            query(s, PublishJob, a.tenant_id).where(
                PublishJob.account_id == a.id,
                PublishJob.external_id == event.work_id,
                PublishJob.status == "succeeded",
            )
        ).first()
        if not job:
            fail("WORK_NOT_OWNED", "仅能回复该授权账号已核实的作品评论", 403)
        out = api(
            secret,
            "/item/comment/reply/",
            {"open_id": row.config["open_id"]},
            {
                "item_id": event.work_id,
                "comment_id": event.external_id,
                "content": reply.body,
            },
        )
        return (
            {"status": "succeeded", "external_id": str(out["comment_id"])}
            if out.get("comment_id")
            else {"status": "unknown"}
        )
    # Access is withheld until a current account-specific private-message API has been verified.
    fail(
        "CAPABILITY_UNVERIFIED",
        "当前抖音私信发送接口尚待账号专项验证，请使用官方后台",
        409,
    )


def verify_webhook(secret, raw, signature):
    expected = hashlib.sha1(secret["client_secret"].encode() + raw).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        fail("SIGNATURE_INVALID", "回调验签失败", 403)

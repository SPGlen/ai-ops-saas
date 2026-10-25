"""Only talks to a trusted publisher gateway. No arbitrary MCP endpoints from tenants."""

import hmac, hashlib
import httpx
from ..config import settings
from ..security import fail


def token(tenant_id):
    return hmac.new(
        settings().publisher_token.encode(), tenant_id.encode(), hashlib.sha256
    ).hexdigest()


def call(tenant_id, account_id, operation, body=None, timeout=180):
    cfg = settings()
    if not cfg.publisher_url or not cfg.publisher_token:
        fail("PUBLISHER_UNCONFIGURED", "发布执行节点尚未连接", 503)
    if any("/" in x or len(x) > 100 for x in (tenant_id, account_id)):
        fail("ACCOUNT_INVALID", "发布账号标识无效")
    from .mcp_client import Client, MCPError

    operation_tools = {
        "status": "check_login",
        "search": "search_topics",
        "login": "start_login",
        "login-image": "login_qrcode",
        "publish": "publish_content",
        "result": "query_result",
        "metrics": "collect_metrics",
        "comments-list": "list_comments",
        "comments-reply": "reply_comment",
        "messages-list": "list_messages",
        "messages-reply": "reply_message",
    }
    if operation not in operation_tools:
        fail("OPERATION_INVALID", "不支持的连接器操作")
    platform = (body or {}).get("platform", "")
    client = Client(
        cfg.publisher_url.rstrip("/") + f"/mcp/{tenant_id}/{account_id}/{platform}",
        {"X-Publisher-Token": token(tenant_id)},
        timeout,
    )
    try:
        client.initialize()
        return client.call(operation_tools[operation], body or {})
    except (httpx.HTTPError, MCPError):
        fail("PUBLISHER_UNAVAILABLE", "连接器暂不可用；已提交任务请先核实结果", 503)


def check_login(tenant_id, account):
    return call(tenant_id, account.id, "status", {"platform": account.platform}, 30)


def start_login(tenant_id, account):
    return call(tenant_id, account.id, "login", {"platform": account.platform}, 45)


def login_image(tenant_id, account):
    return call(
        tenant_id, account.id, "login-image", {"platform": account.platform}, 30
    )


def publish(tenant_id, account, job, content, assets):
    if not settings().allow_live_publish:
        fail("LIVE_PUBLISH_DISABLED", "真实发布尚未启用，请由部署管理员配置", 503)
    return call(
        tenant_id,
        account.id,
        "publish",
        {
            "platform": account.platform,
            "job_id": job.id,
            "title": content.title,
            "body": content.body,
            "assets": assets,
            "content_hash": content.content_hash,
        },
        300,
    )


def query_result(tenant_id, account, job):
    return call(
        tenant_id,
        account.id,
        "result",
        {
            "platform": account.platform,
            "job_id": job.id,
            "external_id": job.external_id,
        },
        60,
    )


def collect_metrics(tenant_id, account, job):
    return call(
        tenant_id,
        account.id,
        "metrics",
        {
            "platform": account.platform,
            "external_id": job.external_id,
            "external_url": job.external_url,
        },
        90,
    )

"""One service instance per institution. State encrypted at rest; no DB or model credentials."""

import os, json, hmac, hashlib, base64, asyncio, time, ipaddress, socket, re, tempfile
from pathlib import Path
from contextlib import asynccontextmanager
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from playwright.async_api import async_playwright
from .platforms import URLS, logged_in, prepare, publication_response

ROOT = Path(os.environ.get("PUB_STATE_DIR", "/state"))
ROOT.mkdir(parents=True, exist_ok=True)
TENANT = os.environ.get("PUB_TENANT_ID", "")
TOKEN = os.environ.get("PUB_TOKEN", "")
KEY = os.environ.get("PUB_KEY", "")
if not TENANT or len(TOKEN) < 32 or len(KEY) < 32:
    raise RuntimeError("Per-tenant publisher credentials required")
cipher = Fernet(base64.urlsafe_b64encode(hashlib.sha256(KEY.encode()).digest()))
contexts = {}
context_lifecycle_lock = asyncio.Lock()
locks = {}
dns_cache = {}
browser = None


def safe(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise HTTPException(400, "Invalid identifier")
    return value


def read(name):
    path = ROOT / (safe(name) + ".enc")
    return json.loads(cipher.decrypt(path.read_bytes())) if path.exists() else None


def write(name, data):
    target = ROOT / (safe(name) + ".enc")
    temp = target.with_suffix(".tmp")
    temp.write_bytes(cipher.encrypt(json.dumps(data).encode()))
    temp.chmod(0o600)
    temp.replace(target)


def authorize(tenant, token):
    if tenant != TENANT or not hmac.compare_digest(token, TOKEN):
        raise HTTPException(403, "Forbidden")


async def block_private(route):
    from urllib.parse import urlparse

    url = urlparse(route.request.url)
    host = url.hostname
    if url.scheme not in ("https", "wss") or not host:
        return await route.abort()
    if host not in dns_cache or dns_cache[host][1] < time.time():
        try:
            values = await asyncio.to_thread(socket.getaddrinfo, host, url.port or 443)
            allowed = all(ipaddress.ip_address(v[4][0]).is_global for v in values)
            dns_cache[host] = (allowed, time.time() + 60)
        except Exception:
            allowed = False
    else:
        allowed = dns_cache[host][0]
    if not allowed:
        return await route.abort()
    await route.continue_()


async def page_for(account, platform, home=False):
    async with context_lifecycle_lock:
        return await _page_for(account, platform, home)


async def _page_for(account, platform, home=False):
    if account not in contexts:
        cap = max(1, int(os.environ.get("PUB_BROWSER_MAX_CONTEXTS", "2")))
        if len(contexts) >= cap:
            idle = sorted(((aid, value) for aid,value in contexts.items() if not locks.get(aid, asyncio.Lock()).locked()), key=lambda pair: pair[1][2])
            if not idle:
                raise HTTPException(429, "Browser capacity busy; wait for running account tasks")
            aid,(old_context,*_) = idle[0]
            write("account-"+aid, await old_context.storage_state())
            await old_context.close()
            contexts.pop(aid,None)
        state = read("account-" + account)
        context = await browser.new_context(
            storage_state=state,
            viewport={"width": 1280, "height": 900},
            accept_downloads=False,
        )
        await context.route("**/*", block_private)
        page = await context.new_page()
        contexts[account] = (context, page, time.time(), platform)
        await page.goto(
            URLS[platform]["upload"], wait_until="domcontentloaded", timeout=60000
        )
    context, page, _, saved_platform = contexts[account]
    if saved_platform != platform:
        raise HTTPException(409, "Platform mismatch")
    contexts[account] = (context, page, time.time(), platform)
    return context, page


async def reap():
    while True:
        await asyncio.sleep(30)
        for account, (context, page, last, platform) in list(contexts.items()):
            if (
                last < time.time() - 900
                and not locks.get(account, asyncio.Lock()).locked()
            ):
                write("account-" + account, await context.storage_state())
                await context.close()
                contexts.pop(account, None)


@asynccontextmanager
async def lifespan(app):
    global browser
    async with async_playwright() as p:
        xhs.executable = p.chromium.executable_path
        browser = await p.chromium.launch(headless=True, chromium_sandbox=True)
        task = asyncio.create_task(reap())
        yield
        task.cancel()
        for account, (context, *_) in contexts.items():
            write("account-" + account, await context.storage_state())
            await context.close()
        await xhs.close()
        await browser.close()


app = FastAPI(docs_url=None, openapi_url=None, lifespan=lifespan)
from .xhs_runtime import Runtime

xhs = Runtime(read, write)


class Asset(BaseModel):
    name: str
    mime: str
    data: str = Field(max_length=280000000)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: str
    job_id: str = ""
    content_hash: str = ""
    title: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=15000)
    assets: list[Asset] = Field(default_factory=list, max_length=20)
    external_id: str = ""
    external_url: str = ""
    comment_id: str = ""
    thread_id: str = ""
    event_id: str = ""
    work_ids: list[str] = Field(default_factory=list, max_length=2000)
    keyword: str = Field(default="", max_length=80)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/{tenant}/{account}/{operation}")
async def action(
    tenant: str,
    account: str,
    operation: str,
    body: Input,
    x_publisher_token: str = Header(default=""),
):
    authorize(tenant, x_publisher_token)
    safe(account)
    if body.platform not in URLS:
        raise HTTPException(400, "Unknown platform")
    if operation not in (
        "status",
        "search",
        "login",
        "login-image",
        "publish",
        "result",
        "metrics",
        "comments-list",
        "comments-reply",
    ):
        raise HTTPException(404, "Unknown operation")
    async with locks.setdefault(account, asyncio.Lock()):
        if body.platform == "xiaohongshu":
            return await xhs_action(account, operation, body)
        if operation.startswith("comments-"):
            raise HTTPException(
                409,
                {
                    "code": "CAPABILITY_UNSUPPORTED",
                    "message": "请使用已授权官方评论接口",
                },
            )
        if operation == "result":
            return read("job-" + safe(body.job_id)) or {"status": "unknown"}
        if operation == "metrics":
            # Collect only the authenticated account's exact post, never public search results.
            context, page = await page_for(account, body.platform)
            await page.goto(
                URLS[body.platform]["manage"], wait_until="domcontentloaded"
            )
            if not await logged_in(page, body.platform):
                return {"available": False, "reason": "login_required"}
            links = await page.locator("a[href]").evaluate_all(
                '(nodes)=>nodes.map(n=>({href:n.href,text:n.closest("tr,article,[class*=item]")?.innerText||""}))'
            )
            row = next(
                (
                    x
                    for x in links
                    if body.external_id and body.external_id in x["href"]
                ),
                None,
            )
            if not row:
                return {
                    "available": False,
                    "metrics": {
                        k: None
                        for k in ("plays", "likes", "comments", "shares", "saves")
                    },
                }
            metrics = {}
            for key, label in [
                ("plays", "播放"),
                ("likes", "点赞"),
                ("comments", "评论"),
                ("shares", "分享"),
                ("saves", "收藏"),
            ]:
                match = re.search(
                    label + r"\s*[:：]?\s*(\d+)(?![.\d万千])", row["text"]
                )
                metrics[key] = int(match[1]) if match else None
            return {
                "available": any(v is not None for v in metrics.values()),
                "metrics": metrics,
            }
        context, page = await page_for(account, body.platform)
        if operation == "login":
            await page.goto(
                URLS[body.platform]["upload"], wait_until="domcontentloaded"
            )
            return {
                "status": "connected"
                if await logged_in(page, body.platform)
                else "waiting_authorization"
            }
        if operation == "login-image":
            await page.wait_for_timeout(1500)
            return {
                "image": "data:image/png;base64,"
                + base64.b64encode(await page.screenshot()).decode()
            }
        if operation == "status":
            status = (
                "connected"
                if await logged_in(page, body.platform)
                else "waiting_authorization"
            )
            if status == "connected":
                write("account-" + account, await context.storage_state())
            identity = ""
            if status == "connected" and body.platform == "douyin":
                links = await page.locator('a[href*="douyin.com/user/"]').all()
                for link in links:
                    if await link.is_visible():
                        href = await link.get_attribute("href") or ""
                        match = re.fullmatch(r"https://www\.douyin\.com/user/([A-Za-z0-9_-]{10,200})/?", href)
                        if match:
                            identity = match.group(1)
                            break
            return {"status": status, "external_user_id": identity, "identity_namespace": "public", "identity_verified": bool(identity), "reason": "" if identity else "未读取到可靠账号ID，无人值守发布等待真实账号联调"}
        job_key = "job-" + safe(body.job_id)
        prior = read(job_key)
        if prior:
            if prior.get("content_hash") != body.content_hash:
                raise HTTPException(409, "Job fingerprint mismatch")
            return prior
        if os.environ.get("PUB_ALLOW_LIVE", "false").lower() != "true":
            raise HTTPException(
                403,
                {"code": "LIVE_PUBLISH_DISABLED", "message": "发布节点真实发布未启用"},
            )
        if not await logged_in(page, body.platform):
            raise HTTPException(
                409, {"code": "LOGIN_REQUIRED", "message": "请扫码登录"}
            )
        result = {
            "status": "unknown",
            "content_hash": body.content_hash,
            "account": account,
            "submitted": False,
        }
        # Durable intent before the first external side effect. Existing intent is never replayed.
        write(job_key, result)
        try:
            with tempfile.TemporaryDirectory(prefix="publish-") as tmp:
                files = []
                for i, asset in enumerate(body.assets):
                    extension = {
                        "image/png": ".png",
                        "image/jpeg": ".jpg",
                        "image/webp": ".webp",
                        "video/mp4": ".mp4",
                    }.get(asset.mime)
                    if not extension:
                        continue
                    raw = base64.b64decode(asset.data, validate=True)
                    if len(raw) > 200 * 1024 * 1024:
                        raise ValueError("ASSET_TOO_LARGE")
                    path = Path(tmp) / (str(i) + extension)
                    path.write_bytes(raw)
                    files.append(path)
                button = await prepare(
                    page, body.platform, body.title, body.body, files
                )
                seen = []
                pending = set()

                async def response_seen(response):
                    if response.request.method != "POST":
                        return
                    try:
                        data = await response.json()
                        match = publication_response(body.platform, response.url, data)
                        if match:
                            seen.append(match)
                    except Exception:
                        pass

                def on_response(response):
                    task = asyncio.create_task(response_seen(response))
                    pending.add(task)
                    task.add_done_callback(pending.discard)

                page.on("response", on_response)
                try:
                    result["submitted"] = True
                    write(job_key, result)
                    await button.click(timeout=10000)
                    for _ in range(45):
                        if seen:
                            break
                        await asyncio.sleep(1)
                    if seen:
                        result.update(seen[0])
                finally:
                    page.remove_listener("response", on_response)
                write("account-" + account, await context.storage_state())
        except Exception as error:
            # Logs and responses contain a code, never copy, credentials or browser state.
            code = (
                str(error)
                if str(error)
                in (
                    "LOGIN_REQUIRED",
                    "TITLE_TOO_LONG",
                    "CHANNELS_VIDEO_REQUIRED",
                    "ACCOUNT_REVIEW_REQUIRED",
                    "PUBLISH_FORM_INCOMPLETE",
                    "ASSET_TOO_LARGE",
                )
                else "PUBLISH_RESULT_UNKNOWN"
            )
            result["error_code"] = code
        write(job_key, result)
        return result


def deep_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from deep_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from deep_nodes(child)


def profile_posts(profile):
    posts = {}
    for node in deep_nodes(profile):
        card = node.get("noteCard", node.get("note_card", {}))
        rid = node.get("id", node.get("note_id", ""))
        title = (
            card.get("displayTitle", card.get("display_title", card.get("title", "")))
            if isinstance(card, dict)
            else ""
        )
        if (
            isinstance(rid, str)
            and re.fullmatch(r"[a-zA-Z0-9_-]{8,100}", rid)
            and title
        ):
            posts[rid] = title
    return posts


async def xhs_action(account, operation, body):
    from .mcp_client import MCPError

    if operation in ("status", "login"):
        out = await xhs.call(account, "check_login_status", {})
        logged = out.get("is_logged_in") is True or (
            "已登录" in out.get("text", "") and "未登录" not in out.get("text", "")
        )
        if operation == "login" and not logged:
            await xhs.call(account, "get_login_qrcode", {})
        identity = ""
        if logged:
            try:
                profile = await xhs.call(account, "get_my_profile", {})
                basic = profile.get("userBasicInfo", profile.get("user_basic_info", {}))
                identity = str(basic.get("userId", basic.get("user_id", "")))
            except Exception:
                pass
        return {"status": "connected" if logged else "waiting_authorization", "external_user_id": identity, "identity_verified": bool(identity), "identity_namespace": "public", "reason": "" if identity else "尚未取得可核验的平台账号ID"}

    if operation == "search":
        out = await xhs.call(account, "search_feeds", {"keyword": body.keyword})
        items = []
        for item in out.get("feeds", [])[:20]:
            card = item.get("noteCard", {})
            note_id = item.get("id")
            title = card.get("displayTitle", "")
            if note_id and title:
                items.append({"title": title, "url": "https://www.xiaohongshu.com/explore/"+str(note_id), "published_at": None})
        return {"available": bool(items), "items": items}
    if operation == "login-image":
        return await xhs.call(account, "get_login_qrcode", {})
    if operation == "comments-list":
        profile = await xhs.call(account, "get_my_profile", {})
        own = profile_posts(profile)
        basic = profile.get("userBasicInfo", profile.get("user_basic_info", {}))
        self_id = basic.get("userId", basic.get("user_id", ""))
        out = await xhs.call(
            account, "list_notifications", {"tab": "mentions", "limit": 50}
        )
        if not isinstance(out.get("items"), list):
            raise MCPError("NOTIFICATION_SCHEMA_UNVERIFIED")
        events = []
        for item in out.get("items", []):
            if self_id and item.get("from", {}).get("user_id") == self_id:
                continue
            if (
                item.get("feed_id") not in own
                or not item.get("comment_id")
                or not item.get("comment_text")
            ):
                continue
            events.append(
                {
                    "external_id": item["comment_id"],
                    "kind": "comment",
                    "thread_id": item["comment_id"],
                    "work_id": item["feed_id"],
                    "sender_id": item.get("from", {}).get("user_id", ""),
                    "sender_name": item.get("from", {}).get("nickname", ""),
                    "body": item["comment_text"],
                    "feed_xsec_token": item.get("feed_xsec_token", ""),
                }
            )
        write("xhs-events-" + account, {e["external_id"]: e for e in events})
        return {"events": events, "available": True, "external_user_id": self_id}
    if operation == "comments-reply":
        event = (read("xhs-events-" + account) or {}).get(body.comment_id)
        if not event:
            raise HTTPException(404, "Comment is not a verified incoming interaction")
        if os.environ.get("PUB_ALLOW_REPLIES", "false").lower() != "true":
            raise HTTPException(403, "Live replies disabled")
        key = "reply-" + safe(body.job_id)
        prior = read(key)
        fingerprint = hashlib.sha256(body.body.encode()).hexdigest()
        if prior:
            if prior.get("fingerprint") != fingerprint:
                raise HTTPException(409, "Reply fingerprint mismatch")
            return prior
        result = {"status": "unknown", "fingerprint": fingerprint}
        write(key, result)
        out = await xhs.call(
            account,
            "reply_notification",
            {"comment_id": body.comment_id, "content": body.body},
        )
        # A UI success string is not an external delivery receipt.
        if out.get("reply_id"):
            result.update(status="succeeded", external_id=str(out["reply_id"]))
        elif event.get("feed_xsec_token"):
            profile = await xhs.call(account, "get_my_profile", {})
            basic = profile.get("userBasicInfo", profile.get("user_basic_info", {}))
            self_id = basic.get("userId", basic.get("user_id", ""))
            detail = await xhs.call(
                account,
                "get_feed_detail",
                {
                    "feed_id": event["work_id"],
                    "xsec_token": event["feed_xsec_token"],
                    "load_all_comments": True,
                    "limit": 50,
                    "click_more_replies": True,
                },
            )
            matches = []
            for parent in deep_nodes(detail):
                if parent.get("id") != body.comment_id:
                    continue
                for node in deep_nodes(parent):
                    user = node.get("userInfo", node.get("user_info", {}))
                    if (
                        self_id
                        and user.get("userId", user.get("user_id")) == self_id
                        and node.get("content") == body.body
                        and node.get("id") != body.comment_id
                    ):
                        matches.append(node["id"])
            if len(set(matches)) == 1:
                result.update(status="succeeded", external_id=matches[0])
        write(key, result)
        return result
    if operation == "metrics":
        return {
            "available": False,
            "reason": "指标需实际作品验证",
            "metrics": {
                k: None for k in ("plays", "likes", "comments", "shares", "saves")
            },
        }
    key = "job-" + safe(body.job_id)
    prior = read(key)
    if operation == "result":
        if not prior:
            return {"status": "unknown"}
        if prior.get("status") == "succeeded":
            return prior
        posts = profile_posts(await xhs.call(account, "get_my_profile", {}))
        matches = [
            rid
            for rid, title in posts.items()
            if rid not in prior.get("before", []) and title == prior.get("title")
        ]
        if len(matches) == 1:
            prior.update(
                status="succeeded",
                external_id=matches[0],
                external_url="https://www.xiaohongshu.com/explore/" + matches[0],
            )
            write(key, prior)
        return prior
    if prior:
        if prior.get("content_hash") != body.content_hash:
            raise HTTPException(409, "Job fingerprint mismatch")
        return prior
    if os.environ.get("PUB_ALLOW_LIVE", "false").lower() != "true":
        raise HTTPException(403, "Live publishing disabled")
    before = profile_posts(await xhs.call(account, "get_my_profile", {}))
    result = {
        "status": "unknown",
        "before": list(before),
        "title": body.title,
        "content_hash": body.content_hash,
        "submitted": True,
    }
    write(key, result)
    with tempfile.TemporaryDirectory(prefix="xhs-media-") as directory:
        files = []
        for idx, a in enumerate(body.assets):
            ext = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/webp": ".webp",
                "video/mp4": ".mp4",
            }.get(a.mime)
            if not ext:
                raise HTTPException(400, "Unsupported media")
            raw = base64.b64decode(a.data, validate=True)
            if len(raw) > 200 * 1024 * 1024:
                raise HTTPException(413, "Media too large")
            path = Path(directory) / (str(idx) + ext)
            path.write_bytes(raw)
            files.append(str(path))
        video = next((p for p in files if p.endswith(".mp4")), None)
        await xhs.call(
            account,
            "publish_with_video" if video else "publish_content",
            {
                "title": body.title,
                "content": body.body,
                **({"video": video} if video else {"images": files}),
            },
        )
    return await xhs_action(account, "result", body)


MCP_TOOLS = {
    "check_login": "status",
    "search_topics": "search",
    "start_login": "login",
    "login_qrcode": "login-image",
    "publish_content": "publish",
    "query_result": "result",
    "collect_metrics": "metrics",
    "list_comments": "comments-list",
    "reply_comment": "comments-reply",
}


@app.get("/mcp/{tenant}/{account}/{platform}")
async def mcp_get(
    tenant: str,
    account: str,
    platform: str,
    request: Request,
    x_publisher_token: str = Header(default=""),
):
    authorize(tenant, x_publisher_token)
    if request.headers.get("origin"):
        raise HTTPException(403, "Browser origins are not permitted")
    return Response(status_code=405)


@app.post("/mcp/{tenant}/{account}/{platform}")
async def mcp(
    tenant: str,
    account: str,
    platform: str,
    request: Request,
    x_publisher_token: str = Header(default=""),
):
    authorize(tenant, x_publisher_token)
    safe(account)
    if request.headers.get("origin"):
        raise HTTPException(403, "Browser origins are not permitted")
    if platform not in URLS:
        raise HTTPException(400, "Unknown platform")
    raw = await request.body()
    if len(raw) > 290 * 1024 * 1024:
        raise HTTPException(413, "Payload too large")
    try:
        rpc = json.loads(raw)
    except ValueError:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            }
        )
    if (
        not isinstance(rpc, dict)
        or rpc.get("jsonrpc") != "2.0"
        or not isinstance(rpc.get("method"), str)
        or not isinstance(rpc.get("params", {}), dict)
    ):
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request"},
            }
        )
    rid = rpc.get("id")
    method = rpc.get("method")
    params = rpc.get("params", {})
    if rid is None and method != "notifications/initialized":
        return Response(status_code=202)

    def response(result):
        return {"jsonrpc": "2.0", "id": rid, "result": result}

    if method == "initialize":
        return response(
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "zhiying-publisher", "version": "0.2.0"},
            }
        )
    if method == "notifications/initialized":
        return Response(status_code=202)
    if method == "ping":
        return response({})
    tools = {
        k: v
        for k, v in MCP_TOOLS.items()
        if platform == "xiaohongshu" or (not v.startswith("comments-") and v != "search")
    }
    if os.environ.get("PUB_ALLOW_LIVE", "false").lower() != "true":
        tools.pop("publish_content", None)
    if os.environ.get("PUB_ALLOW_REPLIES", "false").lower() != "true":
        tools.pop("reply_comment", None)
    if method == "tools/list":
        return response(
            {
                "tools": [
                    {
                        "name": name,
                        "description": op,
                        "inputSchema": Input.model_json_schema(),
                    }
                    for name, op in tools.items()
                ]
            }
        )
    if method != "tools/call" or params.get("name") not in tools:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": -32601, "message": "Method or tool unavailable"},
        }
    args = params.get("arguments", {})
    if not isinstance(args, dict):
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": -32602, "message": "Invalid tool arguments"},
        }
    if args.get("platform", platform) != platform:
        raise HTTPException(403, "Platform mismatch")
    try:
        out = await action(
            tenant,
            account,
            tools[params["name"]],
            Input(**{**args, "platform": platform}),
            x_publisher_token,
        )
        return response(
            {
                "content": [
                    {"type": "text", "text": json.dumps(out, ensure_ascii=False)}
                ],
                "structuredContent": out,
                "isError": False,
            }
        )
    except Exception:
        return response(
            {
                "content": [
                    {
                        "type": "text",
                        "text": "CONNECTOR_OPERATION_FAILED: query pending results before retrying",
                    }
                ],
                "isError": True,
            }
        )

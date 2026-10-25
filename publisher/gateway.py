"""Trusted provisioning gateway, deployed on a separate rootless Docker publisher host."""

import os, hmac, hashlib, re, asyncio, time
import httpx
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import JSONResponse

app = FastAPI(docs_url=None, openapi_url=None)
MASTER = os.environ.get("PUB_MASTER_KEY", "")
if len(MASTER) < 32:
    raise RuntimeError("PUB_MASTER_KEY must be at least 32 characters")
SOCKET = os.environ.get("PUB_DOCKER_SOCKET", "/run/docker.sock")
IMAGE = os.environ.get("PUB_BROWSER_IMAGE", "care-ops-publisher:0.4.0-rc1")
NETWORK = os.environ.get("PUB_NETWORK", "ops_browser")
LOCKS = {}


def derive(tenant, purpose=""):
    return hmac.new(
        MASTER.encode(), (purpose + tenant).encode(), hashlib.sha256
    ).hexdigest()


def docker():
    return httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(uds=SOCKET),
        base_url="http://docker",
        timeout=45,
    )


async def ensure(tenant):
    name = "ops-browser-" + tenant
    async with LOCKS.setdefault(tenant, asyncio.Lock()), docker() as client:
        info = await client.get("/info")
        if info.status_code != 200 or not any(
            "rootless" in x for x in info.json().get("SecurityOptions", [])
        ):
            raise HTTPException(503, "A dedicated rootless Docker daemon is required")
        result = await client.get("/containers/" + name + "/json")
        if result.status_code == 404:
            containers = (
                await client.get("/containers/json", params={"all": "true"})
            ).json()
            if sum(
                x.get("Labels", {}).get("ops.publisher") == "tenant" for x in containers
            ) >= int(os.environ.get("PUB_MAX_TENANTS", "20")):
                raise HTTPException(503, "Publisher capacity reached")
            payload = {
                "Image": IMAGE,
                "User": "1000:1000",
                "Labels": {"ops.publisher": "tenant", "ops.tenant": tenant},
                "Env": [
                    "PUB_TENANT_ID=" + tenant,
                    "PUB_TOKEN=" + derive(tenant),
                    "PUB_KEY=" + derive(tenant, "encryption:"),
                    "PUB_ALLOW_LIVE=" + os.environ.get("PUB_ALLOW_LIVE", "false"),
                    "PUB_ALLOW_REPLIES=" + os.environ.get("PUB_ALLOW_REPLIES", "false"),
                    "PUB_STATE_DIR=/state",
                    "PUB_BROWSER_MAX_CONTEXTS=" + os.environ.get("PUB_BROWSER_MAX_CONTEXTS", "2"),
                    "PUB_XHS_MAX_ACTIVE=" + os.environ.get("PUB_XHS_MAX_ACTIVE", "2"),
                ],
                "ExposedPorts": {"8901/tcp": {}},
                "HostConfig": {
                    "ReadonlyRootfs": True,
                    "CapDrop": ["ALL"],
                    "SecurityOpt": [
                        "no-new-privileges:true",
                        "seccomp=" + open("/etc/ops/chromium-seccomp.json").read(),
                    ],
                    "Memory": 1610612736,
                    "NanoCpus": 1500000000,
                    "PidsLimit": 256,
                    "ShmSize": 268435456,
                    "NetworkMode": NETWORK,
                    "Binds": ["ops-browser-state-" + tenant + ":/state"],
                    "Tmpfs": {"/tmp": "rw,nosuid,size=512m"},
                    "RestartPolicy": {"Name": "unless-stopped"},
                },
                "NetworkingConfig": {"EndpointsConfig": {NETWORK: {"Aliases": [name]}}},
            }
            result = await client.post(
                "/containers/create", params={"name": name}, json=payload
            )
            if result.status_code != 201:
                raise HTTPException(503, "Cannot provision tenant browser")
        elif result.status_code != 200:
            raise HTTPException(503, "Publisher host unavailable")
        result = await client.post("/containers/" + name + "/start")
        if result.status_code not in (204, 304):
            raise HTTPException(503, "Cannot start tenant browser")
    for attempt in range(15):
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                response = await client.get("http://" + name + ":8901/health")
                if response.status_code == 200:
                    return name
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)
    raise HTTPException(
        503, "Tenant browser warming up; check Chromium sandbox support"
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/{tenant}/{account}/{operation}")
async def proxy(
    tenant: str,
    account: str,
    operation: str,
    request: Request,
    x_publisher_token: str = Header(default=""),
):
    if not all(re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", v) for v in (tenant, account)):
        raise HTTPException(400, "Invalid identifier")
    if not hmac.compare_digest(derive(tenant), x_publisher_token):
        raise HTTPException(403, "Forbidden")
    if operation not in (
        "login",
        "status",
        "login-image",
        "publish",
        "result",
        "metrics",
    ):
        raise HTTPException(404, "Unknown operation")
    raw = await request.body()
    if len(raw) > 290 * 1024 * 1024:
        raise HTTPException(413, "Request too large")
    name = await ensure(tenant)
    # The server identity is derived, never supplied by the client.
    try:
        async with httpx.AsyncClient(timeout=300, follow_redirects=False) as client:
            response = await client.post(
                "http://"
                + name
                + ":8901/v1/"
                + tenant
                + "/"
                + account
                + "/"
                + operation,
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Publisher-Token": derive(tenant),
                },
            )
            return JSONResponse(response.json(), status_code=response.status_code)
    except httpx.HTTPError:
        raise HTTPException(
            502,
            {
                "code": "PUBLISH_RESULT_UNKNOWN",
                "message": "发布节点未返回结果，请先核实",
            },
        )


@app.api_route("/mcp/{tenant}/{account}/{platform}", methods=["POST", "GET"])
async def mcp_proxy(
    tenant: str,
    account: str,
    platform: str,
    request: Request,
    x_publisher_token: str = Header(default=""),
):
    if request.headers.get("origin"):
        raise HTTPException(403, "Browser origins are not permitted")
    if not all(
        re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", v) for v in (tenant, account)
    ) or platform not in ("xiaohongshu", "douyin", "channels"):
        raise HTTPException(400, "Invalid route")
    if not hmac.compare_digest(derive(tenant), x_publisher_token):
        raise HTTPException(403, "Forbidden")
    if request.method == "GET":
        return JSONResponse({}, 405)
    raw = await request.body()
    if len(raw) > 290 * 1024 * 1024:
        raise HTTPException(413, "Payload too large")
    name = await ensure(tenant)
    async with httpx.AsyncClient(timeout=360, follow_redirects=False) as c:
        r = await c.post(
            f"http://{name}:8901/mcp/{tenant}/{account}/{platform}",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "X-Publisher-Token": derive(tenant),
            },
        )
    return JSONResponse(r.json() if r.content else {}, r.status_code)

"""Loopback-only development gateway. Production must use the rootless Docker gateway."""

import os, json, asyncio, hmac, hashlib, re, socket, sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from app.config import settings, ROOT

cfg = settings()
if cfg.production:
    raise RuntimeError("Development gateway is prohibited in production")
if len(cfg.publisher_token) < 32:
    raise RuntimeError("Configure a publisher token first")
processes = {}
lock = asyncio.Lock()


def token(tenant, purpose=""):
    return hmac.new(
        cfg.publisher_token.encode(), (purpose + tenant).encode(), hashlib.sha256
    ).hexdigest()


@asynccontextmanager
async def lifespan(app):
    yield
    for proc, port in processes.values():
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), 10)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()


app = FastAPI(lifespan=lifespan, docs_url=None, openapi_url=None)


async def ensure(tenant):
    async with lock:
        if tenant in processes and processes[tenant][0].returncode is None:
            return processes[tenant][1]
        if len(processes) >= 3:
            raise HTTPException(
                503, "Development gateway allows at most 3 institutions"
            )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            in (
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "HOME",
                "SSL_CERT_FILE",
                "SSL_CERT_DIR",
            )
        }
        env.update(
            PUB_TENANT_ID=tenant,
            PUB_TOKEN=token(tenant),
            PUB_KEY=token(tenant, "encryption:"),
            PUB_STATE_DIR=str(cfg.data_dir / "publisher" / tenant),
            PUB_XHS_BINARY=str(ROOT / ".local" / "xiaohongshu-mcp.exe")
            if sys.platform == "win32"
            else str(ROOT / ".local" / "xiaohongshu-mcp"),
            PUB_ALLOW_LIVE="true" if cfg.allow_live_publish else "false",
            PUB_ALLOW_REPLIES="true" if cfg.allow_live_replies else "false",
            PLAYWRIGHT_BROWSERS_PATH=str(ROOT / ".local" / "browsers"),
        )
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "uvicorn",
            "publisher.service:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
            "--no-proxy-headers",
            cwd=ROOT,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        processes[tenant] = (proc, port)
        import httpx

        for _ in range(30):
            if proc.returncode is not None:
                raise HTTPException(
                    503, "Publisher startup failed; check browser installation"
                )
            try:
                async with httpx.AsyncClient(timeout=2) as c:
                    if (
                        await c.get(f"http://127.0.0.1:{port}/health")
                    ).status_code == 200:
                        return port
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        raise HTTPException(503, "Publisher startup timed out")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "environment": "development",
        "live_publish": cfg.allow_live_publish,
        "live_replies": cfg.allow_live_replies,
    }


@app.api_route("/mcp/{tenant}/{account}/{platform}", methods=["POST", "GET"])
async def proxy(tenant: str, account: str, platform: str, request: Request):
    if request.headers.get("origin"):
        raise HTTPException(403, "Browser origins prohibited")
    if not all(
        re.fullmatch(r"[A-Za-z0-9_-]{1,100}", v) for v in (tenant, account)
    ) or platform not in ("xiaohongshu", "douyin", "channels"):
        raise HTTPException(400, "Invalid route")
    if not hmac.compare_digest(
        token(tenant), request.headers.get("X-Publisher-Token", "")
    ):
        raise HTTPException(403, "Forbidden")
    if request.method == "GET":
        return Response(status_code=405)
    raw = await request.body()
    if len(raw) > 290 * 1024 * 1024:
        raise HTTPException(413, "Request too large")
    port = await ensure(tenant)
    import httpx

    async with httpx.AsyncClient(timeout=360, follow_redirects=False) as c:
        r = await c.post(
            f"http://127.0.0.1:{port}/mcp/{tenant}/{account}/{platform}",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "X-Publisher-Token": token(tenant),
            },
        )
    return Response(
        content=r.content,
        status_code=r.status_code,
        media_type=r.headers.get("content-type", "application/json"),
    )

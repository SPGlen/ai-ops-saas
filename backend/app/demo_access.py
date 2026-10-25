"""Browser-friendly showcase gate, separate from institution authentication."""
import hashlib
import hmac
import json
import secrets
from urllib.parse import urlsplit
from fastapi import HTTPException
from sqlmodel import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from .db import engine
from .models import now
from .security import limit

COOKIE = "ops_demo_access"
MAX_AGE = 8 * 3600
HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"}

def signature(cfg, stamp, nonce):
    value = f"showcase-access:{cfg.public_url}:{cfg.demo_access_code}:{stamp}:{nonce}"
    return hmac.new(cfg.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()

def token(cfg):
    stamp = str(int(now().timestamp()))
    nonce = secrets.token_urlsafe(24)
    return f"{stamp}.{nonce}.{signature(cfg, stamp, nonce)}"

def authorized(request, cfg):
    value = request.cookies.get(COOKIE, "")
    try:
        stamp, nonce, signed = value.split(".")
        age = now().timestamp() - int(stamp)
        return -30 <= age < MAX_AGE and len(nonce) == 32 and hmac.compare_digest(signed, signature(cfg, stamp, nonce))
    except (ValueError, TypeError):
        return False

def error(code, message, status):
    return JSONResponse({"detail": {"code": code, "message": message}}, status_code=status, headers=HEADERS)

async def unlock(request, cfg):
    if request.method != "POST":
        return error("METHOD_NOT_ALLOWED", "请在页面中输入演示访问码。", 405)
    # JSON plus an exact Origin check keeps credentials and sessions same-origin.
    if request.headers.get("origin", "").rstrip("/") != cfg.public_url.rstrip("/"):
        return error("DEMO_ORIGIN_INVALID", "请从演示网址打开页面后重试。", 403)
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        return error("DEMO_REQUEST_INVALID", "请使用页面中的访问码输入框。", 415)
    raw = bytearray()
    async for part in request.stream():
        raw.extend(part)
        if len(raw) > 1024:
            return error("BODY_TOO_LARGE", "访问码过长，请检查后重试。", 413)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        return error("DEMO_REQUEST_INVALID", "请求格式错误，请刷新页面。", 400)
    code = data.get("code") if isinstance(data, dict) else None
    if not isinstance(code, str) or not 1 <= len(code) <= 256:
        return error("DEMO_ACCESS_INVALID", "请输入正确的演示访问码。", 401)
    try:
        with Session(engine()) as session:
            limit(session, "showcase-access:" + (request.client.host if request.client else "unknown"), 20, 300)
    except HTTPException as exc:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=HEADERS)
    if not hmac.compare_digest(code.strip().encode(), cfg.demo_access_code.encode()):
        return error("DEMO_ACCESS_INVALID", "访问码不正确，请核对后重试。", 401)
    response = JSONResponse({"ok": True}, headers=HEADERS)
    response.set_cookie(COOKIE, token(cfg), max_age=MAX_AGE, httponly=True, secure=urlsplit(cfg.public_url).scheme == "https", samesite="strict", path="/")
    return response

def page():
    nonce = secrets.token_urlsafe(18)
    html = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>知营 · 企业演示访问</title>
<style nonce="NONCE">
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f6ef;color:#204536;font-family:Microsoft YaHei,system-ui,sans-serif;padding:24px}main{width:100%;max-width:460px;background:#fff;border:1px solid #e1e7da;border-radius:20px;padding:38px;box-shadow:0 16px 70px #214c3510}.brand{display:flex;align-items:center;gap:12px;margin-bottom:38px}.mark{background:#d9edb5;color:#194735;font-size:24px;font-weight:700;padding:8px 12px;border-radius:12px}.brand strong{display:block;font-size:22px}.brand small{font-size:10px;letter-spacing:2px;color:#6d8470}.eyebrow{font-size:12px;color:#809469;letter-spacing:2px}h1{font-size:26px;margin:12px 0}p{font-size:14px;line-height:1.9;color:#75836e;margin:12px 0 26px}label{display:block;font-size:14px;margin-bottom:10px;font-weight:600}input{width:100%;border:1px solid #d7e1cf;border-radius:9px;padding:13px;font:16px system-ui;background:#fbfcf8;color:#234d38}input:focus{outline:2px solid #bad194;outline-offset:1px}button{width:100%;padding:14px;margin-top:20px;border:0;border-radius:9px;background:#20533d;color:#fff;font:600 15px Microsoft YaHei,system-ui;cursor:pointer}button:disabled{opacity:.6;cursor:wait}.error{min-height:22px;color:#a13f34;font-size:13px;margin-top:10px}.hint{font-size:12px;margin:24px 0 0;color:#8a9681;line-height:1.8}@media(max-width:500px){main{padding:28px}h1{font-size:24px}}
</style></head><body><main><div class="brand"><span class="mark">知</span><div><strong>知营</strong><small>ZHIYING · EDUCATION OPS</small></div></div><span class="eyebrow">企业体验 · 独立演示环境</span><h1>欢迎体验机构运营工作台</h1><p>请输入演示负责人提供的访问码。验证后选择岗位，即可体验招生、学员、教务与财务。</p><form id="demo-access-form"><label for="access-code">演示访问码</label><input id="access-code" name="code" type="password" required maxlength="256" autocomplete="off" spellcheck="false" autofocus placeholder="粘贴演示访问码"><div id="error" class="error" role="alert" aria-live="polite"></div><button type="submit" id="enter">验证并进入演示</button></form><p class="hint">本演示仅包含虚构资料。访问码验证在当前浏览器有效，无需用户名；链接到期后请联系演示负责人。</p></main>
<script nonce="NONCE">
const form=document.getElementById('demo-access-form'),button=document.getElementById('enter'),error=document.getElementById('error');
form.addEventListener('submit',async event=>{event.preventDefault();error.textContent='';button.disabled=true;button.textContent='正在验证…';try{const response=await fetch('/__demo/access',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:form.elements.code.value})});const result=await response.json();if(!response.ok)throw new Error(result.detail?.message||'暂时无法验证，请稍后重试。');location.replace('/');}catch(e){error.textContent=e.message;button.disabled=false;button.textContent='验证并进入演示';}});
</script></body></html>'''
    return HTMLResponse(html.replace("NONCE", nonce), headers={**HEADERS, "Content-Security-Policy": f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'", "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff"})

async def gate(scope, receive, cfg):
    request = Request(scope, receive)
    if request.url.path == "/__demo/access":
        return await unlock(request, cfg)
    # Readiness exposes no business data and lets loopback startup probes work
    # without sending a Secure browser cookie over plain HTTP.
    if request.method in ("GET", "HEAD") and request.url.path == "/api/v1/health":
        return None
    if authorized(request, cfg):
        return None
    if request.method in ("GET", "HEAD") and (request.url.path == "/" or "text/html" in request.headers.get("accept", "")):
        return page()
    return error("DEMO_ACCESS_REQUIRED", "请先在演示首页验证访问码。", 401)

import json
from urllib.parse import urlparse
import httpx
from pydantic import BaseModel
from ..config import settings
from ..models import Integration
from ..domain import query
from ..security import decrypt, fail
from sqlmodel import select


def config(session, tenant_id, funding):
    cfg = settings()
    if funding == "byok":
        integration = session.exec(
            query(session, Integration, tenant_id).where(
                Integration.provider == "aliyun", Integration.active == True
            )
        ).first()
        if not integration:
            fail("KEY_REQUIRED", "请先配置机构的百炼 Key", 503)
        key = decrypt(tenant_id, integration.secret_cipher)
        base = integration.config.get("base_url", cfg.aliyun_base_url)
    else:
        key = cfg.aliyun_api_key
        base = cfg.aliyun_base_url
    if not key:
        fail("MODEL_UNCONFIGURED", "尚未配置模型凭证", 503)
    host = urlparse(base).hostname or ""
    if not base.startswith("https://") or not (
        host in ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com")
        or host.endswith(".maas.aliyuncs.com")
    ):
        fail("MODEL_HOST_INVALID", "仅支持已允许的百炼官方域名")
    return key, base.rstrip("/").removesuffix("/compatible-mode/v1")


def text_agent(
    session,
    tenant_id,
    funding,
    instructions,
    prompt,
    output_type,
    model_name=None,
    media=None,
):
    import asyncio
    from pydantic_ai import Agent, PromptedOutput, BinaryContent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from pydantic_ai.usage import UsageLimits
    from openai import AsyncOpenAI

    key, base = config(session, tenant_id, funding)
    text_base = settings().aliyun_text_base_url if funding == "platform" else ""
    if funding == "byok":
        row = session.exec(
            query(session, Integration, tenant_id).where(
                Integration.provider == "aliyun", Integration.active == True
            )
        ).first()
        text_base = row.config.get("text_base_url", "") if row else ""
    if text_base:
        base = text_base.rstrip("/").removesuffix("/compatible-mode/v1")
    host = urlparse(base).hostname or ""
    if not base.startswith("https://") or not (
        host in ("dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com")
        or host.endswith(".maas.aliyuncs.com")
    ):
        fail("MODEL_HOST_INVALID", "模型地址不在供应商白名单中")

    async def invoke():
        async with AsyncOpenAI(
            base_url=base + "/compatible-mode/v1",
            api_key=key,
            max_retries=0,
            timeout=90,
        ) as sdk:
            provider = OpenAIProvider(openai_client=sdk)
            model = OpenAIChatModel(
                model_name or settings().text_model, provider=provider
            )
            agent = Agent(
                model,
                output_type=PromptedOutput(output_type) if media else output_type,
                instructions=instructions,
                model_settings={
                    "temperature": 0.35,
                    "max_tokens": 3000,
                    **(
                        {"extra_body": {"enable_thinking": False}}
                        if (model_name or settings().text_model).startswith("qwen3")
                        else {}
                    ),
                },
                retries=0,
            )
            content = (
                [prompt]
                + [BinaryContent(data=raw, media_type=mime) for raw, mime in media]
                if media
                else prompt
            )
            result = await agent.run(
                content,
                usage_limits=UsageLimits(request_limit=1, total_tokens_limit=20000),
            )
            return result.output, result.usage().total_tokens or None

    return asyncio.run(invoke())


def api(session, tenant_id, funding, method, path, body=None):
    key, base = config(session, tenant_id, funding)
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    if method == "POST" and "video-generation" in path:
        headers["X-DashScope-Async"] = "enable"
    with httpx.Client(
        timeout=httpx.Timeout(90, connect=15), follow_redirects=False
    ) as client:
        response = client.request(method, base + path, headers=headers, json=body)
        if response.status_code in (401, 403):
            fail("MODEL_KEY_REJECTED", "模型授权被拒绝，请检查 Key 与地域", 502)
        if response.status_code == 400:
            fail(
                "MODEL_REQUEST_REJECTED",
                "供应商拒绝了任务参数，请核对模型、地域、比例和时长",
                400,
            )
        if response.status_code == 429:
            fail("MODEL_RATE_LIMITED", "供应商限流，任务等待重试", 429)
        response.raise_for_status()
        return response.json()


def create_image(session, tenant_id, funding, prompt, ratio):
    size = {
        "9:16": "928*1664",
        "16:9": "1664*928",
        "1:1": "1328*1328",
        "3:4": "1104*1472",
    }[ratio]
    body = {
        "model": settings().image_model,
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {"size": size, "n": 1, "watermark": True},
    }
    data = api(
        session,
        tenant_id,
        funding,
        "POST",
        "/api/v1/services/aigc/multimodal-generation/generation",
        body,
    )
    content = (
        data.get("output", {})
        .get("choices", [{}])[0]
        .get("message", {})
        .get("content", [])
    )
    urls = [part["image"] for part in content if "image" in part]
    if not urls:
        fail("IMAGE_RESULT_INVALID", "图片任务未返回媒体结果", 502)
    return urls, data.get("request_id", "")


def submit_video(session, tenant_id, funding, prompt, parameters):
    body = {
        "model": settings().video_model,
        "input": {"prompt": prompt},
        "parameters": {
            "resolution": "720P",
            "ratio": parameters.get("ratio", "9:16"),
            "duration": parameters.get("duration", 10),
            "watermark": True,
            "prompt_extend": True,
        },
    }
    data = api(
        session,
        tenant_id,
        funding,
        "POST",
        "/api/v1/services/aigc/video-generation/video-synthesis",
        body,
    )
    if not data.get("output", {}).get("task_id"):
        fail("VIDEO_RESULT_INVALID", "视频任务未返回任务编号", 502)
    return data["output"]["task_id"], data.get("request_id", "")


def video_status(session, tenant_id, funding, task_id):
    if not task_id or len(task_id) > 100 or "/" in task_id:
        fail("TASK_ID_INVALID", "任务编号无效")
    return api(session, tenant_id, funding, "GET", "/api/v1/tasks/" + task_id)


def embed(session, tenant_id, funding, texts, return_usage=False):
    data = api(
        session,
        tenant_id,
        funding,
        "POST",
        "/api/v1/services/embeddings/text-embedding/text-embedding",
        {
            "model": settings().embedding_model,
            "input": {"texts": texts},
            "parameters": {"dimension": 1024, "text_type": "document"},
        },
    )
    embeddings = [x["embedding"] for x in data["output"]["embeddings"]]
    used = data.get("usage", {}).get("total_tokens") or data.get("usage", {}).get(
        "input_tokens"
    )
    return (embeddings, used) if return_usage else embeddings


def speech(session, tenant_id, funding, text):
    if not 1 <= len(text) <= 600:
        fail("NARRATION_INVALID", "Narration must contain 1 to 600 characters")
    result = api(
        session,
        tenant_id,
        funding,
        "POST",
        "/api/v1/services/aigc/multimodal-generation/generation",
        {
            "model": settings().tts_model,
            "input": {"text": text, "voice": "Cherry", "language_type": "Chinese"},
        },
    )
    url = result.get("output", {}).get("audio", {}).get("url")
    if not url:
        fail("SPEECH_RESULT_INVALID", "Speech service returned no audio", 502)
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    if parts.scheme == "http":
        url = urlunsplit(parts._replace(scheme="https"))
    return url, result.get("usage", {}).get("characters", len(text))

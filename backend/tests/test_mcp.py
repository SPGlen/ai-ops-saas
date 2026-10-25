"""MCP contract tests use a fake transport and never log in or publish externally."""

import asyncio, base64, importlib, json
import pytest, httpx
from fastapi.testclient import TestClient
from publisher.mcp_client import Client, MCPError


@pytest.fixture
def publisher_app(tmp_path, monkeypatch):
    monkeypatch.setenv("PUB_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("PUB_TENANT_ID", "tenant")
    monkeypatch.setenv("PUB_TOKEN", "t" * 64)
    monkeypatch.setenv("PUB_KEY", "k" * 64)
    monkeypatch.setenv("PUB_ALLOW_LIVE", "false")
    monkeypatch.setenv("PUB_ALLOW_REPLIES", "false")
    from publisher import service

    service = importlib.reload(service)
    return service, TestClient(service.app)


def rpc(c, method, params=None, token="t" * 64, platform="xiaohongshu", origin=None):
    headers = {"X-Publisher-Token": token}
    if origin:
        headers["Origin"] = origin
    return c.post(
        "/mcp/tenant/account/" + platform,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers=headers,
    )


def test_mcp_handshake_filtered_tools_and_origin_auth(publisher_app):
    service, c = publisher_app
    assert rpc(c, "initialize").json()["result"]["protocolVersion"] == "2025-06-18"
    tools = rpc(c, "tools/list").json()["result"]["tools"]
    names = {x["name"] for x in tools}
    assert (
        "check_login" in names
        and "publish_content" not in names
        and "reply_comment" not in names
        and "reply_message" not in names
    )
    channel_names = {
        x["name"]
        for x in rpc(c, "tools/list", platform="channels").json()["result"]["tools"]
    }
    assert "list_comments" not in channel_names
    assert rpc(c, "tools/list", token="wrong").status_code == 403
    assert rpc(c, "tools/list", origin="https://untrusted.example").status_code == 403
    assert (
        c.post(
            "/mcp/foreign/account/xiaohongshu",
            json={},
            headers={"X-Publisher-Token": "t" * 64},
        ).status_code
        == 403
    )
    assert (
        rpc(c, "tools/call", {"name": "arbitrary_shell", "arguments": {}}).json()[
            "error"
        ]["code"]
        == -32601
    )


def test_mcp_tool_input_is_bound_to_platform(publisher_app, monkeypatch):
    service, c = publisher_app
    calls = []

    async def action(tenant, account, operation, body, token):
        calls.append((tenant, account, operation))
        return {"status": "connected"}

    monkeypatch.setattr(service, "action", action)
    r = rpc(
        c,
        "tools/call",
        {"name": "check_login", "arguments": {"platform": "xiaohongshu"}},
    )
    assert r.json()["result"]["structuredContent"]["status"] == "connected"
    assert (
        rpc(
            c,
            "tools/call",
            {"name": "check_login", "arguments": {"platform": "douyin"}},
        ).status_code
        == 403
    )
    assert (
        rpc(c, "tools/call", {"name": "check_login", "arguments": []}).json()["error"][
            "code"
        ]
        == -32602
    )
    assert len(calls) == 1


def test_upstream_publish_text_without_new_work_is_unknown_and_never_replayed(
    publisher_app, monkeypatch
):
    service, c = publisher_app
    monkeypatch.setenv("PUB_ALLOW_LIVE", "true")
    calls = []

    class Upstream:
        async def call(self, account, name, args):
            calls.append(name)
            if name == "get_my_profile":
                return {
                    "feeds": [
                        {"id": "oldwork123456", "noteCard": {"displayTitle": "same"}}
                    ]
                }
            return {"text": "发布完成"}

    monkeypatch.setattr(service, "xhs", Upstream())
    body = service.Input(
        platform="xiaohongshu",
        job_id="samejob",
        content_hash="hash",
        title="new work",
        body="copy",
        assets=[
            service.Asset(
                name="x.png",
                mime="image/png",
                data=base64.b64encode(b"image-fixture").decode(),
            )
        ],
    )
    first = asyncio.run(service.xhs_action("acct", "publish", body))
    second = asyncio.run(service.xhs_action("acct", "publish", body))
    assert first["status"] == second["status"] == "unknown"
    assert calls.count("publish_content") == 1
    assert "external_id" not in first


def test_upstream_new_unique_own_work_is_reconciled(publisher_app, monkeypatch):
    service, c = publisher_app
    monkeypatch.setenv("PUB_ALLOW_LIVE", "true")
    profiles = []

    class Upstream:
        async def call(self, account, name, args):
            if name == "get_my_profile":
                profiles.append(1)
                return {
                    "feeds": []
                    if len(profiles) == 1
                    else [
                        {
                            "id": "newwork123456",
                            "noteCard": {"displayTitle": "new work"},
                        }
                    ]
                }
            return {"text": "发布完成"}

    monkeypatch.setattr(service, "xhs", Upstream())
    body = service.Input(
        platform="xiaohongshu",
        job_id="newjob",
        content_hash="hash",
        title="new work",
        body="copy",
        assets=[],
    )
    result = asyncio.run(service.xhs_action("acct", "publish", body))
    assert result["external_id"] == "newwork123456" and result["status"] == "succeeded"


def test_mcp_client_supports_session_and_sse_without_retry(monkeypatch):
    calls = []
    original = httpx.Client

    def transport(req):
        p = json.loads(req.content)
        calls.append(p["method"])
        if p["method"] == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": p["id"],
                    "result": {"protocolVersion": "2025-06-18"},
                },
                headers={"Mcp-Session-Id": "test-session"},
            )
        assert req.headers["Mcp-Session-Id"] == "test-session"
        if p["method"] == "notifications/initialized":
            return httpx.Response(202)
        return httpx.Response(
            200,
            text="data: "
            + json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": p["id"],
                    "result": {
                        "content": [{"type": "text", "text": '{"status":"connected"}'}]
                    },
                }
            )
            + "\n\n",
            headers={"Content-Type": "text/event-stream"},
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(transport), **kw),
    )
    client = Client("http://connector/mcp")
    client.initialize()
    assert client.call("check_login", {})["status"] == "connected"
    assert len(calls) == 3


def test_mcp_client_does_not_retry_uncertain_mutation(monkeypatch):
    original = httpx.Client
    calls = []

    def transport(req):
        calls.append(1)
        raise httpx.ReadTimeout("uncertain")

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(transport), **kw),
    )
    with pytest.raises(httpx.ReadTimeout):
        Client("http://connector/mcp").call("publish_content", {})
    assert len(calls) == 1

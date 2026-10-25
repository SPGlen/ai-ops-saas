"""Small Streamable HTTP MCP client; paid/side-effect calls are never replayed."""

import json, uuid
import httpx


class MCPError(RuntimeError):
    pass


class Client:
    def __init__(self, url, headers=None, timeout=180):
        self.url = url
        self.headers = {
            "Accept": "application/json, text/event-stream",
            **(headers or {}),
        }
        self.timeout = timeout

    def rpc(self, method, params=None, notification=False):
        rid = uuid.uuid4().hex
        payload = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            payload["id"] = rid
        with httpx.Client(timeout=self.timeout, follow_redirects=False) as c:
            r = c.post(self.url, json=payload, headers=self.headers)
            r.raise_for_status()
            if r.headers.get("Mcp-Session-Id"):
                self.headers["Mcp-Session-Id"] = r.headers["Mcp-Session-Id"]
            if notification:
                return None
            if "text/event-stream" in r.headers.get("content-type", ""):
                objects = []
                event = []
                for line in r.text.splitlines() + [""]:
                    if line.startswith("data:"):
                        event.append(line[5:].lstrip())
                    elif not line and event:
                        objects.append(json.loads("\n".join(event)))
                        event = []
                data = next((d for d in objects if d.get("id") == rid), None)
            else:
                data = r.json()
            if not isinstance(data, dict) or data.get("id") != rid or "error" in data:
                raise MCPError("MCP_RESPONSE_INVALID")
            return data.get("result", {})

    def initialize(self):
        out = self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "zhiying-ops", "version": "0.2.0"},
            },
        )
        if out.get("protocolVersion") not in ("2025-03-26", "2025-06-18", "2025-11-25"):
            raise MCPError("MCP_VERSION_UNSUPPORTED")
        self.headers["MCP-Protocol-Version"] = out["protocolVersion"]
        self.rpc("notifications/initialized", notification=True)
        return out

    def tools(self):
        return self.rpc("tools/list").get("tools", [])

    def call(self, name, args):
        out = self.rpc("tools/call", {"name": name, "arguments": args})
        if out.get("isError"):
            raise MCPError("MCP_TOOL_FAILED")
        if isinstance(out.get("structuredContent"), dict):
            return out["structuredContent"]
        parts = [
            x.get("text", "") for x in out.get("content", []) if x.get("type") == "text"
        ]
        joined = "\n".join(parts)
        try:
            return json.loads(joined)
        except ValueError:
            try:
                return json.JSONDecoder().raw_decode(joined[joined.index("{") :])[0]
            except (ValueError, TypeError):
                img = next(
                    (x for x in out.get("content", []) if x.get("type") == "image"),
                    None,
                )
                return {
                    "text": joined,
                    **(
                        {
                            "image": "data:"
                            + img.get("mimeType", "image/png")
                            + ";base64,"
                            + img["data"]
                        }
                        if img
                        else {}
                    ),
                }

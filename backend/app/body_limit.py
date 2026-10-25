"""Bound request bodies before JSON/multipart parsing, including chunked requests."""

from starlette.responses import JSONResponse


class BoundedBody:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        limit = (
            27 * 1024 * 1024
            if path == "/api/v1/assets"
            else 1024 * 1024
            if path == "/api/v1/imports/payments"
            else 256 * 1024
        )
        parts = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            raw = message.get("body", b"")
            size += len(raw)
            if size > limit:
                return await JSONResponse(
                    {
                        "detail": {
                            "code": "BODY_TOO_LARGE",
                            "message": "请求内容超过允许大小",
                        }
                    },
                    413,
                )(scope, receive, send)
            parts.append(raw)
            if not message.get("more_body", False):
                break
        body = b"".join(parts)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

FROM golang:1.27.3-bookworm@sha256:21ade014faf952365b9ecbd8dbdb87176fbacb82fac9fb132d9f2a7b8cc3f132 AS xhs-builder
WORKDIR /src
COPY publisher/vendor/xiaohongshu /src
RUN CGO_ENABLED=0 go build -trimpath -o /xiaohongshu-mcp .
FROM mcr.microsoft.com/playwright/python:v1.64.0-noble@sha256:684df257a1fa0ef3fa288239819984008f560e8f8db5b635ee9e2a50cbcd2e23
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY publisher/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir pip==26.2.1 && pip install --no-cache-dir -r /tmp/requirements.lock && mkdir /state && chown 1000:1000 /state
COPY publisher /srv/publisher
COPY --from=xhs-builder /xiaohongshu-mcp /usr/local/bin/xiaohongshu-mcp
USER 1000:1000
EXPOSE 8901
CMD ["uvicorn","publisher.service:app","--host","0.0.0.0","--port","8901","--no-access-log","--no-proxy-headers"]

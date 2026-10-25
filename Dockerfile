FROM node:24-bookworm-slim@sha256:a5f4366e834695d5f363b920c104953a535d3a9864d1bdf74566a0ebe01daee5 AS web
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258 AS runtime
ENV OPS_PROJECT_ROOT=/srv/ops PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-cjk ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/ops
COPY backend/requirements-resolved.lock ./requirements.lock
COPY backend/build-requirements.lock ./build-requirements.lock
RUN pip install --no-cache-dir pip==26.2.1 && pip install --no-cache-dir --require-hashes -r build-requirements.lock && pip install --no-cache-dir --require-hashes -r requirements.lock
COPY backend/ ./backend/
RUN pip install --no-build-isolation --no-deps --no-cache-dir ./backend && useradd --uid 10001 --create-home ops && mkdir /srv/ops/.local && chown -R ops:ops /srv/ops/.local
COPY --from=web /src/frontend/dist ./frontend/dist
COPY docs/openapi.json ./docs/openapi.json
COPY scripts/doctor.py scripts/backup.py scripts/restore.py ./scripts/
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--no-access-log","--no-proxy-headers"]

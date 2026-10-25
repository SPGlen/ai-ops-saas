"""Read-only deployment readiness; no credentials are printed or sent to third parties."""

import json, shutil, sys
from pathlib import Path
from app.config import settings
from app.db import engine, check_runtime_role
from sqlalchemy import text

checks = []


def check(name, fn):
    try:
        result = fn()
        checks.append({"check": name, "status": "passed", "detail": result})
    except Exception as error:
        checks.append(
            {"check": name, "status": "failed", "detail": type(error).__name__}
        )


cfg = settings()
check("runtime_configuration", lambda: cfg.validate_runtime() or cfg.environment)


def database():
    with engine().connect() as connection:
        return connection.execute(text("SELECT 1")).scalar()


check("database", database)
if cfg.production:
    check(
        "database_runtime_role_and_rls",
        lambda: check_runtime_role() or "non-owner, forced tenant policies",
    )
check("ffmpeg", lambda: shutil.which("ffmpeg") or (_ for _ in ()).throw(RuntimeError()))
check(
    "ffprobe", lambda: shutil.which("ffprobe") or (_ for _ in ()).throw(RuntimeError())
)
check(
    "chinese_font",
    lambda: (
        __import__("app.integrations.rendering", fromlist=["font"])
        .font(20)
        .getname()[0]
    ),
)
if cfg.s3_bucket:

    def storage():
        from app.integrations.storage import Storage

        Storage().client().head_bucket(Bucket=cfg.s3_bucket)
        return "reachable; verify bucket privacy policy separately"

    check("private_storage_access", storage)
print(
    json.dumps(
        {
            "checks": checks,
            "external_model": "not_called",
            "publishing_accounts": "not_called",
        },
        ensure_ascii=False,
        indent=2,
    )
)
sys.exit(any(x["status"] == "failed" for x in checks))

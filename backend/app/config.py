from functools import lru_cache
from pathlib import Path
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(
    os.environ.get("OPS_PROJECT_ROOT", str(Path(__file__).resolve().parents[2]))
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", env_prefix="OPS_"
    )
    environment: str = "development"
    demo_mode: bool = False
    demo_access_code: str = ""
    demo_expires_at: str = ""
    database_url: str = "sqlite:///" + str(ROOT / ".local" / "ops.db").replace(
        "\\", "/"
    )
    secret_key: str = ""
    public_url: str = "http://127.0.0.1:5188"
    broker_url: str = "redis://127.0.0.1:6379/0"
    task_mode: str = "local"
    data_dir: Path = ROOT / ".local" / "data"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    text_provider: str = "aliyun"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-flash"
    aliyun_api_key: str = ""
    aliyun_base_url: str = "https://dashscope.aliyuncs.com"
    aliyun_text_base_url: str = ""
    text_model: str = "qwen-plus"
    score_model: str = "qwen3-vl-plus"
    review_model: str = "qwen-max"
    tts_model: str = "qwen3-tts-flash"
    embedding_model: str = "text-embedding-v3"
    image_model: str = "qwen-image-plus"
    video_model: str = "wan2.7-t2v-2026-06-12"
    publisher_url: str = ""
    publisher_token: str = ""
    allow_live_publish: bool = False
    allow_live_replies: bool = False
    ocr_python: str = ""
    ocr_enabled: bool = False
    matrix_source_hosts: str = ""
    matrix_max_running: int = 2
    payment_enabled: bool = False
    session_hours: int = 12
    max_upload_mb: int = 25

    @property
    def production(self):
        return self.environment == "production"

    def validate_runtime(self):
        if self.text_provider not in ("aliyun", "deepseek"):
            raise RuntimeError("OPS_TEXT_PROVIDER must be aliyun or deepseek")
        if self.demo_mode:
            from urllib.parse import urlparse
            if self.production or not self.database_url.startswith("sqlite:") or self.task_mode != "demo":
                raise RuntimeError("Showcase mode requires its isolated SQLite database and OPS_TASK_MODE=demo")
            if self.deepseek_api_key or self.aliyun_api_key or self.smtp_host or self.s3_bucket or self.publisher_url or self.allow_live_publish or self.allow_live_replies:
                raise RuntimeError("Showcase mode cannot contain real model, mail, storage or publishing connections")
            if urlparse(self.public_url).hostname not in ("localhost", "127.0.0.1", "::1"):
                if len(self.demo_access_code) < 16:
                    raise RuntimeError("An external showcase URL requires a 16+ character access code")
        if len(self.secret_key) < 32:
            raise RuntimeError(
                "OPS_SECRET_KEY needs 32+ characters; run scripts/configure.py"
            )
        if self.production:
            if not self.database_url.startswith("postgresql"):
                raise RuntimeError(
                    "Production requires PostgreSQL with non-owner ops_app role"
                )
            if not self.public_url.startswith("https://") or self.task_mode != "celery":
                raise RuntimeError("Production requires HTTPS and OPS_TASK_MODE=celery")
            if not self.smtp_host or not self.s3_bucket:
                raise RuntimeError("Production requires SMTP and private S3 storage")
        self.data_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def settings():
    # The showcase receives explicit settings from its private launch manifest.
    # Windows PowerShell 5 removes empty environment variables: never fall back
    # to the ordinary workspace .env and accidentally load real connections.
    if os.environ.get("OPS_DEMO_MODE", "").lower() == "true" and os.environ.get("OPS_TASK_MODE") == "demo":
        return Settings(_env_file=None)
    return Settings()

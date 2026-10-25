from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
target = root / ".env.production"
if target.exists():
    raise SystemExit("Existing .env.production preserved")
keys = [
    "OPS_SECRET_KEY",
    "OPS_DB_ROOT_PASSWORD",
    "OPS_DB_PASSWORD",
    "OPS_MIGRATION_PASSWORD",
    "OPS_VALKEY_PASSWORD",
    "OPS_PUBLISHER_TOKEN",
]
values = {k: secrets.token_hex(32) for k in keys}
values.update(
    {
        "OPS_DOMAIN": "",
        "OPS_PUBLIC_URL": "",
        "OPS_SMTP_HOST": "",
        "OPS_SMTP_PORT": "587",
        "OPS_SMTP_USER": "",
        "OPS_SMTP_PASSWORD": "",
        "OPS_SMTP_FROM": "",
        "OPS_S3_BUCKET": "",
        "OPS_S3_ENDPOINT": "",
        "OPS_S3_REGION": "cn-hangzhou",
        "OPS_S3_ACCESS_KEY": "",
        "OPS_S3_SECRET_KEY": "",
        "OPS_TEXT_PROVIDER": "aliyun",
        "OPS_DEEPSEEK_API_KEY": "",
        "OPS_DEEPSEEK_MODEL": "deepseek-flash",
        "OPS_ALIYUN_API_KEY": "",
        "OPS_PUBLISHER_URL": "",
        "OPS_ALLOW_LIVE_PUBLISH": "false",
        "OPS_MATRIX_SOURCE_HOSTS": "",
        "OPS_MATRIX_MAX_RUNNING": "2",
    }
)
target.write_text(
    "# Keep this file private. Fill the blank infrastructure fields before deployment.\n"
    + "\n".join(k + "=" + v for k, v in values.items())
    + "\n",
    encoding="utf8",
)
target.chmod(0o600)
print("Private configuration created. Secret values were not printed.")

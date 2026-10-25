"""Generate development secrets without printing them. Never overwrite an existing .env."""

from pathlib import Path
import secrets

root = Path(__file__).resolve().parents[1]
env = root / ".env"
if env.exists():
    print(".env already exists; preserved")
else:
    env.write_text(
        "OPS_SECRET_KEY="
        + secrets.token_urlsafe(48)
        + "\nOPS_ENVIRONMENT=development\nOPS_TASK_MODE=local\n",
        encoding="utf8",
    )
    print("Development .env created. Credentials are not printed.")
(root / ".local").mkdir(exist_ok=True)

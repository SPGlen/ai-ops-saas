"""Configure a loopback publisher without printing or overwriting existing credentials."""

import os
from pathlib import Path
import secrets
from app.config import ROOT

path = ROOT / ".env"
s = path.read_text(encoding="utf-8") if path.exists() else ""
lines = s.splitlines()
values = {
    line.split("=", 1)[0]: line.split("=", 1)[1]
    for line in lines
    if "=" in line and not line.lstrip().startswith("#")
}
if (
    os.environ.get(
        "OPS_ENVIRONMENT", values.get("OPS_ENVIRONMENT", "development")
    ).strip("\"'")
    == "production"
):
    raise SystemExit("Use production deployment tools")
updates = {"OPS_PUBLISHER_URL": "http://127.0.0.1:8900"}
if len(values.get("OPS_PUBLISHER_TOKEN", "").strip("\"'")) < 32:
    updates["OPS_PUBLISHER_TOKEN"] = secrets.token_hex(32)
for key, value in updates.items():
    lines = [line for line in lines if not line.startswith(key + "=")]
    lines.append(key + "=" + value)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(
    "Local publisher configured; real publishing and replies retain their existing switches."
)

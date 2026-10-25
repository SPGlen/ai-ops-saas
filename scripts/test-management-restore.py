"""Verify the pre-change backup in a new isolated SQLite database, without touching preview data."""

import argparse, hashlib, json, os, sqlite3, uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--backup", required=True)
args = p.parse_args()
source = Path(args.backup).resolve() / "database.sqlite"
if not source.is_file():
    raise SystemExit("Backup database not found")
target = root / ".local" / "restore-check-031" / uuid.uuid4().hex
assert target.resolve().is_relative_to(root.resolve())
target.mkdir(parents=True)
dest = target / "restored.sqlite"
with sqlite3.connect(source) as original, sqlite3.connect(dest) as restored:
    original.backup(restored)
os.environ["OPS_DATABASE_URL"] = "sqlite:///" + dest.as_posix()
os.environ["OPS_DATA_DIR"] = str(target / "data")
os.environ["OPS_ENVIRONMENT"] = "development"
from app.db import initialize, IMMUTABLE_TABLES


def state(path):
    with sqlite3.connect(path) as conn:
        available = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        result = {}
        for table in IMMUTABLE_TABLES:
            if table not in available:
                continue
            records = conn.execute(
                'SELECT * FROM "' + table + '" ORDER BY id'
            ).fetchall()
            result[table] = {
                "count": len(records),
                "sha256": hashlib.sha256(
                    json.dumps(records, ensure_ascii=False, default=str).encode()
                ).hexdigest(),
            }
        return result


before = state(source)
initialize()
after = state(dest)
assert before == {k: after[k] for k in before}
with sqlite3.connect(dest) as conn:
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
report = {
    "status": "passed",
    "engine": "SQLite development restore",
    "native_postgresql": False,
    "original_unchanged": True,
    "immutable_tables": after,
    "authorization_migration": "passed",
}
(root / "docs" / "management-backup-restore.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8"
)
print(
    json.dumps(
        {
            "status": "passed",
            "immutable_tables": len(after),
            "ledger_rows": after["ledger_entries"]["count"],
            "credit_rows": after["credit_entries"]["count"],
            "audit_rows": after["audit_events"]["count"],
        }
    )
)

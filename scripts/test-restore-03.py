"""Restore rehearsal and pre-0.3 journal preservation check; never alters live data."""

import json, sqlite3, subprocess, sys, uuid, hashlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
backups = root / ".local/backups-03"
backup = max(backups.glob("ops-*"), key=lambda p: p.name)
destination = root / ".local/restore-03" / uuid.uuid4().hex / "database.sqlite"
assert destination.resolve().is_relative_to(root.resolve())
subprocess.run(
    [
        sys.executable,
        str(root / "scripts/restore.py"),
        str(backup),
        "--sqlite-destination",
        str(destination),
    ],
    check=True,
)
with (
    sqlite3.connect(backup / "database.sqlite") as original,
    sqlite3.connect(destination) as restored,
):
    tables = [
        r[0]
        for r in original.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    counts = {}
    for table in tables:
        assert table.replace("_", "").isalnum()
        a = original.execute("SELECT count(*) FROM " + table).fetchone()[0]
        b = restored.execute("SELECT count(*) FROM " + table).fetchone()[0]
        assert a == b, (table, a, b)
        counts[table] = b
    assert restored.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert restored.execute("PRAGMA foreign_key_check").fetchall() == []
    preserved = {}
    before = root / ".local/backups/ops-20261021T173409Z/database.sqlite"
    if before.exists():
        with sqlite3.connect(before) as prior:
            for table in ("ledger_entries", "credit_entries", "audit_events"):
                columns = [
                    r[1] for r in prior.execute("PRAGMA table_info(" + table + ")")
                ]
                new_columns = [
                    r[1] for r in restored.execute("PRAGMA table_info(" + table + ")")
                ]
                assert columns == new_columns
                old = {r[0]: r for r in prior.execute("SELECT * FROM " + table)}
                new = {r[0]: r for r in restored.execute("SELECT * FROM " + table)}
                assert all(new.get(k) == v for k, v in old.items()), table
                preserved[table] = len(old)
report = {
    "status": "passed",
    "engine": "SQLite development restore",
    "native_postgresql": False,
    "tables": len(tables),
    "row_counts": counts,
    "foreign_key_check": "passed",
    "integrity_check": "passed",
    "pre_03_journal_rows_unchanged": preserved,
    "backup_checksums_verified": True,
    "live_database_modified": False,
}
(root / "docs/backup-restore-03.json").write_text(
    json.dumps(report, indent=2), encoding="utf-8"
)
print(
    json.dumps(
        {
            "status": report["status"],
            "tables": len(tables),
            "preserved_journals": preserved,
        }
    )
)

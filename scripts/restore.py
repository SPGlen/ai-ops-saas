"""Restore only to a separately named, empty rehearsal database. Never --clean or DROP."""

import os, json, argparse, hashlib, sqlite3, subprocess
from pathlib import Path
from sqlalchemy.engine import make_url

p = argparse.ArgumentParser()
p.add_argument("backup")
p.add_argument("--sqlite-destination")
args = p.parse_args()
root = Path(args.backup).resolve()
manifest = json.loads((root / "manifest.json").read_text(encoding="utf8"))
for name, expected in manifest["files"].items():
    file = (root / name).resolve()
    if not file.is_relative_to(root):
        raise SystemExit("Invalid backup path")
    with file.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected:
        raise SystemExit("Backup checksum mismatch")
if args.sqlite_destination:
    target = Path(args.sqlite_destination).resolve()
    if target.exists():
        raise SystemExit("Destination already exists; preserved")
    target.parent.mkdir(parents=True, exist_ok=True)
    with (
        sqlite3.connect(root / "database.sqlite") as source,
        sqlite3.connect(target) as dest,
    ):
        source.backup(dest)
    with sqlite3.connect(target) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("SQLite integrity check failed")
else:
    url = make_url(os.environ.get("OPS_RESTORE_DATABASE_URL", ""))
    if not url.database or not url.database.endswith("_restore"):
        raise SystemExit("Restore rehearsal database name must end in _restore")
    import psycopg

    conn = psycopg.connect(
        host=url.host,
        port=url.port or 5432,
        dbname=url.database,
        user=url.username,
        password=url.password,
    )
    with conn:
        count = conn.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
        ).fetchone()[0]
        if count:
            raise SystemExit("Restore target must be empty")
    env = {
        **os.environ,
        "PGHOST": url.host or "",
        "PGPORT": str(url.port or 5432),
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
        "PGDATABASE": url.database,
    }
    subprocess.run(
        [
            "pg_restore",
            "--no-password",
            "--no-owner",
            "--exit-on-error",
            "--dbname",
            url.database,
            str(root / "database.dump"),
        ],
        env=env,
        check=True,
    )
print(
    "Database restoration completed in the separate rehearsal target. Restore object versions and verify application access before promotion."
)

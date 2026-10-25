"""Operator-run PostgreSQL or dev SQLite backup. No destructive database commands."""

import os, json, subprocess, datetime, hashlib, sqlite3, shutil, argparse
from pathlib import Path
from sqlalchemy.engine import make_url
from app.config import settings

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--directory", required=True)
args = p.parse_args()
target = Path(args.directory).resolve() / (
    "ops-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
)
target.mkdir(parents=True, exist_ok=False)
target.chmod(0o700)
cfg = settings()
manifest = {
    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "files": {},
    "encryption_key_included": False,
}
if cfg.database_url.startswith("sqlite:///"):
    database = cfg.database_url.removeprefix("sqlite:///")
    with (
        sqlite3.connect(database) as source,
        sqlite3.connect(target / "database.sqlite") as dest,
    ):
        source.backup(dest)
    objects = cfg.data_dir / "objects"
    if objects.exists():
        shutil.copytree(objects, target / "objects")
else:
    url = make_url(os.environ.get("OPS_BACKUP_DATABASE_URL", ""))
    if not url.host or not url.database:
        raise SystemExit("OPS_BACKUP_DATABASE_URL must use an operator backup role")
    env = {
        **os.environ,
        "PGHOST": url.host,
        "PGPORT": str(url.port or 5432),
        "PGUSER": url.username or "",
        "PGPASSWORD": url.password or "",
        "PGDATABASE": url.database,
    }
    subprocess.run(
        [
            "pg_dump",
            "--format=custom",
            "--no-password",
            "--file",
            str(target / "database.dump"),
        ],
        env=env,
        check=True,
    )
if cfg.s3_bucket:
    from app.integrations.storage import Storage

    client = Storage().client()
    rows = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=cfg.s3_bucket):
        for obj in page.get("Contents", []):
            rows.append({"key": obj["Key"], "etag": obj["ETag"], "size": obj["Size"]})
    (target / "objects-manifest.json").write_text(
        json.dumps({"bucket": cfg.s3_bucket, "objects": rows}, indent=2),
        encoding="utf8",
    )
    manifest["object_backup"] = (
        "S3 manifest only. Bucket replication/versioning must be configured and restored separately."
    )
for file in target.rglob("*"):
    if file.is_file():
        manifest["files"][str(file.relative_to(target))] = hashlib.file_digest(
            file.open("rb"), "sha256"
        ).hexdigest()
        file.chmod(0o600)
(target / "manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8"
)
print(
    json.dumps({"backup_directory": str(target), "file_count": len(manifest["files"])})
)

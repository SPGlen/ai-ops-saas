"""Package only reviewed source paths. Never include local data, credentials, browser state or caches."""

import zipfile, hashlib, json, argparse, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
version = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf8"))["version"]
parser.add_argument("--name", default=f"ai-ops-saas-{version}.zip")
args = parser.parse_args()
if not re.fullmatch(r"[A-Za-z0-9._-]+\.zip", args.name):
    raise SystemExit("Archive name must be a plain .zip filename")
EXCLUDED = {
    ".git",
    ".venv",
    ".local",
    ".upstream",
    "node_modules",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "test-results",
    "playwright-report",
    "build",
}
folders = ["backend", "frontend", "publisher", "deploy", "docs", "scripts", ".github"]
files = [
    ROOT / n
    for n in ["README.md", "Dockerfile", "compose.yaml", ".gitignore", ".dockerignore"]
]
files.extend(ROOT.glob("*.cmd"))
files.extend(ROOT.glob("UPGRADE_*.txt"))
manual = ROOT / "output/pdf/知营使用说明书与自媒体账号接入指南.pdf"
if manual.is_file():
    files.append(manual)
for folder in folders:
    base = ROOT / folder
    if not base.exists():
        continue
    for file in base.rglob("*"):
        if not file.is_file():
            continue
        relative = file.relative_to(ROOT)
        if any(p in EXCLUDED or p.endswith(".egg-info") for p in relative.parts):
            continue
        if file.name.startswith(".env") or file.suffix in (
            ".pyc",
            ".log",
            ".sqlite",
            ".db",
            ".enc",
        ):
            continue
        files.append(file)
files = sorted(set(f for f in files if f.is_file()))
manifest = {
    str(f.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(
        f.read_bytes()
    ).hexdigest()
    for f in files
}
(ROOT / "SOURCE_MANIFEST.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8"
)
target = ROOT / ".local" / "delivery"
target.mkdir(parents=True, exist_ok=True)
archive = target / args.name
with zipfile.ZipFile(
    archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
) as output:
    for file in files + [ROOT / "SOURCE_MANIFEST.json"]:
        output.write(
            file, "ai-ops-saas/" + str(file.relative_to(ROOT)).replace("\\", "/")
        )
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
    names = check.namelist()
    assert not any(
        "/.env" in x or "/.local/" in x or "/node_modules/" in x for x in names
    )
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix(".zip.sha256").write_text(digest + "  " + archive.name + "\n")
print(
    json.dumps(
        {
            "archive": str(archive),
            "files": len(files) + 1,
            "bytes": archive.stat().st_size,
            "sha256": digest,
        }
    )
)

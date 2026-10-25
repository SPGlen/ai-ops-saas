"""Summarize existing verification evidence; never creates test success from a stub."""

import json
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def stream(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    decoder = json.JSONDecoder()
    while text.strip():
        text = text.lstrip()
        value, end = decoder.raw_decode(text)
        yield value
        text = text[end:]


def junit(path):
    root = ET.parse(path).getroot()
    suites = list(root.iter("testsuite"))
    return {
        key: sum(int(s.get(key, 0)) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def vulnerabilities(name):
    return sum(len(d.get("vulns", [])) for d in read(DOC / name)["dependencies"])


source = ROOT / "publisher" / "vendor" / "xiaohongshu"
origin = read(source / "SOURCE.json")
changed = []
missing = []
for name, previous in origin["files"].items():
    path = source / name
    if not path.is_file():
        missing.append(name)
        continue
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    if current != previous:
        changed.append(
            {"path": name, "original_sha256": previous, "current_sha256": current}
        )
created = []
for path in sorted(source.rglob("*")):
    if path.is_file():
        relative = path.relative_to(source).as_posix()
        if relative not in origin["files"] and relative not in (
            "SOURCE.json",
            "LOCAL_PATCHES.json",
            "LOCAL_PATCHES.md",
        ):
            created.append(
                {
                    "path": relative,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
write(
    source / "LOCAL_PATCHES.json",
    {
        "repository": origin["repository"],
        "commit": origin["commit"],
        "original_input_files": len(origin["files"]),
        "modified_files": changed,
        "added_files": created,
        "removed_files": missing,
        "changes": [
            "Require per-process bearer token and loopback binding",
            "Require an absolute account-specific cookies path",
            "Use managed standard Chromium with sandbox enabled; disable upstream browser download and fingerprint changes",
            "Return structured login identity for account-bound verification",
            "Upgrade MCP Go SDK and vulnerable network/crypto dependencies; exact versions in go.mod/go.sum",
        ],
        "provenance": "SOURCE.json records original input hashes; LOCAL_PATCHES.json records current local differences. The user download directory was preserved.",
    },
)

api = junit(DOC / "staff-mcp-tests.xml")
mcp = junit(DOC / "mcp-tests.xml")
e2e = read(DOC / "e2e-report.json")["stats"]
rls = read(DOC / "rls-test-report.json")
migration = read(DOC / "migration-test-report.json")
runtime = read(DOC / "xhs-runtime-report.json")
go_tests = list(stream(DOC / "xhs-go-test-report.jsonl"))
go_report = {
    "passed_tests": sum(
        x.get("Action") == "pass" and bool(x.get("Test")) and "/" not in x["Test"]
        for x in go_tests
    ),
    "passed_subtests": sum(
        x.get("Action") == "pass" and "/" in x.get("Test", "") for x in go_tests
    ),
    "failed": sum(x.get("Action") == "fail" for x in go_tests),
    "scope": "go test ./... -run 'Test.*(Parse|Cookies|Middleware|Routes|Validate|Mask|Title)' -count=1; selected unit tests only",
}
go_scans = {}
for os_name, filename in [
    ("windows", "xhs-go-vuln-report.jsonl"),
    ("linux", "xhs-go-linux-vuln-report.jsonl"),
]:
    findings = [x["finding"] for x in stream(DOC / filename) if "finding" in x]
    reachable = [
        x
        for x in findings
        if any(frame.get("function") for frame in x.get("trace", []))
    ]
    go_scans[os_name] = {
        "reachable_findings": len(reachable),
        "module_only_findings": [
            x["osv"]
            for x in findings
            if not any(
                frame.get("package") or frame.get("function")
                for frame in x.get("trace", [])
            )
        ],
        "report": filename,
    }
security = {
    "python_installed_known_vulnerabilities": vulnerabilities("pip-audit.json"),
    "publisher_lock_known_vulnerabilities": vulnerabilities(
        "publisher-dependency-audit.json"
    ),
    "gateway_lock_known_vulnerabilities": vulnerabilities(
        "gateway-dependency-audit.json"
    ),
    "frontend": read(DOC / "npm-audit.json")["metadata"]["vulnerabilities"],
    "go": go_scans,
    "development_tool_fix": {
        "tool": "uv",
        "from": "0.13.3",
        "to": "0.13.4",
        "advisory": "GHSA-hq85-5cpj-mr62",
        "url": "https://github.com/astral-sh/uv/security/advisories/GHSA-hq85-5cpj-mr62",
    },
}
pending = [
    "native_postgresql_and_alembic",
    "linux_docker_images_and_scan",
    "real_bailian_models",
    "real_ocr_model",
    "xiaohongshu_real_login_publish_comments_metrics",
    "douyin_real_publish_official_comments_permissions",
    "douyin_private_message_schema_and_send",
    "channels_real_login_publish_metrics",
    "wecom_official_account",
    "cloud_s3_restore",
    "production_upgrade_and_rollback",
]
report = {
    "version": "0.2.0-rc1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "formal_delivery_accepted": False,
    "api": api,
    "mcp_contract": mcp,
    "browser": {
        "passed": e2e["expected"],
        "failed": e2e["unexpected"],
        "flaky": e2e["flaky"],
        "skipped": e2e["skipped"],
        "database": "isolated development SQLite; synthetic fixtures; scripts/test-browser.ps1",
    },
    "postgres_wasm_rls": rls,
    "migration": migration,
    "development_restore": read(DOC / "backup-restore-test.json"),
    "xhs_real_process_protocol": runtime,
    "xhs_selected_go_tests": go_report,
    "source_verification": read(DOC / "xhs-source-verification.json"),
    "dependencies": security,
    "actual_external_publications": {"xiaohongshu": [], "douyin": [], "channels": []},
    "actual_external_replies": [],
    "live_publish_default": False,
    "live_replies_default": False,
    "not_verified": pending,
    "notes": [
        "The current report records automated tests and real MCP processes, not real social account acceptance.",
        "Unsupported or unverified messaging uses explicit manual processing. No simulated interaction is labeled as a real external event.",
        "PostgreSQL WASM tests do not replace native PostgreSQL and Docker production verification.",
    ],
}
write(DOC / "staff-mcp-acceptance.json", report)
write(DOC / "release-gates.json", report)
print(
    json.dumps(
        {
            "api": api,
            "browser": report["browser"],
            "go_tests": go_report,
            "modified_upstream_files": len(changed),
            "added_upstream_files": len(created),
            "formal_delivery_accepted": False,
        }
    )
)

"""Assemble 0.3 evidence from completed checks, without inventing external acceptance."""

import json, hashlib, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
docs = root / "docs"


def read(name):
    return json.loads((docs / name).read_text(encoding="utf-8-sig"))


def junit(name):
    suites = list(ET.parse(docs / name).getroot().iter("testsuite"))
    return {
        k: sum(int(s.get(k, 0)) for s in suites)
        for k in ("tests", "failures", "errors", "skipped")
    }


def audit(name):
    return sum(len(x.get("vulns", [])) for x in read(name)["dependencies"])


api = junit("operations-api-tests.xml")
browser = read("e2e-report.json")["stats"]
report = {
    "version": "0.3.0-rc1",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "formal_delivery_accepted": False,
    "api": api,
    "browser": {
        "passed": browser["expected"],
        "failed": browser["unexpected"],
        "flaky": browser["flaky"],
        "skipped": browser["skipped"],
        "database": "isolated SQLite with synthetic fixtures",
    },
    "migration": read("migration-test-report.json"),
    "postgres_wasm_rls": read("rls-test-report.json"),
    "development_backup_restore": read("backup-restore-03.json"),
    "real_cpu_ocr": read("operations-real-ocr.json"),
    "dependency_vulnerabilities": {
        "backend": audit("pip-audit.json"),
        "ocr": audit("ocr-dependency-audit.json"),
        "publisher": audit("publisher-dependency-audit.json"),
        "frontend": read("npm-audit.json")["metadata"]["vulnerabilities"],
    },
    "checks_scope": {
        "native_postgresql": False,
        "docker_images": False,
        "real_wecom_group_delivery": False,
        "real_social_publication": False,
        "real_bailian_models": False,
        "real_digital_human_live": False,
    },
    "not_verified": [
        "Native PostgreSQL migration and restore",
        "Linux Docker build, image scan and code rollback",
        "Real WeCom group webhook and delivery",
        "Aliyun server, private object store, SMTP and domain deployment",
        "Real Bailian model generation and billing",
        "Real publications on Xiaohongshu / Douyin / Channels",
        "Handwritten, skewed and representative institutional scan samples",
    ],
    "consultation_enabled_by_default": False,
    "live_social_send_by_default": False,
    "digital_human": "application and platform review only; provider pending",
    "legacy_mcp_evidence": "staff-mcp-acceptance.json (0.2 historical evidence, not 0.3 external account acceptance)",
    "evidence_sha256": {
        name: hashlib.sha256((docs / name).read_bytes()).hexdigest()
        for name in [
            "operations-api-tests.xml",
            "e2e-report.json",
            "migration-test-report.json",
            "rls-test-report.json",
            "backup-restore-03.json",
            "operations-real-ocr.json",
        ]
    },
}
assert api["failures"] == api["errors"] == 0, api
assert report["browser"]["failed"] == report["browser"]["flaky"] == 0, report["browser"]
assert report["migration"]["status"] == "passed"
assert report["development_backup_restore"]["status"] == "passed"
for name in ["operations-acceptance.json", "release-gates.json"]:
    (docs / name).write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
print(
    json.dumps(
        {
            "version": report["version"],
            "api": api,
            "browser": report["browser"],
            "formal_delivery_accepted": False,
        }
    )
)

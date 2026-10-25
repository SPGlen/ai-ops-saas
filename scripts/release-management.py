"""Assemble 0.3.1 evidence; external production acceptance remains separate."""

import json, hashlib, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parents[1]
docs = root / "docs"


def read(name):
    return json.loads((docs / name).read_text(encoding="utf-8-sig"))


suites = list(
    ET.parse(docs / "management-full-api-tests.xml").getroot().iter("testsuite")
)
api = {
    key: sum(int(s.get(key, 0)) for s in suites)
    for key in ("tests", "errors", "failures", "skipped")
}
browser = read("e2e-report.json")["stats"]
migration = read("management-migration-test.json")
restore = read("management-backup-restore.json")
assert api["failures"] == api["errors"] == 0
assert browser["unexpected"] == browser["flaky"] == 0
assert migration["status"] == restore["status"] == "passed"
report = {
    "version": read("../frontend/package.json")["version"],
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "formal_delivery_accepted": False,
    "api": api,
    "browser": {
        "passed": browser["expected"],
        "failed": browser["unexpected"],
        "flaky": browser["flaky"],
        "skipped": browser["skipped"],
        "database": "isolated SQLite, synthetic fixtures",
    },
    "migration": migration,
    "backup_restore": restore,
    "behavior": {
        "multi_role_members": True,
        "owner_managed_authorization": True,
        "independent_scheduler": True,
        "aggregate_revenue_without_finance_detail": True,
        "encrypted_scoped_family_feedback": True,
        "receipt_preview_and_download": True,
        "automatic_weekly_monthly_snapshots": True,
        "deterministic_operating_summary": True,
        "llm_report_interpretation": False,
    },
    "external_acceptance": {
        "native_postgresql": False,
        "docker_images": False,
        "real_wecom_push": False,
        "website_sso": False,
        "real_social_accounts": False,
        "aliyun_deployment": False,
    },
    "unchanged_dependency_versions": True,
    "legacy_evidence": "operations-acceptance.json (0.3.0 historical checks)",
    "evidence_sha256": {
        name: hashlib.sha256((docs / name).read_bytes()).hexdigest()
        for name in (
            "management-full-api-tests.xml",
            "e2e-report.json",
            "management-migration-test.json",
            "management-backup-restore.json",
            "migration-upgrade-0004.sql",
            "openapi.json",
        )
    },
}
for name in ("management-acceptance.json", "release-gates.json"):
    (docs / name).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
print(
    json.dumps(
        {
            "version": report["version"],
            "api_passed": api["tests"],
            "browser_passed": browser["expected"],
            "formal_delivery_accepted": False,
        }
    )
)

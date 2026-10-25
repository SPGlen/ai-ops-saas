"""Reproducible real CPU OCR smoke test, using synthetic data only."""

import io, os, json, time, argparse
from pathlib import Path
from PIL import Image
from app.config import settings
from app.admission_import import read_scan

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--ocr-python", default="")
args = p.parse_args()
if args.ocr_python:
    os.environ["OPS_OCR_PYTHON"] = str(Path(args.ocr_python).resolve())
    settings.cache_clear()
fixture = root / "docs/samples/admissions-ocr-fixture.png"
inputs = [("png", fixture.read_bytes())]
raw = io.BytesIO()
Image.open(fixture).convert("RGB").save(raw, format="PDF", resolution=150)
inputs.append(("pdf", raw.getvalue()))
checks = []
for fmt, raw in inputs:
    started = time.time()
    rows, _ = read_scan(raw, "synthetic." + fmt)
    assert len(rows) == 1, rows
    for key, value in {
        "student_name": "林小明",
        "name": "林家长",
        "contact": "13800000001",
    }.items():
        assert rows[0]["data"][key] == value, (fmt, rows)
    checks.append(
        {
            "format": fmt,
            "pages": 1,
            "rows": len(rows),
            "confidence": rows[0]["confidence"],
            "seconds": round(time.time() - started, 1),
        }
    )
report = {
    "status": "passed",
    "sample": "synthetic printed Chinese admissions table",
    "engine": "PaddleOCR 3.7.0 / PaddlePaddle 3.3.1 CPU",
    "mkldnn": False,
    "formats": checks,
    "fields_verified": ["student_name", "contact", "name"],
    "manual_review_required": True,
    "handwriting_verified": False,
}
(root / "docs/operations-real-ocr.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps(report, ensure_ascii=False))

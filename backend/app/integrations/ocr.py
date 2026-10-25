import json, tempfile
from pathlib import Path
from .storage import Storage


def extract(asset):
    from ..config import settings

    if settings().ocr_python:
        from ..admission_import import recognize

        pages = recognize(Storage().read(asset.object_key), asset.name)
        return "\n".join(w["text"] for page in pages for w in page)[:20000]
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        from ..security import fail

        fail("OCR_UNCONFIGURED", "OCR运行组件未安装，请启用 OCR Worker", 503)
    suffix = ".pdf" if asset.mime == "application/pdf" else ".png"
    with tempfile.TemporaryDirectory(prefix="ops-ocr-") as directory:
        path = Path(directory) / ("receipt" + suffix)
        path.write_bytes(Storage().read(asset.object_key))
        engine = PaddleOCR(
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
        output = []
        for result in engine.predict(str(path)):
            data = result.json
            if isinstance(data, str):
                data = json.loads(data)
            item = data.get("res", data)
            output.extend(item.get("rec_texts", []))
        return "\n".join(output)[:20000]

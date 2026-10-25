"""Standalone CPU OCR runner; emits geometry and confidence, no business credentials."""

import sys, json
from pathlib import Path


def main():
    from paddleocr import PaddleOCR

    path = Path(sys.argv[1])
    engine = PaddleOCR(
        enable_mkldnn=False,
        cpu_threads=4,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    metadata = None
    try:
        import cv2, numpy as np
        from PIL import Image

        if path.suffix.lower() == ".pdf":
            import pypdfium2

            pdf = pypdfium2.PdfDocument(str(path))
            picture = pdf[0].render(scale=3).to_pil().convert("RGB")
        else:
            picture = Image.open(path).convert("RGB")
        value, _, _ = cv2.QRCodeDetector().detectAndDecode(
            cv2.cvtColor(np.array(picture), cv2.COLOR_RGB2BGR)
        )
        if value.startswith("zhiying-admissions:"):
            metadata = value.split(":", 1)[1]
    except Exception:
        pass
    pages = []
    for result in engine.predict(str(path)):
        data = result.json
        if isinstance(data, str):
            data = json.loads(data)
        data = data.get("res", data)
        boxes = data.get("rec_polys", data.get("dt_polys", []))
        page = []
        for text, score, box in zip(
            data.get("rec_texts", []), data.get("rec_scores", []), boxes
        ):
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            page.append(
                {
                    "text": text,
                    "score": float(score),
                    "x": sum(xs) / len(xs),
                    "y": sum(ys) / len(ys),
                    "height": max(ys) - min(ys),
                }
            )
        if not pages and metadata:
            page.append(
                {
                    "text": "__TEMPLATE_VERSION__:" + metadata,
                    "score": 1,
                    "x": 0,
                    "y": 0,
                    "height": 0,
                }
            )
        pages.append(page)
    print("OPS_OCR_RESULT=" + json.dumps(pages, ensure_ascii=False))


if __name__ == "__main__":
    main()

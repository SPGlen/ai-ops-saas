"""Construct a fresh, immutable-version media view for visual blind scoring."""

import io, json, shutil, subprocess, tempfile
from pathlib import Path
from PIL import Image
from .models import Asset, ContentVersion
from .domain import own
from .integrations.storage import Storage
from .security import fail


def attachments(session, tenant_id, version_id):
    version = own(session, ContentVersion, tenant_id, version_id)
    result = []
    for asset_id in version.assets:
        asset = own(session, Asset, tenant_id, asset_id)
        raw = Storage().read(asset.object_key)
        if asset.mime.startswith("image/"):
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            image.thumbnail((1000, 1400))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85)
            result.append((out.getvalue(), "image/jpeg"))
        elif asset.mime == "video/mp4":
            ffmpeg = shutil.which("ffmpeg")
            ffprobe = shutil.which("ffprobe")
            if not ffmpeg or not ffprobe:
                fail("FFMPEG_UNAVAILABLE", "视频盲评需要FFmpeg抽帧", 503)
            with tempfile.TemporaryDirectory(prefix="ops-blind-") as directory:
                path = Path(directory)
                (path / "input.mp4").write_bytes(raw)
                probe = subprocess.run(
                    [
                        ffprobe,
                        "-v",
                        "error",
                        "-f",
                        "mov",
                        "-show_format",
                        "-of",
                        "json",
                        "input.mp4",
                    ],
                    cwd=directory,
                    capture_output=True,
                    timeout=20,
                    check=True,
                )
                duration = float(json.loads(probe.stdout)["format"]["duration"])
                for i, fraction in enumerate((0.05, 0.5, 0.9)):
                    target = str(i) + ".jpg"
                    subprocess.run(
                        [
                            ffmpeg,
                            "-nostdin",
                            "-v",
                            "error",
                            "-y",
                            "-ss",
                            str(duration * fraction),
                            "-f",
                            "mov",
                            "-i",
                            "input.mp4",
                            "-frames:v",
                            "1",
                            "-vf",
                            "scale=540:-2",
                            target,
                        ],
                        cwd=directory,
                        capture_output=True,
                        timeout=30,
                        check=True,
                    )
                    result.append(((path / target).read_bytes(), "image/jpeg"))
    return result

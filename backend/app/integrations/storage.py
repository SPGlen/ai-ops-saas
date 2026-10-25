import hashlib, io, ipaddress, socket
from pathlib import Path
from urllib.parse import urlparse
import httpx
from ..config import settings
from ..models import Asset, uid
from ..security import fail
from ..domain import own


class Storage:
    def __init__(self):
        self.cfg = settings()

    def client(self):
        import boto3

        return boto3.client(
            "s3",
            endpoint_url=self.cfg.s3_endpoint or None,
            region_name=self.cfg.s3_region,
            aws_access_key_id=self.cfg.s3_access_key or None,
            aws_secret_access_key=self.cfg.s3_secret_key or None,
        )

    def write(self, key, data, mime):
        if self.cfg.s3_bucket:
            self.client().put_object(
                Bucket=self.cfg.s3_bucket,
                Key=key,
                Body=data,
                ContentType=mime,
                ServerSideEncryption="AES256",
            )
        else:
            path = self.cfg.data_dir / "objects" / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

    def read(self, key):
        if self.cfg.s3_bucket:
            return (
                self.client()
                .get_object(Bucket=self.cfg.s3_bucket, Key=key)["Body"]
                .read()
            )
        root = (self.cfg.data_dir / "objects").resolve()
        path = (root / key).resolve()
        if not path.is_relative_to(root):
            fail("PATH_INVALID", "文件路径无效")
        return path.read_bytes()


def save_asset(session, tenant_id, name, data, mime, consent=False, purpose="content"):
    if purpose not in ("content", "receipt", "document"):
        fail("PURPOSE_INVALID", "素材用途无效")
    if len(data) > settings().max_upload_mb * 1024 * 1024 and mime != "video/mp4":
        fail("FILE_TOO_LARGE", "文件过大")
    if len(data) > 200 * 1024 * 1024:
        fail("FILE_TOO_LARGE", "媒体文件不能超过200MB")
    object_id = uid()
    key = tenant_id + "/" + purpose + "/" + object_id
    Storage().write(key, data, mime)
    asset = Asset(
        id=object_id,
        tenant_id=tenant_id,
        object_key=key,
        name=Path(name).name[:150],
        mime=mime,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        consent=consent,
    )
    session.add(asset)
    session.flush()
    return asset


def upload_mime(raw, name):
    if raw.startswith(b"PK") and name.lower().endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if raw.startswith((b"\x89PNG", b"\xff\xd8\xff", b"RIFF")):
        from PIL import Image

        try:
            image = Image.open(io.BytesIO(raw))
            if image.width * image.height > 40000000:
                fail("IMAGE_TOO_LARGE", "图片像素过大，请缩小后上传")
            image.verify()
        except Exception:
            fail("FILE_INVALID", "图片文件无效或像素过大")
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith(b"%PDF-"):
        return "application/pdf"
    if len(raw) > 12 and raw[4:8] == b"ftyp":
        return "video/mp4"
    if Path(name).suffix.lower() in (".txt", ".md"):
        try:
            raw.decode("utf8")
        except UnicodeDecodeError:
            fail("FILE_INVALID", "文本需要UTF-8编码")
        return "text/plain"
    fail("FILE_TYPE_INVALID", "支持 PNG、JPEG、WebP、PDF、MP4 和 UTF-8 文本")


def validate_result_url(url):
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        fail("RESULT_URL_INVALID", "供应商返回了不安全的媒体地址")
    host = parsed.hostname or ""
    if not (host.endswith(".aliyuncs.com") or host.endswith(".aliyun.com")):
        fail("RESULT_HOST_INVALID", "媒体结果域名尚未获准")
    for address in socket.getaddrinfo(host, 443):
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            fail("RESULT_ADDRESS_INVALID", "媒体地址不能指向内网")


def download_result(url):
    for _ in range(4):
        validate_result_url(url)
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            with client.stream("GET", url) as response:
                if response.is_redirect:
                    from urllib.parse import urljoin

                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 200 * 1024 * 1024:
                        fail("RESULT_TOO_LARGE", "生成结果超过200MB")
                    chunks.append(chunk)
                return b"".join(chunks)
    fail("RESULT_REDIRECT_LIMIT", "媒体下载重定向过多")

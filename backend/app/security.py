import base64, hashlib, hmac, json, secrets
from datetime import timedelta
from cryptography.fernet import Fernet, InvalidToken
from pwdlib import PasswordHash
from fastapi import HTTPException
from sqlmodel import Session, select
from .config import settings
from .models import now, RateBucket

password_hasher = PasswordHash.recommended()


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(value: str):
    return password_hasher.hash(value)


def password_valid(value: str, hashed: str):
    try:
        return password_hasher.verify(value, hashed)
    except Exception:
        return False


def cipher():
    key = hashlib.sha256(settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(tenant_id: str, value):
    return (
        cipher()
        .encrypt(
            json.dumps(
                {"tenant": tenant_id, "value": value}, ensure_ascii=False
            ).encode()
        )
        .decode()
    )


def decrypt(tenant_id: str, value: str):
    try:
        payload = json.loads(cipher().decrypt(value.encode()))
        if not hmac.compare_digest(payload["tenant"], tenant_id):
            raise ValueError()
        return payload["value"]
    except (InvalidToken, ValueError, KeyError):
        raise HTTPException(
            500,
            detail={
                "code": "CREDENTIAL_INTEGRITY_ERROR",
                "message": "凭证不可用，请重新配置",
            },
        )


def fail(code: str, message: str, status=400):
    raise HTTPException(status, detail={"code": code, "message": message})


def limit(session: Session, key: str, maximum: int, seconds=60):
    bucket_id = digest(settings().secret_key + key)
    bucket = session.exec(
        select(RateBucket)
        .where(RateBucket.id == bucket_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    if not bucket:
        bucket = RateBucket(id=bucket_id)
    if bucket.window_start < now() - timedelta(seconds=seconds):
        bucket.hits = 0
        bucket.window_start = now()
    if bucket.hits >= maximum:
        fail("RATE_LIMITED", "操作过于频繁，请稍后再试", 429)
    bucket.hits += 1
    session.add(bucket)
    session.commit()


def random_token():
    return secrets.token_urlsafe(32)


def redact_error(error):
    text = str(error)
    import re

    text = re.sub(r"(?:sk-|Bearer\s+)[A-Za-z0-9._-]+", "[redacted]", text)
    text = re.sub(r"https?://\S+", "[provider URL]", text)
    return text[:240]

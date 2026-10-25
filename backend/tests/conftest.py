import os
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
from app.config import settings
from app.db import engine, initialize
from app.models import User, Tenant, Membership, PlatformSettings, now
from app.security import password_hash


@pytest.fixture
def appenv(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "OPS_DATABASE_URL", "sqlite:///" + str(tmp_path / "test.db").replace("\\", "/")
    )
    monkeypatch.setenv("OPS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv(
        "OPS_SECRET_KEY", "testing-secret-not-used-for-production-123456"
    )
    monkeypatch.setenv("OPS_TASK_MODE", "test")
    monkeypatch.setenv("OPS_ENVIRONMENT", "development")
    monkeypatch.setenv("OPS_ALIYUN_API_KEY", "")
    monkeypatch.setenv("OPS_DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("OPS_TEXT_PROVIDER", "aliyun")
    settings.cache_clear()
    engine.cache_clear()
    initialize()
    with Session(engine()) as s:
        s.add(
            PlatformSettings(
                free_until=now() + timedelta(days=30),
                plans={
                    "prices": {
                        "text_million_fen": 1000,
                        "image_fen": 20,
                        "video_second_fen": 60,
                    }
                },
            )
        )
        for suffix in ("a", "b"):
            user = User(
                id="user-" + suffix,
                email=suffix + "@example.com",
                name="机构" + suffix,
                verified=True,
                password_hash=password_hash("Test-Password-2026!"),
                platform_admin=suffix == "a",
            )
            tenant = Tenant(
                id="tenant-" + suffix,
                slug="org-" + suffix,
                name="机构" + suffix,
                settings={
                    "quotas": {},
                    "funding": "platform",
                    "ops_schema_version": 3,
                    "legacy_maintenance": True,
                    "consultation_enabled": True,
                },
            )
            s.add(user)
            s.add(tenant)
            s.flush()
            s.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))
        s.commit()
    from app.main import app

    with TestClient(app) as client:
        yield client
    engine().dispose()
    engine.cache_clear()
    settings.cache_clear()


def login(client, suffix="a"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": suffix + "@example.com", "password": "Test-Password-2026!"},
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies.get("ops_csrf")
    return client


def add(client, kind, data):
    response = client.post("/api/v1/records/" + kind, json={"data": data})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def client(appenv):
    return login(appenv)

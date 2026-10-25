import io, base64, json, hashlib, hmac, struct, time
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from PIL import Image
from app.models import *
from app.db import engine, set_scope, TENANT_TABLES, rls_statements
from app.domain import reserve, settle, query
from app.worker import execute, reserve_job
from app.integrations import aliyun, publishing
from app.security import encrypt, decrypt
from .conftest import login, add


def configure(monkeypatch, quotas=None):
    monkeypatch.setattr(
        aliyun,
        "config",
        lambda *args: ("test-not-real", "https://dashscope.aliyuncs.com"),
    )
    with Session(engine()) as s:
        t = s.get(Tenant, "tenant-a")
        t.settings = {
            **t.settings,
            "quotas": quotas
            or {
                "text_tokens": 1000000,
                "images": 10,
                "video_seconds": 100,
                "speech_characters": 1000,
                "cost_fen": 100000,
            },
        }
        s.add(t)
        s.commit()


def content(client, assets=None):
    r = client.post(
        "/api/v1/contents",
        json={
            "title": "孩子如何认识AI",
            "body": "先观察，再提出具体问题，一起比较工具回答和真实世界。",
            "assets": assets or [],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def png():
    out = io.BytesIO()
    Image.new("RGB", (32, 32), "green").save(out, format="PNG")
    return out.getvalue()


def asset(client, consent=True):
    r = client.post(
        "/api/v1/assets",
        data={"purpose": "content", "consent": str(consent).lower()},
        files={"file": ("test.png", png(), "image/png")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_quota_zero_by_default_and_no_key_fallback(client, monkeypatch):
    configure(monkeypatch, {"images": 0})
    r = client.post(
        "/api/v1/media-jobs",
        json={"kind": "image", "prompt": "教育插图", "request_id": "image-budget-01"},
    )
    assert r.status_code == 402
    assert client.get("/api/v1/usage").json()["items"] == []


def test_quota_reservation_settlement_are_idempotent(client):
    with Session(engine()) as s:
        t = s.get(Tenant, "tenant-a")
        t.settings = {"quotas": {"images": 5}}
        s.add(t)
        s.commit()
        set_scope(s, t.id)
        a = reserve(s, t.id, "reserve-one", "images", 3)
        s.commit()
        b = reserve(s, t.id, "reserve-one", "images", 3)
        assert a.id == b.id
        with pytest.raises(HTTPException):
            reserve(s, t.id, "reserve-two", "images", 3)
        s.rollback()
        settle(s, t.id, "reserve-one", "images", 2, 40)
        s.commit()
        settle(s, t.id, "reserve-one", "images", 2, 40)
        s.commit()
        bucket = s.exec(select(BudgetBucket)).one()
        assert (bucket.used, bucket.reserved) == (2, 0)


def test_byok_is_explicit_and_separately_metered(client, monkeypatch):
    configure(monkeypatch, {"images": 0})
    r = client.post(
        "/api/v1/media-jobs",
        json={
            "kind": "image",
            "prompt": "教育插图",
            "funding": "byok",
            "request_id": "image-byok-one",
        },
    )
    assert r.status_code == 202, r.text
    usage = client.get("/api/v1/usage").json()
    assert usage["items"][0]["funding"] == "byok"
    assert usage["buckets"] == []


def test_credentials_are_tenant_bound_and_never_returned(client):
    r = client.put(
        "/api/v1/integrations/aliyun",
        json={"secret": "sk-fake-test-only-credential", "config": {}},
    )
    assert r.status_code == 200
    assert "sk-fake" not in client.get("/api/v1/integrations").text
    with Session(engine()) as s:
        value = s.exec(select(Integration)).one().secret_cipher
        assert "sk-fake" not in value
        with pytest.raises(HTTPException):
            decrypt("tenant-b", value)
    assert (
        client.put(
            "/api/v1/integrations/aliyun",
            json={"secret": "fake", "config": {"base_url": "http://127.0.0.1:1234"}},
        ).status_code
        == 400
    )


def test_assets_are_private_and_purpose_limited(client):
    image = asset(client)
    assert client.get("/api/v1/assets/" + image["id"] + "/download").content == png()
    login(client, "b")
    assert client.get("/api/v1/assets/" + image["id"] + "/download").status_code == 404
    assert client.get("/api/v1/assets").json() == []


def test_prediction_is_blind_and_append_only(client, monkeypatch):
    configure(monkeypatch)
    c = content(client)
    version = c["versions"][0]
    from app.agents import RubricScore

    prompts = []

    def fake(s, t, f, instructions, prompt, output_type, **kwargs):
        prompts.append(json.loads(prompt))
        return RubricScore(
            **{
                k: 3
                for k in (
                    "clarity",
                    "relevance",
                    "usefulness",
                    "credibility",
                    "narrative",
                    "actionability",
                    "accessibility",
                )
            },
            reasoning="逐项核对主题、课程依据和可执行的行动建议。",
            bet="预测收藏意愿高于泛工具展示内容。",
        ), 100

    monkeypatch.setattr(aliyun, "text_agent", fake)
    r = client.post(
        "/api/v1/runs",
        json={
            "kind": "predict",
            "request_id": "predict-blind-01",
            "input": {"version_id": version["id"]},
        },
    )
    assert r.status_code == 202, r.text
    execute("agent", "tenant-a", r.json()["id"])
    assert not any(
        k in json.dumps(prompts) for k in ("metrics", "plays", "retro", "conversation")
    )
    with Session(engine()) as s:
        pred = s.exec(select(Prediction)).one()
        assert pred.content_hash == version["content_hash"]
        assert pred.rubric_version == "edu-image_text-v0"
        with pytest.raises(IntegrityError):
            s.execute(text("UPDATE predictions SET content_hash=:h"), {"h": "tampered"})
            s.commit()
        s.rollback()
    newer = client.patch(
        "/api/v1/contents/" + c["id"],
        json={
            "title": "一个新问题",
            "body": "新版本会生成新的哈希，历史预测继续保留。",
            "version": 1,
        },
    ).json()
    assert len(newer["versions"]) == 2 and len(newer["predictions"]) == 1


def test_video_persisted_id_restarts_never_resubmit(client, monkeypatch):
    configure(monkeypatch)
    submitted = []
    monkeypatch.setattr(
        aliyun,
        "submit_video",
        lambda *a: submitted.append("one") or ("provider-id-1", "request-id-1"),
    )
    monkeypatch.setattr(
        aliyun, "video_status", lambda *a: {"output": {"task_status": "RUNNING"}}
    )
    body = {
        "kind": "video",
        "prompt": "教育场景，孩子观察树木",
        "request_id": "video-persist-01",
    }
    r = client.post("/api/v1/media-jobs", json=body)
    assert r.status_code == 202, r.text
    execute("media", "tenant-a", r.json()["id"])
    execute("media", "tenant-a", r.json()["id"])
    assert submitted == ["one"]
    row = client.get("/api/v1/media-jobs").json()[0]
    assert row["provider_task_id"] == "provider-id-1" and row["status"] == "polling"
    again = client.post("/api/v1/media-jobs", json=body)
    assert again.json()["id"] == row["id"]


def test_paid_video_submission_timeout_holds_quota(client, monkeypatch):
    configure(monkeypatch)
    calls = []

    def uncertain(*a):
        calls.append(1)
        raise TimeoutError()

    monkeypatch.setattr(aliyun, "submit_video", uncertain)
    r = client.post(
        "/api/v1/media-jobs",
        json={
            "kind": "video",
            "prompt": "一段教育视频",
            "request_id": "video-timeout-01",
        },
    ).json()
    execute("media", "tenant-a", r["id"])
    execute("media", "tenant-a", r["id"])
    assert len(calls) == 1
    assert client.get("/api/v1/media-jobs").json()[0]["status"] == "unknown"
    assert client.post("/api/v1/jobs/media/" + r["id"] + "/cancel").status_code == 400
    assert any(
        u["state"] == "reserved" for u in client.get("/api/v1/usage").json()["items"]
    )


def test_usage_price_is_snapshotted(client, monkeypatch):
    configure(monkeypatch)
    from app.worker import finish_usage

    with Session(engine()) as s:
        set_scope(s, "tenant-a")
        reserve_job(s, "tenant-a", "price-snapshot", "images", 1, "platform")
        s.commit()
        cfg = s.get(PlatformSettings, 1)
        cfg.plans = {"prices": {"image_fen": 999}}
        s.add(cfg)
        s.commit()
        finish_usage(s, "tenant-a", "price-snapshot", "images", 1, "platform")
        s.commit()
        row = s.exec(select(UsageRecord).where(UsageRecord.resource == "images")).one()
        assert row.cost_fen == 20


def test_publish_requires_prediction_and_consent(client):
    a = asset(client, False)
    c = content(client, [a["id"]])
    account = client.post(
        "/api/v1/social-accounts", json={"platform": "xiaohongshu", "name": "测试号"}
    ).json()
    r = client.post(
        "/api/v1/contents/" + c["id"] + "/publish",
        json={
            "account_id": account["id"],
            "scheduled_at": now().isoformat(),
            "request_id": "publish-guard-01",
        },
    )
    assert r.status_code == 400
    assert not c["versions"][0]["policy_checked"]


def test_unknown_publication_is_never_replayed(client, monkeypatch):
    a = asset(client)
    c = content(client, [a["id"]])
    version = c["versions"][0]
    with Session(engine()) as s:
        t = s.get(Tenant, "tenant-a")
        t.settings = {**t.settings, "publishing_enabled": True}
        s.add(t)
        s.add(
            Prediction(
                tenant_id="tenant-a",
                version_id=version["id"],
                content_hash=version["content_hash"],
                rubric_version="test",
                payload={"credibility": 3},
            )
        )
        s.commit()
    account = client.post(
        "/api/v1/social-accounts", json={"platform": "xiaohongshu", "name": "测试号"}
    ).json()
    monkeypatch.setattr(
        __import__("app.worker", fromlist=["settings"]).settings(),
        "allow_live_publish",
        True,
    )
    monkeypatch.setattr(publishing, "check_login", lambda *a: {"status": "connected"})
    count = []
    monkeypatch.setattr(
        publishing, "publish", lambda *a: count.append(1) or {"status": "unknown"}
    )
    r = client.post(
        "/api/v1/contents/" + c["id"] + "/publish",
        json={
            "account_id": account["id"],
            "scheduled_at": now().isoformat(),
            "request_id": "publish-unknown-01",
        },
    ).json()
    execute("publish", "tenant-a", r["id"])
    execute("publish", "tenant-a", r["id"])
    assert (
        count == [1]
        and client.get("/api/v1/publish-jobs").json()[0]["status"] == "unknown"
    )


def test_takeover_during_ai_generation_discards_bot_reply(client, monkeypatch):
    configure(monkeypatch)
    chat = client.post("/api/v1/public/org-a/chat").json()
    client.post(
        "/api/v1/public/org-a/chat/" + chat["id"],
        headers={"X-Public-Token": chat["token"]},
        json={"body": "课程什么时候上"},
    )
    from app.agents import ChatAnswer

    def fake(*args, **kw):
        with Session(engine()) as s:
            c = s.get(Conversation, chat["id"])
            c.state = "human"
            s.add(c)
            s.commit()
        return ChatAnswer(answer="交给同事确认。", source_ids=[], needs_human=True), 100

    monkeypatch.setattr(aliyun, "text_agent", fake)
    with Session(engine()) as s:
        run = s.exec(select(AgentRun).where(AgentRun.kind == "chat")).one()
    execute("agent", "tenant-a", run.id)
    messages = client.get("/api/v1/conversations/" + chat["id"]).json()["messages"]
    assert len(messages) == 2


def test_low_samples_prevent_rubric_upgrade(client):
    body = {
        "form": "video",
        "weights": {
            k: 1
            for k in (
                "clarity",
                "relevance",
                "usefulness",
                "credibility",
                "narrative",
                "actionability",
                "accessibility",
            )
        },
        "notes": "根据复盘样本提出权重变更，等待全量重算与独立复核。",
        "request_id": "rubric-test-001",
    }
    assert client.post("/api/v1/rubrics", json=body).status_code == 400
    active = client.get("/api/v1/rubrics").json()["active"]
    assert active["video"]["version"] != active["image_text"]["version"]


def test_wecom_crypto_and_tamper_rejection(client):
    from app.integrations.wecom import verify_signature, decrypt_message
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = b"k" * 32
    body = b"<xml>example</xml>"
    receiver = b"corporation-id"
    raw = b"r" * 16 + struct.pack("!I", len(body)) + body + receiver
    n = 32 - len(raw) % 32
    raw += bytes([n]) * n
    enc = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    value = base64.b64encode(enc.update(raw) + enc.finalize()).decode()
    assert (
        decrypt_message(
            base64.b64encode(key).decode().rstrip("="), value, "corporation-id"
        )
        == body.decode()
    )
    timestamp = str(int(time.time()))
    sig = hashlib.sha1(
        "".join(sorted(["test-token", timestamp, "nonce", value])).encode()
    ).hexdigest()
    verify_signature("test-token", timestamp, "nonce", value, sig)
    with pytest.raises(HTTPException):
        verify_signature("test-token", timestamp, "nonce", value, "f" * 40)
    with pytest.raises(HTTPException):
        decrypt_message(
            base64.b64encode(key).decode().rstrip("="), value, "other-corporation"
        )


def test_result_download_ssrf_rejected(client):
    from app.integrations.storage import validate_result_url

    for url in (
        "http://example.com/a",
        "https://127.0.0.1/a",
        "https://example.com/a",
        "https://u:p@oss.aliyuncs.com/a",
    ):
        with pytest.raises(HTTPException):
            validate_result_url(url)


def test_booking_qr_and_unapproved_facts_private(client):
    add(client, "course", {"name": "内部未确认课程", "approved": False})
    assert client.get("/api/v1/public/org-a").json()["courses"] == []
    response = client.get("/api/v1/tenant/booking-qr")
    assert response.content.startswith(b"\x89PNG")


def test_rls_policy_covers_all_scoped_tables(client):
    scoped = {
        t.name
        for t in SQLModel.metadata.sorted_tables
        if "tenant_id" in t.columns and t.name not in ("memberships", "auth_sessions")
    }
    assert scoped == set(TENANT_TABLES)
    assert len(rls_statements()) == len(scoped) * 3
    assert all("WITH CHECK" in s for s in rls_statements() if "CREATE POLICY" in s)


def test_limit_retries_keep_one_reservation(client, monkeypatch):
    configure(monkeypatch)

    def limited(*a):
        raise HTTPException(
            429, detail={"code": "MODEL_RATE_LIMITED", "message": "供应商限流"}
        )

    monkeypatch.setattr(aliyun, "create_image", limited)
    r = client.post(
        "/api/v1/media-jobs",
        json={"kind": "image", "prompt": "教育插图", "request_id": "image-limited-01"},
    ).json()
    execute("media", "tenant-a", r["id"])
    jobs = client.get("/api/v1/media-jobs").json()
    assert jobs[0]["status"] == "retrying"
    usage = client.get("/api/v1/usage").json()
    assert len(usage["items"]) == 2 and all(
        x["state"] == "reserved" for x in usage["items"]
    )
    assert client.post("/api/v1/jobs/media/" + r["id"] + "/cancel").status_code == 200


def test_actor_role_revoked_before_background_task(client, monkeypatch):
    configure(monkeypatch)
    r = client.post(
        "/api/v1/runs",
        json={
            "kind": "content",
            "request_id": "revoked-role-01",
            "input": {"topic": "AI课程"},
        },
    ).json()
    with Session(engine()) as s:
        member = s.exec(select(Membership).where(Membership.user_id == "user-a")).one()
        member.role = "finance"
        s.add(member)
        s.commit()
    calls = []
    monkeypatch.setattr(aliyun, "text_agent", lambda *a: calls.append(1))
    execute("agent", "tenant-a", r["id"])
    assert not calls
    with Session(engine()) as s:
        run = s.get(AgentRun, r["id"])
        assert run.error_code == "ROLE_REVOKED"


def test_policy_rechecks_course_price_and_canonical_facts(client):
    c = add(client, "course", {"name": "启蒙课", "price_fen": 198000, "approved": True})
    bad = client.post(
        "/api/v1/contents",
        json={"title": "试听介绍", "body": "启蒙课价格为1990元，请咨询老师。"},
    ).json()
    assert not bad["versions"][0]["policy_checked"]
    from app.agents import knowledge

    with Session(engine()) as s:
        facts = knowledge(s, "tenant-a", "多少钱")
        assert any(x["id"] == c["id"] and "1980" in x["body"] for x in facts)


def test_finished_prediction_rejects_form_mutation(client):
    c = content(client)
    response = client.patch(
        "/api/v1/contents/" + c["id"],
        json={"title": "视频稿", "body": "这是新脚本", "version": 1, "form": "video"},
    )
    assert response.status_code == 400


def test_provider_success_parser_does_not_trust_redirects_or_upload_ids():
    from publisher.platforms import publication_response

    assert (
        publication_response(
            "douyin",
            "https://creator.douyin.com/upload",
            {"status_code": 0, "aweme_id": "1234567890"},
        )
        is None
    )
    assert (
        publication_response(
            "douyin",
            "https://evil.example/aweme/create",
            {"status_code": 0, "aweme_id": "1234567890"},
        )
        is None
    )
    assert (
        publication_response(
            "douyin",
            "https://creator.douyin.com/web/api/media/aweme/create_v2/",
            {"status_code": 0, "aweme_id": "1234567890"},
        )["external_id"]
        == "1234567890"
    )


def test_card_renderer_is_deterministic_and_bounded():
    from app.integrations.rendering import cards

    first = cards(
        png(),
        "一起认识AI",
        "观察生活，提出一个问题。然后比较工具回答与事实。",
        "演示课堂",
    )
    second = cards(
        png(),
        "一起认识AI",
        "观察生活，提出一个问题。然后比较工具回答与事实。",
        "演示课堂",
    )
    assert hashlib.sha256(first[0]).digest() == hashlib.sha256(second[0]).digest()
    assert Image.open(io.BytesIO(first[0])).size == (1080, 1440)


def test_reply_events_and_chunked_body_limit(client):
    with Session(engine()) as s:
        run = AgentRun(
            tenant_id="tenant-a",
            kind="content",
            request_id="sse-failed-job",
            actor_id="user-a",
            status="failed",
        )
        s.add(run)
        s.commit()
        job_id = run.id
    response = client.get("/api/v1/jobs/agent/" + job_id + "/events")
    assert (
        "\nevent: status\ndata: " in response.text and "\\nevent" not in response.text
    )

    def chunks():
        for _ in range(5):
            yield b"x" * 65536

    assert (
        client.post(
            "/api/v1/auth/register",
            content=chunks(),
            headers={"Content-Type": "application/json"},
        ).status_code
        == 413
    )


def test_receipt_cannot_be_published_as_content(client):
    r = client.post(
        "/api/v1/assets",
        data={"purpose": "receipt", "consent": "true"},
        files={"file": ("receipt.png", png(), "image/png")},
    )
    assert r.status_code == 201
    c = client.post(
        "/api/v1/contents",
        json={
            "title": "票据不应公开",
            "body": "内部票据禁止通过内容发布绕过权限。",
            "assets": [r.json()["id"]],
        },
    )
    assert c.status_code == 403


def test_billed_output_validation_failure_does_not_refund_consumed_tokens(
    client, monkeypatch
):
    configure(monkeypatch)
    from app.agents import ContentDraft

    monkeypatch.setattr(
        aliyun,
        "text_agent",
        lambda *a, **kw: (
            ContentDraft(
                title="家长关心的AI课",
                body="这是一段依据未知来源编写、应被业务检查拒绝的文案。",
                image_prompt="插画",
                video_prompt="视频描述",
                cards=["观察生活"],
                source_ids=["wrong-source-id"],
            ),
            150,
        ),
    )
    add(client, "knowledge", {"name": "课程事实", "body": "8节AI课", "approved": True})
    r = client.post(
        "/api/v1/runs",
        json={
            "kind": "content",
            "request_id": "paid-reject-01",
            "input": {"topic": "介绍课程"},
        },
    ).json()
    execute("agent", "tenant-a", r["id"])
    usage = client.get("/api/v1/usage").json()["items"]
    token = next(x for x in usage if x["resource"] == "text_tokens")
    assert token["state"] == "settled" and token["actual"] == 150
    assert client.get("/api/v1/runs").json()[0]["status"] == "failed"


def test_wecom_callback_receipt_is_deduplicated(client):
    from app.integrations.wecom import Cipher, algorithms, modes

    key = b"w" * 32
    token = "test-callback-token"
    corpid = "test-corp"
    kfid = "test-kfid"
    client.put(
        "/api/v1/integrations/wecom",
        json={
            "secret": "test-only-secret",
            "config": {
                "corpid": corpid,
                "open_kfid": kfid,
                "token": token,
                "encoding_aes_key": base64.b64encode(key).decode().rstrip("="),
            },
        },
    )
    xml = b"<xml><Event>kf_msg_or_event</Event><Token>test-pull-token</Token><OpenKfId>test-kfid</OpenKfId></xml>"
    raw = b"r" * 16 + struct.pack("!I", len(xml)) + xml + corpid.encode()
    n = 32 - len(raw) % 32
    raw += bytes([n]) * n
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key[:16])).encryptor()
    value = base64.b64encode(encryptor.update(raw) + encryptor.finalize()).decode()
    timestamp = str(int(time.time()))
    nonce = "test-nonce"
    sig = hashlib.sha1(
        "".join(sorted([token, timestamp, nonce, value])).encode()
    ).hexdigest()
    path = "/api/v1/webhooks/wecom/tenant-a"
    params = {"msg_signature": sig, "timestamp": timestamp, "nonce": nonce}
    for _ in range(2):
        response = client.post(
            path,
            params=params,
            content="<xml><Encrypt>" + value + "</Encrypt></xml>",
            headers={"Content-Type": "text/xml"},
        )
        assert response.status_code == 200, response.text
    with Session(engine()) as s:
        assert len(s.exec(select(WebhookReceipt)).all()) == 1
        assert (
            len(s.exec(select(AgentRun).where(AgentRun.kind == "wecom_event")).all())
            == 1
        )


def test_wecom_duplicate_messages_and_explicit_human_request(client, monkeypatch):
    from app.integrations import wecom

    config = {
        "corpid": "test-corp",
        "open_kfid": "test-kfid",
        "token": "test-token",
        "encoding_aes_key": base64.b64encode(b"x" * 32).decode().rstrip("="),
    }
    client.put(
        "/api/v1/integrations/wecom",
        json={"secret": "test-only-secret", "config": config},
    )
    msg = {
        "msgid": "same-message-id",
        "origin": 3,
        "msgtype": "text",
        "external_userid": "test-customer",
        "text": {"content": "请转人工"},
    }
    monkeypatch.setattr(
        wecom,
        "api",
        lambda *a: {
            "msg_list": [msg, msg],
            "next_cursor": "cursor-after",
            "has_more": False,
        },
    )
    with Session(engine(), expire_on_commit=False) as s:
        set_scope(s, "tenant-a")
        event = {
            "event_cipher": encrypt(
                "tenant-a", {"token": "test-pull", "open_kfid": "test-kfid"}
            )
        }
        wecom.sync_messages(s, "tenant-a", event)
        wecom.sync_messages(s, "tenant-a", event)
        assert len(s.exec(select(Conversation)).all()) == 1
        assert len(s.exec(select(Message)).all()) == 1
        assert s.exec(select(Conversation)).one().state == "waiting_human"

import json
import httpx
import pytest
from sqlmodel import Session, select
from app.db import engine, set_scope
from app.models import AgentRun, Tenant, UsageRecord, Membership, PlatformSettings, ReportSnapshot
from app.worker import execute
from app.integrations import deepseek
from app.model_router import TextModelSettings
from app.security import decrypt
from .conftest import login


def enable(client, **changes):
    r = client.put('/api/v1/integrations/deepseek', json={'secret': 'sk-test-deepseek-not-real', 'config': {}})
    assert r.status_code == 200, r.text
    cfg = TextModelSettings(provider='deepseek', funding='byok').model_dump()
    cfg.update(changes)
    r = client.put('/api/v1/ai-settings', json=cfg)
    assert r.status_code == 200, r.text
    return cfg


def mock_api(monkeypatch, *, content='{"ok":true}', code=200, timeout=False):
    original = deepseek.AsyncOpenAI
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        assert request.url.host == 'api.deepseek.com'
        assert str(request.url.path) == '/chat/completions'
        assert request.headers['authorization'] == 'Bearer sk-test-deepseek-not-real'
        if timeout:
            raise httpx.ReadTimeout('test response lost', request=request)
        if code != 200:
            return httpx.Response(code, json={'error': {'message': 'secret must not be returned', 'type': 'test_error'}})
        return httpx.Response(200, json={'id': 'chatcmpl-test-only', 'created': 0, 'object': 'chat.completion',
            'model': calls[-1]['model'], 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': content}}],
            'usage': {'prompt_tokens': 1000, 'completion_tokens': 100, 'total_tokens': 1100, 'prompt_cache_hit_tokens': 100}})
    def sdk(**kwargs):
        kwargs['http_client'] = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return original(**kwargs)
    monkeypatch.setattr(deepseek, 'AsyncOpenAI', sdk)
    return calls


def probe(client, request_id='deepseek-probe-01'):
    r = client.post('/api/v1/ai-settings/test', json={'request_id': request_id})
    assert r.status_code == 202, r.text
    return r.json()


def test_deepseek_probe_real_sdk_json_usage_and_idempotency(client, monkeypatch):
    enable(client)
    calls = mock_api(monkeypatch)
    row = probe(client)
    execute('agent', 'tenant-a', row['id'])
    execute('agent', 'tenant-a', row['id'])
    assert probe(client)['id'] == row['id']
    assert len(calls) == 1
    assert calls[0]['thinking'] == {'type': 'disabled'}
    assert calls[0]['response_format'] == {'type': 'json_object'}
    assert calls[0]['max_tokens'] == 256
    result = client.get('/api/v1/runs/' + row['id']).json()
    assert result['status'] == 'succeeded', result
    assert result['output']['ok'] is True
    usages = client.get('/api/v1/usage').json()['items']
    u = next(x for x in usages if x['resource'] == 'text_tokens')
    assert (u['actual'], u['cost_fen'], u['funding'], u['state']) == (1100, 1, 'byok', 'settled')
    assert u['model_usage']['calls'][0]['cached_tokens'] == 100
    assert client.get('/api/v1/usage').json()['buckets'] == []
    assert 'sk-test' not in client.get('/api/v1/integrations').text
    assert 'sk-test' not in json.dumps(result)


def test_queued_model_and_rates_are_frozen_without_secret_copy(client, monkeypatch):
    cfg = enable(client)
    calls = mock_api(monkeypatch)
    row = probe(client)
    cfg.update(model='deepseek-v4-pro', input_million_fen=900, output_million_fen=2700)
    assert client.put('/api/v1/ai-settings', json=cfg).status_code == 200
    execute('agent', 'tenant-a', row['id'])
    assert calls[0]['model'] == 'deepseek-flash'
    with Session(engine()) as s:
        u = s.exec(select(UsageRecord).where(UsageRecord.request_id == row['request_id'])).one()
        assert u.cost_fen == 1 and u.model_usage['route']['rates']['output'] == 800
        assert 'sk-test' not in json.dumps(u.model_usage)


def test_key_revocation_blocks_queued_calls_and_no_cross_provider_fallback(client, monkeypatch):
    enable(client)
    calls = mock_api(monkeypatch)
    row = probe(client)
    assert client.delete('/api/v1/integrations/deepseek').status_code == 200
    execute('agent', 'tenant-a', row['id'])
    assert calls == []
    result = client.get('/api/v1/runs/' + row['id']).json()
    assert result['status'] == 'waiting_authorization'
    assert result['error_code'] == 'KEY_REQUIRED'
    assert all(x['state'] == 'settled' and x['actual'] == 0 for x in client.get('/api/v1/usage').json()['items'])


@pytest.mark.parametrize('status,error', [(401,'MODEL_KEY_REJECTED'),(402,'MODEL_BALANCE_INSUFFICIENT'),(400,'MODEL_REQUEST_REJECTED')])
def test_provider_rejections_are_safe_and_release_reservations(client, monkeypatch, status, error):
    enable(client)
    calls = mock_api(monkeypatch, code=status)
    row = probe(client)
    execute('agent', 'tenant-a', row['id'])
    result = client.get('/api/v1/runs/' + row['id']).json()
    assert result['status'] == 'failed' and result['error_code'] == error
    assert 'secret must not' not in json.dumps(result)
    assert len(calls) == 1
    assert all(x['actual'] == 0 for x in client.get('/api/v1/usage').json()['items'])


def test_timeout_does_not_resubmit_paid_call(client, monkeypatch):
    enable(client)
    calls = mock_api(monkeypatch, timeout=True)
    row = probe(client)
    execute('agent', 'tenant-a', row['id'])
    execute('agent', 'tenant-a', row['id'])
    result = client.get('/api/v1/runs/' + row['id']).json()
    assert result['status'] == 'unknown', result
    assert len(calls) == 1
    assert client.get('/api/v1/usage').json()['items'][0]['state'] == 'reserved'


def test_invalid_json_records_consumption_before_failure(client, monkeypatch):
    enable(client)
    mock_api(monkeypatch, content='{"ok":"not-valid"}')
    row = probe(client)
    execute('agent', 'tenant-a', row['id'])
    result = client.get('/api/v1/runs/' + row['id']).json()
    assert result['error_code'] == 'MODEL_OUTPUT_INVALID'
    u = client.get('/api/v1/usage').json()['items'][0]
    assert u['actual'] == 1100 and u['cost_fen'] == 1 and u['state'] == 'settled'


def test_rate_limit_retains_hold_and_uses_existing_backoff(client, monkeypatch):
    enable(client)
    mock_api(monkeypatch, code=429)
    row = probe(client)
    execute('agent', 'tenant-a', row['id'])
    result = client.get('/api/v1/runs/' + row['id']).json()
    assert result['status'] == 'retrying' and result['output']['_retry_count'] == 1
    assert client.get('/api/v1/usage').json()['items'][0]['state'] == 'reserved'


def test_deepseek_configuration_rejects_urls_and_unknown_models(client):
    assert client.put('/api/v1/integrations/deepseek', json={'secret':'test', 'config': {'base_url':'http://127.0.0.1'}}).status_code == 400
    assert client.put('/api/v1/ai-settings', json={'provider':'deepseek','model':'unapproved-model'}).status_code == 400
    assert client.put('/api/v1/ai-settings', json={'provider':'deepseek','cached_million_fen':10000}).status_code == 400


def test_tenant_and_employee_isolation_for_credentials_settings_and_runs(client, monkeypatch):
    enable(client)
    row = probe(client)
    login(client, 'b')
    assert client.get('/api/v1/integrations').json() == []
    assert not client.get('/api/v1/ai-settings').json()['credential_configured']
    assert client.get('/api/v1/runs/' + row['id']).status_code == 404
    with Session(engine()) as s:
        s.add(Membership(tenant_id='tenant-a', user_id='user-b', role='teacher', roles=['teacher']))
        s.commit()
    r = client.post('/api/v1/auth/switch-tenant', json={'tenant_id':'tenant-a'})
    assert r.status_code == 200, r.text
    assert client.get('/api/v1/ai-settings').status_code == 403
    assert client.put('/api/v1/ai-settings', json=TextModelSettings().model_dump()).status_code == 403
    assert client.post('/api/v1/ai-settings/test', json={'request_id':'no-teacher-probe'}).status_code == 403
    assert client.get('/api/v1/runs/' + row['id']).status_code == 403


def test_platform_selection_never_uses_tenant_key_and_requires_configured_rates(client):
    cfg = enable(client)
    cfg['funding'] = 'platform'
    assert client.put('/api/v1/ai-settings', json=cfg).status_code == 200
    assert not client.get('/api/v1/ai-settings').json()['credential_configured']
    r = client.post('/api/v1/ai-settings/test', json={'request_id':'platform-no-fallback'})
    assert r.status_code == 503
    assert client.get('/api/v1/usage').json()['items'] == []


def test_report_analysis_sends_aggregates_only_and_preserves_snapshot(client, monkeypatch):
    enable(client)
    payload={'baseline_status':'needs_calibration','metrics':{'new_students':None,'new_leads':5},
             'family_feedback':{'count':1,'average_rating':3,'record_ids':['private-id']},
             'finance':{'totals':{'received_fen':198000},'entries':[{'contact':'13812345678','student':'private-child'}]}}
    with Session(engine()) as s:
        report=ReportSnapshot(tenant_id='tenant-a',kind='weekly',period='2026-10-19',version=1,digest='test',payload=payload)
        s.add(report);s.commit();rid=report.id
    calls=mock_api(monkeypatch,content=json.dumps({'summary':'本周新增五条线索，新增在读人数尚待校准，应先核对期初数据。','actions':['核对期初名单'],'limitations':['在读指标待校准']},ensure_ascii=False))
    r=client.post('/api/v1/runs',json={'kind':'report_summary','request_id':'report-deepseek-01','input':{'report_id':rid}})
    assert r.status_code==202,r.text
    execute('agent','tenant-a',r.json()['id'])
    result=client.get('/api/v1/runs/'+r.json()['id']).json()
    assert result['status']=='succeeded',result
    body=json.dumps(calls,ensure_ascii=False)
    assert all(x not in body for x in ('13812345678','private-child','private-id','record_ids','entries'))
    with Session(engine()) as s:
        assert s.get(ReportSnapshot,rid).payload==payload
    login(client,'b')
    assert client.post('/api/v1/runs',json={'kind':'report_summary','request_id':'cross-report-id-01','input':{'report_id':rid}}).status_code==404


def test_platform_deepseek_metering_and_quota_release(client, monkeypatch):
    enable(client, funding='platform')
    from app.config import settings
    monkeypatch.setenv('OPS_DEEPSEEK_API_KEY','sk-test-deepseek-not-real')
    monkeypatch.setenv('OPS_TEXT_PROVIDER','deepseek')
    settings.cache_clear()
    assert client.get('/api/v1/health').json()['model_configured'] is True
    with Session(engine()) as s:
        t=s.get(Tenant,'tenant-a');t.settings={**t.settings,'quotas':{'text_tokens':50000,'cost_fen':100}}
        p=s.get(PlatformSettings,1);p.plans={**p.plans,'prices':{**p.plans['prices'],'deepseek_flash_input_million_fen':200,'deepseek_flash_output_million_fen':800,'deepseek_flash_cached_million_fen':4}}
        s.add(t);s.add(p);s.commit()
    mock_api(monkeypatch)
    row=probe(client)
    execute('agent','tenant-a',row['id'])
    usage=client.get('/api/v1/usage').json()
    byresource={x['resource']:x for x in usage['buckets']}
    assert byresource['cost_fen']['used']==1 and byresource['cost_fen']['reserved']==0
    assert byresource['text_tokens']['used']==1100 and byresource['text_tokens']['reserved']==0


def test_visual_and_embedding_reservations_stay_on_aliyun(client):
    enable(client)
    from app.worker import reserve_job
    from fastapi import HTTPException
    with Session(engine()) as s:
        set_scope(s,'tenant-a')
        for purpose in ('vision','embedding','review'):
            with pytest.raises(HTTPException) as error:
                reserve_job(s,'tenant-a','separate-'+purpose,'text_tokens',20000,'byok',purpose=purpose)
            assert error.value.detail['code']=='KEY_REQUIRED'
            assert '百炼' in error.value.detail['message']
            s.rollback()


def test_legacy_empty_routing_keeps_aliyun_after_provider_switch(client, monkeypatch):
    from app.domain import reserve
    from app.model_router import reservation
    with Session(engine()) as s:
        set_scope(s,'tenant-a')
        reserve(s,'tenant-a','legacy-before-deepseek','text_tokens',20000,'byok')
        s.commit()
    enable(client)
    with Session(engine()) as s:
        set_scope(s,'tenant-a')
        old=reservation(s,'tenant-a','legacy-before-deepseek','byok')
        new=reservation(s,'tenant-a','future-deepseek-request','byok')
        assert old['provider']=='aliyun'
        assert new['provider']=='deepseek'

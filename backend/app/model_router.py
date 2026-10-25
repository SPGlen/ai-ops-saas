"""Institution-selected text models; immutable routing and conservative budget estimates."""
import math
from copy import deepcopy
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from sqlmodel import select
from .config import settings
from .models import Tenant, UsageRecord, Integration, PlatformSettings
from .domain import query
from .security import fail, decrypt

DEEPSEEK_MODELS = ('deepseek-flash', 'deepseek-v4-pro')

class TextModelSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider: Literal['aliyun', 'deepseek'] = 'aliyun'
    model: str = Field(default='deepseek-flash', max_length=100)
    funding: Literal['platform', 'byok'] = 'platform'
    thinking: bool = False
    max_tokens: int = Field(default=3000, ge=256, le=8000)
    input_million_fen: int = Field(default=200, ge=0, le=1000000)
    output_million_fen: int = Field(default=800, ge=0, le=1000000)
    cached_million_fen: int = Field(default=4, ge=0, le=1000000)


def configuration(session, tenant_id):
    t = session.get(Tenant, tenant_id)
    if not t:
        fail('NOT_FOUND', '机构不存在', 404)
    defaults = {'provider': settings().text_provider, 'model': settings().deepseek_model,
                'funding': t.settings.get('funding', 'platform')}
    return TextModelSettings.model_validate({**defaults, **t.settings.get('ai_text', {})})


def purpose_for(kind):
    return {'predict': 'vision', 'rubric_review': 'review', 'knowledge_index': 'embedding',
            'chat': 'legacy'}.get(kind, 'text')


def default_funding(session, tenant_id, kind):
    if purpose_for(kind) == 'text':
        return configuration(session, tenant_id).funding
    return session.get(Tenant, tenant_id).settings.get('funding', 'platform')


def aliyun_snapshot(purpose):
    model = {'vision': settings().score_model, 'review': settings().review_model,
             'embedding': settings().embedding_model}.get(purpose, settings().text_model)
    return {'provider': 'aliyun', 'model': model, 'purpose': purpose,
            'score_model': settings().score_model, 'review_model': settings().review_model}


def snapshot(session, tenant_id, funding, purpose='text'):
    cfg = configuration(session, tenant_id)
    if purpose != 'text' or cfg.provider == 'aliyun':
        return aliyun_snapshot(purpose)
    if cfg.model not in DEEPSEEK_MODELS:
        fail('MODEL_UNSUPPORTED', '请选择已接通的 DeepSeek 模型')
    rates = {k: getattr(cfg, k + '_million_fen') for k in ('input', 'output', 'cached')}
    if funding == 'platform':
        platform = session.get(PlatformSettings, 1)
        prices = platform.plans.get('prices', {}) if platform else {}
        prefix = 'deepseek_pro' if cfg.model == 'deepseek-v4-pro' else 'deepseek_flash'
        rates = {k: int(prices.get(prefix + '_' + k + '_million_fen', 0)) for k in rates}
    if rates['input'] <= 0 or rates['output'] <= 0 or rates['cached'] > rates['input']:
        fail('PRICE_UNCONFIGURED', '请配置 DeepSeek 的输入、输出及缓存估算单价', 503)
    return {'provider': 'deepseek', 'model': cfg.model, 'purpose': purpose,
            'thinking': cfg.thinking, 'max_tokens': cfg.max_tokens, 'rates': rates,
            'cost_basis': 'configured_estimate_not_provider_invoice'}


def credentials(session, tenant_id, funding, route):
    if route['provider'] == 'aliyun':
        from .integrations import aliyun
        return aliyun.config(session, tenant_id, funding)[0]
    if funding == 'byok':
        row = session.exec(query(session, Integration, tenant_id).where(
            Integration.provider == 'deepseek', Integration.active == True)).first()
        if not row or not row.secret_cipher:
            fail('KEY_REQUIRED', '请先配置当前机构的 DeepSeek Key', 503)
        key = decrypt(tenant_id, row.secret_cipher)
    else:
        key = settings().deepseek_api_key
    if not key or not isinstance(key, str):
        fail('MODEL_UNCONFIGURED', '尚未配置所选费用来源的 DeepSeek Key', 503)
    return key


def reservation(session, tenant_id, request_id, funding, purpose='text'):
    previous = session.exec(query(session, UsageRecord, tenant_id).where(
        UsageRecord.request_id == request_id, UsageRecord.resource == 'text_tokens')).first()
    if previous:
        # Reservations from before this integration were all Bailian. Never
        # silently move old paid/pending work to the newly selected provider.
        return deepcopy(previous.model_usage.get('route')) or aliyun_snapshot(purpose)
    return snapshot(session, tenant_id, funding, purpose)


def actual_cost(usage, actual=None):
    meta = usage.model_usage or {}
    calls = meta.get('calls', [])
    if meta.get('route', {}).get('provider') == 'deepseek' and calls and all(c.get('metered') for c in calls):
        r = meta['route']['rates']
        weighted = sum((c['input_tokens'] - c['cached_tokens']) * r['input'] +
                       c['cached_tokens'] * r['cached'] + c['output_tokens'] * r['output'] for c in calls)
        return math.ceil(weighted / 1000000)
    return math.ceil((usage.actual if actual is None else actual) * usage.unit_rate_fen / usage.unit_scale)

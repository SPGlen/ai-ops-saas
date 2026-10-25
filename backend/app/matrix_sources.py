"""Bounded, allowlisted public feeds and explicitly verified Xiaohongshu search."""
import ipaddress, socket
from urllib.parse import urlparse
import httpx
from defusedxml.ElementTree import fromstring
from .config import settings
from .security import fail
from .models import now
from .integrations import publishing
from .domain import own
from .models import SocialAccount


def feed_url(url):
    p = urlparse(url)
    allowed = {h.strip().lower() for h in settings().matrix_source_hosts.split(',') if h.strip()}
    if p.scheme != 'https' or p.port not in (None, 443) or p.username or p.password or not p.hostname or p.hostname.lower() not in allowed:
        fail('SOURCE_NOT_ALLOWED', 'RSS来源须使用平台配置的HTTPS域名白名单')
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        fail('SOURCE_NOT_ALLOWED', 'RSS来源不能指向本地或私有网络')
    return url


def parse_feed(raw, source):
    root = fromstring(raw)
    items = []
    for item in list(root.findall('.//item')) + list(root.findall('{http://www.w3.org/2005/Atom}entry')):
        def text(name):
            v = item.find(name)
            if v is None:
                v = item.find('{http://www.w3.org/2005/Atom}'+name)
            return (v.text or '').strip() if v is not None else ''
        link = text('link')
        if not link:
            el = item.find('{http://www.w3.org/2005/Atom}link')
            link = el.get('href', '') if el is not None else ''
        if urlparse(link).scheme not in ('https', 'http'):
            continue
        title = text('title')[:250]
        if title:
            items.append({'title': title, 'url': link[:1500], 'source_url': source, 'published_at': text('pubDate') or text('published') or text('updated') or None, 'retrieved_at': now().isoformat(), 'kind': 'feed'})
    return items[:30]


def collect(s, run):
    items, notes = [], []
    for url in run.snapshot['spec']['source_urls']:
        try:
            feed_url(url)
            with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
                with client.stream('GET', url, headers={'Accept': 'application/rss+xml, application/atom+xml, application/xml'}) as r:
                    r.raise_for_status()
                    raw = bytearray()
                    for part in r.iter_bytes():
                        raw.extend(part)
                        if len(raw) > 2*1024*1024:
                            fail('SOURCE_TOO_LARGE', 'RSS文档超过2MB')
            items += parse_feed(bytes(raw), url)
        except Exception:
            notes.append({'url': url, 'status': 'unavailable', 'reason': '来源未在白名单、无法访问或格式不符合要求'})
    if run.snapshot['spec'].get('xhs_search'):
        candidates = [a for a in run.snapshot['accounts'] if a['platform'] == 'xiaohongshu']
        for selected in candidates:
            account = own(s, SocialAccount, run.tenant_id, selected['id'])
            if account.config.get('verified_capabilities', {}).get('search') and account.identity_key:
                try:
                    result = publishing.call(run.tenant_id, account.id, 'search', {'platform': 'xiaohongshu', 'keyword': run.snapshot['spec']['direction'][:80]}, 60)
                    for item in result.get('items', [])[:20]:
                        if item.get('title') and item.get('url'):
                            items.append({'title': str(item['title'])[:250], 'url': item['url'], 'published_at': item.get('published_at'), 'retrieved_at': now().isoformat(), 'kind': 'xiaohongshu'})
                except Exception:
                    notes.append({'status': 'unavailable', 'reason': '小红书搜索连接器尚未验证或暂不可用'})
                break
        else:
            notes.append({'status': 'unavailable', 'reason': '小红书搜索能力尚未验证'})
    if not items:
        items = [{'title': run.snapshot['spec']['direction'], 'kind': 'evergreen', 'url': None, 'published_at': None, 'retrieved_at': now().isoformat()}]
    seen = set()
    unique = []
    for item in items:
        key = item.get('url') or item['title']
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return {'items': unique[:60], 'notes': notes, 'realtime': any(x['kind'] != 'evergreen' for x in unique)}

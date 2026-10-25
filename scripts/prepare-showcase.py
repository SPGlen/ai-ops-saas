"""Prepare an isolated, restartable demo. Never copies the development database or credentials."""
import argparse,contextlib,io,json,os,secrets,sys,sqlite3
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlparse
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'backend'))
parser=argparse.ArgumentParser()
parser.add_argument('--fresh',action='store_true')
parser.add_argument('--channel',choices=['local','shared'],default='local')
parser.add_argument('--hours',type=int,default=8)
parser.add_argument('--public-url',default='http://127.0.0.1:8188')
args=parser.parse_args()
u=urlparse(args.public_url)
if u.scheme not in ('http','https') or not u.hostname or u.username or u.password or u.path not in ('','/') or u.query or u.fragment:
    raise SystemExit('Use an http(s) origin without a path or credentials')
if u.hostname not in ('localhost','127.0.0.1','::1') and u.scheme!='https':
    raise SystemExit('External demo access requires HTTPS')
folder=root/'.local'/('showcase' if args.channel=='local' else 'showcase-shared');folder.mkdir(parents=True,exist_ok=True)
manifest=folder/'current.json'
old=json.loads(manifest.read_text(encoding='utf-8')) if manifest.exists() else None
today=datetime.now().date().isoformat()
fresh=args.fresh or not old or old.get('prepared_date')!=today or not Path(old.get('database_path','')).is_file()
if fresh:
    run=folder/'runs'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(4));run.mkdir(parents=True)
    config={'run_dir':str(run),'database_path':str(run/'ops.db'),'data_dir':str(run/'data'),'secret_key':secrets.token_hex(32),'prepared_date':today,'access_code':''}
else: config=old
config['public_url']=args.public_url.rstrip('/')
if u.hostname not in ('localhost','127.0.0.1','::1'):
    config['access_code']=config.get('access_code') or secrets.token_urlsafe(24)
else:
    config['access_code']=''
config['expires_at']=(datetime.now(timezone.utc)+timedelta(hours=max(1,min(args.hours,72)))).isoformat() if args.channel=='shared' else ''
config['port']=u.port or (443 if u.scheme=='https' else 80)
env={
    'OPS_DEMO_MODE':'true','OPS_ENVIRONMENT':'development','OPS_TASK_MODE':'demo',
    'OPS_DATABASE_URL':'sqlite:///'+config['database_path'].replace('\\','/'),
    'OPS_DATA_DIR':config['data_dir'],'OPS_SECRET_KEY':config['secret_key'],
    'OPS_PUBLIC_URL':config['public_url'],'OPS_DEMO_ACCESS_CODE':config['access_code'],
    'OPS_SMTP_HOST':'','OPS_SMTP_USER':'','OPS_SMTP_PASSWORD':'','OPS_S3_BUCKET':'','OPS_S3_ACCESS_KEY':'','OPS_S3_SECRET_KEY':'',
    'OPS_ALIYUN_API_KEY':'','OPS_PUBLISHER_URL':'','OPS_PUBLISHER_TOKEN':'',
    'OPS_ALLOW_LIVE_PUBLISH':'false','OPS_ALLOW_LIVE_REPLIES':'false','OPS_OCR_ENABLED':'false',
}
os.environ.update(env)
# Backup the isolated demo before applying presentation example upgrades.
if not fresh and not (Path(config['run_dir']) / 'before-examples-v2.db').exists():
    with sqlite3.connect(config['database_path']) as source, sqlite3.connect(str(Path(config['run_dir']) / 'before-examples-v2.db')) as backup:
        source.backup(backup)
from app.demo_showcase import seed
with contextlib.redirect_stdout(io.StringIO()) as report: seed()
result=json.loads(report.getvalue().strip().splitlines()[-1])
if fresh: config['fixture_report']=result
config['examples_revision']=2
manifest.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'ready':True,'fresh':fresh,'manifest':str(manifest),'url':config['public_url'],'synthetic_data':True,'real_calls_enabled':False},ensure_ascii=False))

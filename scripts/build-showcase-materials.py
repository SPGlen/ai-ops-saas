# Offline demonstration materials, deliberately excluding runtime credentials and databases.
from pathlib import Path
from datetime import datetime,timezone
import base64,hashlib,html,json,shutil,sqlite3,zipfile,subprocess,re,xml.etree.ElementTree as ET
root=Path(__file__).resolve().parents[1]
out=root/'.local/delivery/showcase';out.mkdir(parents=True,exist_ok=True)
def read_json(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def test_totals(path):
    data=ET.parse(path).getroot();suites=list(data) if data.tag=='testsuites' else [data]
    return {key:sum(int(s.get(key,0)) for s in suites) for key in ['tests','failures','errors','skipped']}
def snapshot_db(path,table):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT * FROM '+table+' ORDER BY id').fetchall()
        return {'rows':len(rows),'sha256':hashlib.sha256(json.dumps(rows,ensure_ascii=True,default=str,separators=(',',':')).encode()).hexdigest()}
backend=test_totals(root/'docs/showcase-regression-tests.xml');assert not backend['failures'] and not backend['errors']
feature=test_totals(root/'docs/showcase-api-tests.xml');assert not feature['failures'] and not feature['errors']
browser=read_json(root/'docs/showcase-browser-tests.json')['stats'];assert browser['expected']==3 and browser['unexpected']==0
regular=read_json(root/'docs/e2e-report.json')['stats'];assert regular['expected']==24 and regular['unexpected']==0
external=read_json(root/'docs/showcase-external-test.json');assert external['https'] and external['normal_role_login'] and external['media_playback']
recording=read_json(out/'recording.json');assert recording['completed'] and not recording['errors']
probe=shutil.which('ffprobe')
if probe and probe.lower().endswith('.cmd'):
    match=re.search(r'"([^"\r\n]+\.exe)"',Path(probe).read_text(encoding='utf-8-sig'));probe=match.group(1) if match else None
if not probe:raise SystemExit('ffprobe is required to verify the recording')
video_probe=json.loads(subprocess.run([probe,'-v','error','-show_entries','format=duration','-of','json',str(out/'企业演示录像.mp4')],capture_output=True,text=True,check=True).stdout)
duration=float(video_probe['format']['duration'])
offline=read_json(root/'docs/showcase-offline-test.json');assert offline['video_playback'] and not offline['errors']
config=read_json(root/'.local/showcase/current.json')
with sqlite3.connect(config['database_path']) as db:
    object_key=db.execute("SELECT object_key FROM assets WHERE mime='video/mp4' LIMIT 1").fetchone()[0]
shutil.copy2(Path(config['data_dir'])/'objects'/object_key,out/'程序合成案例.mp4')
shutil.copy2(root/'docs/ENTERPRISE_DEMO.md',out/'演示使用说明.md')
images=[('经营总览','showcase-overview.png','查看经营结果与完整业务入口。'),('财务图表','showcase-finance.png','从实收、退款和费用，进入关联明细。'),('票据原件','showcase-receipt.png','示例票据明确标记为虚构；可核对原件与操作记录。'),('班级学员','showcase-students.png','从班级查看学员、家长、课时与出勤。'),('矩阵账号','showcase-matrix.png','品牌、账号分组和预算；账号未连接，计划默认关闭。'),('授课视角','showcase-teacher.png','仅显示授课岗位获得授权的范围。'),('手机查看','showcase-mobile.png','移动端可查看和体验。')]
panels=[];buttons=[]
for index,(title,name,copy) in enumerate(images):
    file=root/'docs/screenshots'/name;assert file.is_file(),name
    encoded=base64.b64encode(file.read_bytes()).decode();active='active' if index==0 else ''
    buttons.append(f'<button data-index="{index}" class="{active}">{html.escape(title)}</button>')
    panels.append(f'<section class="scene {active}"><h2>{html.escape(title)}</h2><p>{html.escape(copy)}</p><img alt="{html.escape(title)}" src="data:image/png;base64,{encoded}"/></section>')
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>知营 · 企业演示资料</title><style>
*{box-sizing:border-box}body{margin:0;font-family:Microsoft YaHei,system-ui;background:#f4f6ef;color:#234532}header{padding:35px max(24px,calc((100vw - 1200px)/2));background:#173e32;color:#f6f9ee}header small{letter-spacing:3px;color:#b8cca8}h1{font-size:30px;margin:14px 0}header p{max-width:850px;line-height:1.9;color:#c4d3bf;font-size:14px}.wrap{max-width:1200px;margin:auto;padding:26px 22px}.note{background:#edf2e2;border:1px solid #d8e3c7;padding:18px 22px;border-radius:12px;font-size:13px;line-height:1.9}nav{display:flex;gap:8px;flex-wrap:wrap;position:sticky;top:0;padding:17px 0;background:#f4f6eff5;z-index:2}button,a{font:inherit}button{border:1px solid #dce4d2;border-radius:8px;padding:10px 17px;background:white;color:#3a5a3a;cursor:pointer}button.active{background:#214f3a;color:white;border-color:#214f3a}.scene{display:none;background:white;padding:24px;border:1px solid #e1e8d9;border-radius:14px}.scene.active{display:block}.scene h2{margin:0 0 10px;font-size:21px}.scene p{color:#7d8e73;font-size:13px;margin:0 0 22px}.scene img{width:100%;height:auto;display:block;border:1px solid #e3e8dc;border-radius:8px}video{width:100%;max-height:700px;background:#183f31;border-radius:12px;margin:16px 0}summary{font-weight:600;cursor:pointer}details{background:white;border:1px solid #e1e8d9;padding:22px;margin:22px 0;border-radius:14px}.files{display:flex;gap:20px;flex-wrap:wrap;margin:20px 0}.files a{color:#316441;font-size:13px}footer{padding:24px 0;color:#85927a;font-size:12px;line-height:1.9}@media(max-width:650px){h1{font-size:24px}.scene{padding:13px}nav{gap:6px}button{padding:9px 12px;font-size:12px}}
</style><header><small>ZHIYING · EDUCATION OPS</small><h1>从机构日常，到看得清的经营结果。</h1><p>招生、学员、教务、财务、经营报表与自媒体矩阵，在一个工作台协作。一人可以兼任多个岗位，由负责人控制功能授权。</p></header><main class="wrap"><div class="note"><strong>离线演示资料</strong> · 以下为真实产品界面截图与操作录像，数据均为虚构案例。此页面可断网打开，用于展示结果；操作业务请进入本机演示系统。真实 AI 调用与外部发布未启用。</div><details open><summary>57秒操作录像 · 从负责人总览到岗位切换</summary><video controls preload="metadata" src="企业演示录像.mp4"></video><p style="font-size:12px;color:#849376">无声录像，包含讲解字幕。可全屏播放，配合现场说明。</p></details><nav>BUTTONS</nav>PANELS<div class="files"><a href="演示招生表.xlsx">下载虚构招生示例表</a><a href="程序合成案例.mp4">打开15秒程序视频案例</a><a href="演示使用说明.md">演示使用说明与讲解路线</a></div><footer>此资料包不含真实学生信息、模型凭证、浏览器登录状态或外部演示访问码。图片与视频案例不表示模型和平台真实发布已通过验收。</footer></main><script>const buttons=[...document.querySelectorAll('nav button')],scenes=[...document.querySelectorAll('.scene')];buttons.forEach((b,i)=>b.onclick=()=>{buttons.forEach(x=>x.classList.remove('active'));scenes.forEach(x=>x.classList.remove('active'));b.classList.add('active');scenes[i].classList.add('active')});</script></html>'''
page=page.replace('57秒',str(round(duration))+'秒')
page=page.replace('BUTTONS',''.join(buttons)).replace('PANELS',''.join(panels));(out/'打开演示导览.html').write_text(page,encoding='utf-8')
backup=sorted((root/'.local/backups').glob('showcase-*'))[0]
preserved={}
for table in ['ledger_entries','credit_entries','audit_events','report_snapshots','content_versions']:
    before=snapshot_db(backup/'ops.db',table);after=snapshot_db(root/'.local/ops.db',table);assert before==after,table
    preserved[table]={'rows':after['rows'],'unchanged':True}
evidence={'version':'enterprise-demo-1','generated_at':datetime.now(timezone.utc).isoformat(),'formal_production_accepted':False,'backend_regression':backend,'demo_api':feature,'browser_regression':{'passed':regular['expected'],'failed':regular['unexpected']},'demo_browser':{'passed':browser['expected'],'failed':browser['unexpected']},'external_https_browser':external,'recording':{'scenes':len(recording['steps']),'duration_seconds':duration,'audio':False,'completed':True},'original_data_preserved':preserved,'synthetic_data':True,'offline_materials':offline,'real_ai_calls':False,'real_publish':False,'ocr_scans':False,'excel_import':True,'artifact_credentials_included':False}
(root/'docs/showcase-acceptance.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
files=['打开演示导览.html','企业演示录像.mp4','程序合成案例.mp4','演示招生表.xlsx','演示使用说明.md'];archive=root/'.local/delivery/知营-企业演示资料.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=8) as z:
    for name in files:z.write(out/name,'知营企业演示/'+name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert not any('current.json' in n or '访问说明.txt' in n or '.db' in n or '.env' in n for n in z.namelist())
archive.with_suffix('.zip.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n',encoding='utf-8')
print(json.dumps({'offline_html':str(out/'打开演示导览.html'),'demo_video':str(out/'企业演示录像.mp4'),'archive':str(archive),'bytes':archive.stat().st_size,'original_data_preserved':True,'backend_tests':backend['tests'],'demo_browser_passed':browser['expected']},ensure_ascii=True))

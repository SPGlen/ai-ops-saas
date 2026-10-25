"""Create fictional, internally consistent enterprise examples in a dedicated demo database."""
import io, json, os, shutil, subprocess
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from unittest.mock import patch
from sqlalchemy import event as sqlalchemy_event
from sqlmodel import Session, select
from .config import settings
from .db import engine, initialize, set_scope
from .models import *
from .domain import create_record, record_money, attend, save_content, query, credit_balance
from .operations import capture_rosters, set_kpi, refund, dt
from .permissions import identity_for
from .security import password_hash
from .reports import TZ, snapshot, evaluate_alerts, build
from .integrations.storage import save_asset
from .integrations.rendering import font, lines
from .schemas import ContentInput
from .matrix_schemas import PlanSpec
from .routes_operations import RefundInput
from .matrix import snapshot as plan_snapshot
from .demo_examples import enrich

_seed_time = ContextVar("showcase_timestamp", default=None)

@contextmanager
def historical(at):
    token = _seed_time.set(at)
    try:
        with patch("app.domain.now", return_value=at), patch("app.operations.now", return_value=at):
            yield
    finally:
        _seed_time.reset(token)

def timestamp(mapper, connection, target):
    at = _seed_time.get()
    if at is not None:
        target.created_at = at
        if hasattr(target, "updated_at"):
            target.updated_at = at

STAMPED = [Record, LedgerEntry, CreditEntry, AuditEvent, BusinessEvent]

def graphic(title, subtitle, rows, *, receipt=False):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (1080, 1440), "#f6f7ef")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((55,55,1025,1385),radius=36,fill="#ffffff",outline="#dfe7dc",width=3)
    d.rounded_rectangle((95,102,985,218),radius=25,fill="#194d3c")
    d.text((130,138), "知营 · " + ("票据明细示例" if receipt else "AI 创想课堂"),font=font(37),fill="#e7f2d8")
    y=285
    for line in lines(title.replace("，", "，\n", 1),830,d,font(65)):
        d.text((125,y),line,font=font(65),fill="#194d3c"); y+=92
    y+=25
    for line in lines(subtitle,830,d,font(30)):
        d.text((125,y),line,font=font(30),fill="#60725d"); y+=46
    y+=50
    for index,row in enumerate(rows):
        d.rounded_rectangle((118,y,962,y+128),radius=20,fill="#f1f5e9")
        d.text((144,y+18),f"0{index+1}",font=font(24),fill="#739454")
        for ln,text in enumerate(lines(row,690,d,font(31))[:2]):
            d.text((213,y+22+ln*42),text,font=font(31),fill="#314b37")
        y+=155
    d.line((125,1240,955,1240),fill="#dfe7dc",width=2)
    d.text((125,1270),"虚构演示资料 · 未发生真实交易" if receipt else "预置内容案例 · 未调用模型或实际发布",font=font(26),fill="#76876f")
    out=io.BytesIO();im.save(out,format="PNG");return out.getvalue()

def preview_video(folder, frames):
    """A real, playable slide render, explicitly a silent presentation sample."""
    executable = os.environ.get("OPS_DEMO_FFMPEG", "") or shutil.which("ffmpeg")
    if executable and executable.lower().endswith(".cmd"):
        import re
        text=Path(executable).read_text(encoding="utf-8-sig")
        match=re.search(r'"([^"\r\n]+\.exe)"', text)
        executable=match.group(1) if match else ""
    if not executable:
        return None
    folder.mkdir(parents=True,exist_ok=True)
    for index,raw in enumerate(frames):
        (folder/f"frame{index}.png").write_bytes(raw)
    filters=[]
    args=[executable,"-hide_banner","-loglevel","error","-y"]
    for index in range(len(frames)):
        args += ["-loop","1","-t","5","-i",str(folder/f"frame{index}.png")]
        filters.append(f"[{index}:v]scale=720:960,setsar=1,fps=24[v{index}]")
    filters.append(''.join(f"[v{i}]" for i in range(len(frames)))+f"concat=n={len(frames)}:v=1:a=0[out]")
    output=folder/'showcase-program-video.mp4'
    subprocess.run(args+["-filter_complex",";".join(filters),"-map","[out]","-c:v","libx264","-preset","ultrafast","-crf","26","-pix_fmt","yuv420p","-movflags","+faststart",str(output)],check=True,capture_output=True,timeout=90)
    return output.read_bytes()

def make_people(s, tenant, code):
    specs={"owner":["owner"],"admissions1":["admissions"],"admissions2":["admissions"],"teacher1":["teacher"],"teacher2":["teacher"],"finance":["finance"],"content":["content_ops"],"academic":["academic_admin"],"combined":["teacher","finance"],"scheduler":["scheduler"],"revenue":["revenue_viewer"]}
    names={"owner":"陈校长","admissions1":"林老师 · 招生","admissions2":"周老师 · 招生","teacher1":"王老师 · 授课","teacher2":"李老师 · 授课","finance":"许老师 · 财务","content":"小青 · 内容运营","academic":"赵老师 · 教务","combined":"郑老师 · 授课兼财务","scheduler":"吴老师 · 排班","revenue":"合伙人 · 营收查看"}
    out={}
    hashed=password_hash("Demo-Staff-2026!")
    for key,roles in specs.items():
        u=User(email=f"{key}.{code}@zhiying.example",name=names[key],verified=True,password_hash=hashed)
        s.add(u);s.flush()
        s.add(Membership(tenant_id=tenant.id,user_id=u.id,role=roles[0],roles=roles));out[key]=u
    s.flush()
    return out

def seed_tenant(s, tenant, code, total, current):
    set_scope(s,tenant.id)
    people=make_people(s,tenant,code);actor=people["owner"].id
    local=current.astimezone(TZ)
    month=local.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    previous_month=(month-timedelta(days=1)).replace(day=1)
    def record(kind,data): return create_record(s,tenant.id,actor,kind,data)
    with historical(previous_month):
        channels=[record("channel",{"name":name,"confirmed":True,"commission_bps":0,"notes":"虚构来源，正式分润比例由负责人确认"}) for name in ["小红书内容获客","社区体验活动","家长转介绍"]]
        classes=[record("class",{"name":name,"teacher_id":people["teacher1" if j==0 else "teacher2" if j==1 else "combined"].id,"program_name":"AI创想实践","capacity":18}) for j,name in enumerate(["启蒙创想 · 周六上午班","AI探索 · 周日下午班","创作实践 · 周五提升班"])]
        knowledge=record("knowledge",{"name":"已审核课程与试听说明","body":"AI创想实践面向小学阶段，8次实践课，每次90分钟，公开示例价格1980元。以观察、提问、核对和创作为主，家长可预约体验，由老师确认时间。不承诺获奖、升学或成绩提升。本资料仅为企业演示。","approved":True})
    enrollments=[]; orders=[]; students=[]
    opening=total-6 if total>=20 else total-3
    for j in range(total):
        recent=j>=opening
        started=(month-timedelta(days=10+j%7)) if not recent else (local-timedelta(days=max(1,6-(j-opening)))).replace(hour=11,minute=0,second=0,microsecond=0)
        if recent: started=max(month,min(started,current-timedelta(minutes=1)))
        with historical(started-timedelta(days=1)):
            lead=record("lead",{"name":f"家长{j+1:02d}（演示）","student_name":f"学员{j+1:02d}","contact":f"DEMO-{code}-{j+1:04d}","grade":["二年级","三年级","四年级"][j%3],"source":channels[j%3].data["name"],"owner_id":people["admissions1" if j%2==0 else "admissions2"].id,"stage":"attended","class_id":classes[j%3].id,"need":"希望孩子能在实践中了解AI并完成自己的小作品"})
        with historical(started):
            student=record("student",{"name":f"{('青禾' if code=='qinghe' else '星光')}学员{j+1:02d}","grade":["二年级","三年级","四年级"][j%3],"guardians":[{"name":f"家长{j+1:02d}","relationship":"母亲" if j%2 else "父亲","contact":f"DEMO-{code}-{j+1:04d}"}],"notes":"虚构演示学员；请勿录入真实儿童资料"})
            order=record("order",{"name":f"秋季AI实践报名 · {student.data['name']}","program_name":"AI创想实践 · 秋季8次课","price_fen":198000,"purchased_units":8,"discount_fen":0,"student_id":student.id,"class_id":classes[j%3].id,"channel_id":channels[j%3].id,"lead_id":lead.id,"owner_id":lead.data["owner_id"]})
            record_money(s,tenant.id,actor,order.id,"payment",198000,f"showcase-payment-{code}-{j}","演示收款记录，未产生真实资金交易")
            en=record("enrollment",{"student_id":student.id,"order_id":order.id,"class_id":classes[j%3].id})
            enrollments.append(en);orders.append(order);students.append(student)
    # An unconverted cohort and its honest loss reasons.
    for j in range(30 if total>=20 else 12):
        at=(local-timedelta(days=j%18)).replace(hour=9,minute=15,second=0,microsecond=0)
        stage=["new","contacted","booked","attended","lost"][j%5]
        with historical(at):
            record("lead",{"name":f"试听家长{j+1:02d}（演示）","student_name":f"体验学员{j+1:02d}","grade":["一年级","二年级","五年级"][j%3],"contact":f"DEMO-TRIAL-{code}-{j+1:03d}","source":channels[j%3].data["name"],"owner_id":people["admissions1" if j%2==0 else "admissions2"].id,"stage":stage,"class_id":classes[j%3].id,"loss_reason":"时间与其他课程冲突" if stage=="lost" else "","trial_at":(local+timedelta(days=1)).isoformat() if stage=="booked" else "","followup_at":(local+timedelta(hours=j%6)).isoformat(),"need":"想了解试听时间、上课方式及孩子是否适合"})
    # Capture the historical class roster before withdrawals; use real attendance services.
    day_numbers=sorted(set([min(day,max(1,local.day-2)) for day in [3,8,15,20]]))
    for ci,cls in enumerate(classes):
        for li,day in enumerate(day_numbers):
            at=month.replace(day=day,hour=9+ci*2)
            if at+timedelta(hours=2)>current: continue
            with historical(at+timedelta(hours=2)):
                lesson=record("lesson",{"name":f"第{li+1}课 · "+["观察与提问","AI故事创作","事实核对实验","我的作品展示"][li%4],"class_id":cls.id,"starts_at":at.isoformat(),"status":"completed"})
                for j,en in enumerate(enrollments):
                    if en.data["class_id"]!=cls.id or dt(en.data["started_at"])>at: continue
                    if (j+li)%8:
                        attend(s,tenant.id,cls.data["teacher_id"],en.id,lesson.id,f"showcase-attend-{code}-{j}-{li}")
                    elif li==0:
                        record("leave",{"name":"演示请假 · 家庭安排","enrollment_id":en.id,"lesson_id":lesson.id,"reason":"家庭出行，已与教务预约补课","status":"approved"})
    capture_rosters(s,tenant.id)
    for index,kpi in enumerate(s.exec(query(s,FeedbackKPI,tenant.id)).all()):
        if index%4:
            with historical(as_utc(kpi.due_at)-timedelta(hours=18)):
                i=identity_for(s,tenant, kpi.teacher_id)
                set_kpi(i,kpi.id,True,kpi.version,"演示课返完成确认")
    # Three types of follow-up are visible in the monthly report.
    for j in range(min(8,len(students))):
        with historical(current-timedelta(days=j%5,hours=1)):
            record("family_feedback",{"name":f"课堂体验反馈{j+1:02d}","student_id":students[j].id,"class_id":classes[j%3].id,"respondent":"parent","category":"schedule" if j%3==0 else "teaching","rating":2 if j==0 else 4 if j%2 else 5,"body":"希望课程结束后能及时了解孩子的课堂表现。" if j==0 else "孩子愿意主动讲解作品，老师的实践环节安排很清楚。","status":"open" if j<2 else "resolved","resolution":"已由教务回访，确认后续上课安排。" if j>=2 else ""})
    owner=identity_for(s,tenant,actor)
    withdrawal_count=9 if total==30 else 2
    for j in range(withdrawal_count):
        with historical(max(month,current-timedelta(hours=12+j))):
            refund(owner,orders[j].id,RefundInput(request_id=f"showcase-refund-{code}-{j}",amount_fen=40000,reason=["家庭搬迁，无法继续到校","课程时间与学校安排冲突","学习安排调整，暂缓学习"][j%3],withdrawal=True,enrollment_ids=[enrollments[j].id]))
    for ci,cls in enumerate(classes):
        record("lesson",{"name":"现场体验 · 下次课与签到","class_id":cls.id,"starts_at":(current+timedelta(days=ci+1)).isoformat(),"status":"scheduled"})
    for j,(name,amount,category) in enumerate([("教室场地费",180000,"场地"),("课程实验耗材",68000,"教学耗材"),("社区试听活动物料",42000,"招生活动")]):
        raw=graphic(name,"示例记账附件，支持点击查看原件",[f"金额：人民币 {amount/100:,.2f} 元",f"分类：{category}","核对状态：人工确认 · 演示用途"],receipt=True)
        asset=save_asset(s,tenant.id,f"演示凭证-{name}.png",raw,"image/png",purpose="receipt");asset.uploaded_by=people["finance"].id
        at=current-timedelta(days=3+j*3)
        with historical(at):
            expense=record("expense",{"name":name,"amount_fen":amount,"date":at.astimezone(TZ).date().isoformat(),"category":category,"status":"confirmed","asset_id":asset.id,"notes":"虚构演示费用，未发生真实交易"})
            s.add(ReceiptLink(tenant_id=tenant.id,kind="expense",record_id=expense.id,asset_id=asset.id,actor_id=actor,note="原件对照示例"))
    raw=graphic("课程报名收款凭据","原始附件与订单、收款流水关联",["报名项目：AI创想实践 · 8次课","登记金额：人民币 1,980.00 元","说明：虚构凭据，非银行回单"],receipt=True)
    asset=save_asset(s,tenant.id,"演示报名收款凭据.png",raw,"image/png",purpose="receipt");asset.uploaded_by=actor
    ledger=s.exec(query(s,LedgerEntry,tenant.id).where(LedgerEntry.order_id==orders[-1].id,LedgerEntry.entry_type=="payment")).first()
    s.add(ReceiptLink(tenant_id=tenant.id,kind="ledger",record_id=ledger.id,asset_id=asset.id,actor_id=actor,note="演示原件"))
    # Persist a complete brand/account/plan configuration, without impersonating connected accounts.
    preview_assets=[]
    for brand_index,brand_name in enumerate(["青禾AI · 中心校区","青禾AI · 社区课堂"] if code=="qinghe" else ["星光 · 创想课堂"]):
        profile=MediaProfile(tenant_id=tenant.id,name=brand_name,audience="小学阶段家长",style="用孩子的观察、作品和提问说明课程价值；不承诺提分或获奖",knowledge_ids=[knowledge.id]);s.add(profile);s.flush()
        group=AccountGroup(tenant_id=tenant.id,profile_id=profile.id,name="中心校区矩阵" if brand_index==0 else "社区体验矩阵");s.add(group);s.flush()
        accounts=[]
        for plat,name,form in [("xiaohongshu","亲子创作","image_text"),("xiaohongshu","校区日常","image_text"),("douyin","实践小课堂","video"),("channels","家长公开课","video")][:4 if brand_index==0 else 2]:
            account=SocialAccount(tenant_id=tenant.id,profile_id=profile.id,platform=plat,name=brand_name+" · "+name,status="unconfigured",config={"matrix":{"positioning":name,"call_to_action":"预约一次AI实践体验","form":form,"monthly_budget_fen":10000},"demo":True});s.add(account);s.flush();accounts.append(account.id)
            s.add(AccountGroupMember(tenant_id=tenant.id,group_id=group.id,account_id=account.id))
        spec=PlanSpec(direction="面向家长介绍AI创想课堂，用真实课程事实规划亲子实践选题",account_ids=accounts,group_ids=[group.id],review="manual",run_budget_fen=3000,daily_budget_fen=6000).model_dump()
        plan=AutomationPlan(tenant_id=tenant.id,profile_id=profile.id,name=brand_name+" · 每周二五内容计划",actor_id=actor,spec=spec,enabled=False);s.add(plan);s.flush()
        s.add(AutomationPlanVersion(tenant_id=tenant.id,plan_id=plan.id,version=1,snapshot=plan_snapshot(s,plan)))
        frames=[]
        for k,(title,sub,items) in enumerate([
            ("孩子学AI，从一个好问题开始","把一次观察，变成一段有依据的表达",["先观察：描述颜色、形状与变化","再提问：请AI补充另一个角度","最后核对：比较回答与真实观察"]),
            ("周末一起做个AI小实验","让孩子成为提问和判断的主人",["用三句话描述窗外的一棵树","比较两种不同的提问方式","选出需要到现场核实的内容"]),
            ("把好奇心，变成自己的小作品","AI创想实践 · 面向小学阶段",["八次实践课，每次90分钟","从观察、提问到创作与分享","家长可预约体验，由老师确认时间"]),
        ]):
            raw=graphic(title,sub,items);frames.append(raw)
            a=save_asset(s,tenant.id,f"预置案例-{brand_index+1}-{k+1}.png",raw,"image/png",consent=True);a.uploaded_by=people["content"].id
            save_content(s,tenant.id,people["content"].id,ContentInput(title=title,body=sub+"。\n\n"+"\n".join(items)+"\n\n预置演示文案，未调用模型，未实际发布。",assets=[a.id]))
            if brand_index==0: preview_assets.append(a.id)
        profile.asset_ids=preview_assets[:1];s.add(profile)
        if code=="qinghe" and brand_index==0:
            raw=preview_video(settings().data_dir/'render',frames)
            if raw:
                a=save_asset(s,tenant.id,"程序合成案例-15秒无声演示.mp4",raw,"video/mp4",consent=True);a.uploaded_by=people["content"].id;preview_assets.append(a.id)
                save_content(s,tenant.id,people["content"].id,ContentInput(title="AI创想课堂 · 程序合成展示",form="video",body="15秒无声程序合成案例；使用预置文案与排版，未调用AIGC、配音或发布接口。",assets=[a.id]))
    tenant.settings={**tenant.settings,"showcase":{"seeded_at":current.isoformat(),"asset_ids":preview_assets,"version":"enterprise-demo-1"}}
    s.add(tenant);s.flush()
    enrich(s,tenant,current)
    for kind,period in [("weekly",local.date().isoformat()),("weekly",(local-timedelta(days=7)).date().isoformat()),("monthly",local.strftime("%Y-%m")),("monthly",previous_month.strftime("%Y-%m"))]: snapshot(owner,kind,period)
    evaluate_alerts(owner,local.strftime("%Y-%m"))
    # All notifications are deliberately retained as unsent; there is no scheduler in demo mode.
    for n in s.exec(query(s,NotificationOutbox,tenant.id)).all():
        n.status="disabled";n.error="独立演示环境：仅展示站内异常，未配置或发送企业微信通知";s.add(n)
    s.commit()
    return {"name":tenant.name,"students":total,"withdrawals":withdrawal_count,"monthly":build(owner,"monthly",local.strftime("%Y-%m"))["metrics"]}

def seed():
    cfg=settings();cfg.validate_runtime()
    if not cfg.demo_mode:
        raise SystemExit("Showcase fixtures require OPS_DEMO_MODE=true; the existing workspace database is never selected")
    initialize()
    with Session(engine(),expire_on_commit=False) as s:
        existing=s.exec(select(Tenant)).all()
        if existing:
            if not all(t.settings.get("showcase") for t in existing):
                raise SystemExit("Refusing to add showcase data to an existing non-showcase database")
            for tenant in existing:
                set_scope(s,tenant.id)
                enrich(s,tenant,now())
            s.commit()
            print(json.dumps({"ready":True,"existing":True,"tenants":len(existing),"examples_revision":2}));return
        for model in STAMPED: sqlalchemy_event.listen(model,"before_insert",timestamp)
        try:
            s.add(PlatformSettings(free_until=now()+timedelta(days=60),plans={"matrix":{"account_limit":9},"prices":{"text_million_fen":1000,"image_fen":20,"video_second_fen":60}}));s.flush()
            result=[];current=now()
            for slug,code,name,total in [("qinghe-demo","qinghe","青禾AI教育 · 企业演示",30),("xingguang-demo","xingguang","星光创想课堂 · 企业演示",12)]:
                tenant=Tenant(name=name,slug=slug,settings={"operations":{"baseline_confirmed":True},"consultation_enabled":False,"publishing_enabled":False,"auto_publish":False,"matrix_monthly_budget_fen":30000,"matrix_account_limit":9,"quotas":{},"funding":"platform"});s.add(tenant);s.flush()
                result.append(seed_tenant(s,tenant,code,total,current))
            print(json.dumps({"ready":True,"tenants":result,"synthetic_data":True,"live_publish":False},ensure_ascii=False,default=str))
        finally:
            for model in STAMPED: sqlalchemy_event.remove(model,"before_insert",timestamp)

if __name__=="__main__": seed()

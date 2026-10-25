"""Idempotent presentation examples; only ever applied to isolated showcase tenants."""
import re
from datetime import timedelta
from sqlmodel import select
from .config import settings
from .models import (Record, User, StudioDefinition, FormSubmission, FlowInstance, FlowTask)
from .domain import query, plain_data, create_record, update_record
from .permissions import identity_for
from . import studio

REVISION = 2
SURNAMES = "陈 林 王 李 张 刘 周 赵 吴 郑 孙 何 黄 徐 胡 高 罗 梁 宋 唐 许 韩 冯 邓 曹 袁 曾 彭 萧 蔡".split()

def demo_phone(code, number):
    # Fictional display values. Demo mode never sends SMS or makes phone calls.
    return f"1380000{number + (1000 if code == 'xingguang' else 0):04d}"

def enrich(s, tenant, current):
    marker = tenant.settings.get("showcase", {})
    if not settings().demo_mode or marker.get("version") != "enterprise-demo-1":
        raise RuntimeError("Example enrichment requires an isolated showcase tenant")
    if marker.get("examples_revision", 0) >= REVISION:
        return False
    code = "xingguang" if tenant.slug == "xingguang-demo" else "qinghe"
    owner_user = s.exec(select(User).where(User.email == f"owner.{code}@zhiying.example")).one()
    owner = identity_for(s, tenant, owner_user.id)
    actor = owner_user.id
    rows = s.exec(query(s, Record, tenant.id).order_by(Record.created_at, Record.id)).all()
    classes = [r for r in rows if r.kind == "class"]
    channels = [r for r in rows if r.kind == "channel"]

    def edit(row, changes):
        original = plain_data(tenant.id, row.data)
        changes = {k: v for k, v in changes.items() if original.get(k) != v}
        if changes:
            update_record(s, tenant.id, actor, row.id, changes, row.version)

    for index, row in enumerate(rows):
        data = plain_data(tenant.id, row.data)
        if row.kind in ("student", "lead"):
            old_contact = data.get("contact", "")
            changes = {}
            match = re.fullmatch(r"DEMO-(TRIAL-)?(?:qinghe|xingguang)-(\d+)", old_contact)
            phone = demo_phone(code, int(match[2]) + (2000 if match[1] else 0)) if match else old_contact
            if old_contact.startswith("DEMO") and not match:
                phone = demo_phone(code, 5000 + index)
            if phone != old_contact:
                changes["contact"] = phone
            number = int(match[2]) - 1 if match else index
            surname = SURNAMES[number % len(SURNAMES)]
            if row.kind == "student":
                guardians = data.get("guardians", []) or [{"name": data.get("guardian") or "家长", "relationship": "母亲", "contact": phone}]
                updated = []
                for guardian in guardians:
                    g = dict(guardian)
                    if g.get("contact", "").startswith("DEMO") or not g.get("contact"):
                        g["contact"] = phone
                    if re.fullmatch(r"家长\d+", g.get("name", "")):
                        g["name"] = surname + ("女士" if g.get("relationship") == "母亲" else "先生")
                    updated.append(g)
                changes["guardians"] = updated
                if not data.get("notes") or data.get("notes", "").startswith("虚构演示学员"):
                    changes["notes"] = ["喜欢绘画与故事表达；家长方便周三晚间沟通。", "对科学实验感兴趣；重点练习提问和核对资料。", "喜欢动手制作；由爸爸接送，课前一天提醒。", "乐于分享作品；优先安排周末课程。 "][number % 4] + "（虚构演示资料，手机号仅展示）"
            else:
                if not data.get("relationship") or data.get("relationship") == "家长":
                    changes["relationship"] = "母亲" if number % 2 else "父亲"
                if not data.get("city"):
                    changes["city"] = ["广州 · 天河", "广州 · 海珠", "广州 · 番禺"][number % 3]
                if not data.get("contact_time"):
                    changes["contact_time"] = ["工作日19:00—20:30", "周六10:00—12:00", "工作日12:00—13:30"][number % 3]
                if not data.get("notes"):
                    changes["notes"] = {
                        "new": "已登记家长需求，安排招生老师首次联系。",
                        "contacted": "已介绍课程安排，家长希望周末带孩子体验。",
                        "booked": "已与家长确认到校路线和试听时间，课前一天提醒。",
                        "attended": "孩子已参加体验，家长正在比较周末上课时间。",
                        "won": "已完成缴费及报名确认，后续由任课老师跟进。",
                        "lost": "已记录未成交原因，本轮结束跟进；后续联系需家长同意。",
                    }.get(data.get("stage"), "已建立联系，等待确认后续安排。") + "（演示）"
            edit(row, changes)
        elif row.kind == "class" and not data.get("notes"):
            edit(row, {"notes": "每周固定小班授课，每次90分钟；课前检查到课名单，课后24小时内确认课返KPI。"})
        elif row.kind == "expense":
            # Fill attribution, never change amounts, dates, money journals or credits.
            changes = {}
            if not data.get("class_id") and classes:
                changes["class_id"] = classes[index % len(classes)].id
            if not data.get("channel_id") and channels:
                changes["channel_id"] = channels[index % len(channels)].id
            edit(row, changes)
        elif row.kind == "leave" and not data.get("makeup_lesson_id"):
            enrollment = next((r for r in rows if r.id == data.get("enrollment_id")), None)
            lesson = next((r for r in rows if r.kind == "lesson" and r.data.get("class_id") == (enrollment.data.get("class_id") if enrollment else None) and r.data.get("status") == "scheduled"), None)
            if lesson:
                edit(row, {"makeup_lesson_id": lesson.id})

    existing_names = {(r.kind, r.data.get("name")) for r in rows}
    def add(kind, data):
        if (kind, data["name"]) not in existing_names:
            existing_names.add((kind, data["name"]))
            return create_record(s, tenant.id, actor, kind, data)

    for n, (title, audience, body) in enumerate([
        ("周末AI亲子体验预热", "一年级至三年级意向家庭", "本周末一起完成一次观察与提问小实验。体验60分钟，家长可与老师确认适合的班级。"),
        ("在读家长作品分享", "秋季班在读家长", "本周孩子们练习了描述观察结果、核对AI回答。请一起听孩子讲解自己的作品，欢迎记录一个新的问题。"),
        ("试听后回访安排", "已到场、尚未报名家庭", "感谢参加体验。请告诉我们孩子最感兴趣的环节，以及方便的上课时间，老师将逐一确认。"),
    ]):
        add("community", {"name": title, "audience": audience, "body": body + "（演示文案）", "status": "approved" if n == 0 else "draft", "due_at": (current + timedelta(days=n+1)).isoformat(), "channel": "manual", "outcome": "已完成分组与文案准备，待员工人工发送；未发生真实触达。"})
    for n, (title, body) in enumerate([
        ("孩子学AI，先学会提出一个好问题", "展示观察、提问、核对三步练习，用课堂示例说明，不使用儿童私人资料。"),
        ("周末亲子AI小实验：观察一棵树", "制作三张图文卡片，引导家长与孩子比较不同提问方式。"),
        ("90秒认识AI课堂中的事实核对", "用程序演示比较AI回答与可观察事实，结尾邀请体验。"),
        ("八次实践课，孩子会经历什么", "依据已审核课程说明，展示从观察到作品分享的学习路径。"),
        ("家长常问：几年级适合体验AI课", "说明小学阶段分龄体验安排，避免升学、获奖或提分承诺。"),
        ("一张作品卡，记录孩子的表达进步", "示意作品讲解结构，只使用机构自制、已授权素材。"),
    ]):
        add("topic", {"name": title, "body": body, "source": "机构常青选题 · 虚构演示", "form": "video" if n % 3 == 2 else "image_text", "status": "selected" if n < 2 else "candidate"})
    for title, body in [
        ("家长体验预约与入班说明", "试听面向小学阶段家庭，家长需提前预约。体验后由招生老师确认班级空位、上课时间与报名信息。示例学费1980元、8次课；实际以机构已确认方案为准。"),
        ("请假、补课与课堂沟通规则", "请假由教务登记确认，批准后原课不扣课时；补课需另行预约同班场次并签到。老师在课程结束后24小时内确认课返是否完成。"),
        ("退款登记与票据核对说明", "财务核对原订单、已上课时及剩余课时后登记退款，退款原因必填。退读与继续上课的部分退款分别记录，银行退款由财务线下确认。"),
    ]:
        add("knowledge", {"name": title, "body": body + "（演示制度说明）", "approved": True})

    definitions = s.exec(query(s, StudioDefinition, tenant.id)).all()
    flows = {}
    for template in studio.templates():
        if template["binding"] not in ("leave", "transfer", "refund", "expense", "independent"):
            continue
        name = "演示 · " + template["name"]
        d = next((d for d in definitions if d.name == name), None)
        if not d:
            d = StudioDefinition(tenant_id=tenant.id, created_by=actor, name=name, kind="workflow", binding=template["binding"], draft=template["spec"], enabled=False)
            s.add(d);s.flush();studio.publish(owner, d)
        flows[template["binding"]] = d
    form_name = "演示 · 周末体验活动申请表"
    form = next((d for d in definitions if d.name == form_name), None)
    if not form:
        form = StudioDefinition(tenant_id=tenant.id, created_by=actor, name=form_name, kind="form", binding="independent", draft={"workflow_id": flows["independent"].id, "fields": [
            {"key": "activity", "label": "活动名称", "type": "text", "required": True},
            {"key": "audience", "label": "目标家庭", "type": "text", "required": True},
            {"key": "families", "label": "计划家庭数", "type": "number", "required": True},
            {"key": "scheduled_date", "label": "活动日期", "type": "date", "required": True},
            {"key": "plan", "label": "执行安排", "type": "textarea", "required": True},
        ]})
        s.add(form);s.flush();studio.publish(owner, form)
    # Submit genuine local example instances through the same service as the UI.
    from .routes_operations import submit_form, SubmissionInput
    for n in range(2):
        request_id = f"showcase-activity-{n}"
        if s.exec(query(s, FormSubmission, tenant.id).where(FormSubmission.request_id == request_id)).first():
            continue
        result = submit_form(form.id, SubmissionInput(request_id=request_id, values={"activity": ["AI亲子观察小实验", "周末作品分享体验"][n], "audience": "一年级至三年级意向家庭", "families": 12 + n*3, "scheduled_date": (current + timedelta(days=n+2)).date().isoformat(), "plan": "招生老师确认名单，教务准备材料，任课老师安排60分钟体验；仅演示，不自动发送通知。"}), owner)
        if n == 0:
            instance = s.exec(query(s, FlowInstance, tenant.id).where(FlowInstance.request_id == "form:" + result["id"])).one()
            task = s.exec(query(s, FlowTask, tenant.id).where(FlowTask.instance_id == instance.id, FlowTask.assignee_id == actor, FlowTask.status == "pending")).one()
            studio.decide(owner, task.id, "approve", "演示审批通过，按计划准备；未发送外部消息。")
    tenant.settings = {**tenant.settings, "showcase": {**marker, "examples_revision": REVISION, "examples_updated_at": current.isoformat()}}
    s.add(tenant);s.flush()
    return True

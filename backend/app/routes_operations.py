"""Public /api/v1 contracts for institution operations, studio and reporting."""

import asyncio, json, hashlib, io
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, UploadFile, File, Form, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import Field, model_validator
from sqlmodel import Session, select
from .models import *
from . import schemas as S
from .auth import Identity, scoped, writable, platform, current
from .domain import own, query, plain_data, view_record, credit_balance
from .permissions import Scope, permit, has, identity_for, member_roles, check_asset
from .security import fail, encrypt
from .db import engine, set_scope
from . import operations as ops, reports, studio
from .config import settings

router = APIRouter(prefix="/api/v1", tags=["经营报表、表单与流程"])


class RefundInput(S.MoneyAction):
    reason: str = Field(default="", max_length=1000)
    withdrawal: bool = False
    enrollment_ids: list[str] = Field(default_factory=list, max_length=100)
    workflow_id: str = ""

    @model_validator(mode="after")
    def legacy_reason(self):
        if not self.reason:
            self.reason = self.note
        return self


class KPIInput(S.Strict):
    completed: bool
    version: int
    note: str = Field(default="", max_length=1000)


class TransferInput(S.Strict):
    class_id: str = ""
    effective_at: datetime | None = None
    reason: str = Field(min_length=1, max_length=1000)
    workflow_id: str = ""


class SettingsInput(S.Strict):
    feedback_hours: int = Field(default=24, ge=1, le=168)
    week_day: int = Field(default=0, ge=0, le=6)
    week_hour: int = Field(default=9, ge=0, le=23)
    month_day: int = Field(default=1, ge=1, le=28)
    month_hour: int = Field(default=9, ge=0, le=23)
    rules: list[dict] = Field(
        default_factory=lambda: ops.DEFAULT_OPS["rules"], max_length=30
    )


class WebhookInput(S.Strict):
    webhook: str = Field(default="", max_length=1000)
    active: bool = True


class Note(S.Strict):
    note: str = Field(default="", max_length=1000)
    verified_not_sent: bool = False


class BaselineInput(S.Strict):
    effective_at: datetime
    enrollment_ids: list[str] = Field(max_length=5000)


class ImportConfirm(S.Strict):
    version: int
    rows: list[dict] = Field(max_length=500)


class DefinitionInput(S.Strict):
    name: str = Field(min_length=1, max_length=100)
    kind: str
    binding: str = "independent"
    spec: dict = Field(default_factory=dict)
    version: int | None = None
    enabled: bool = False


class SubmissionInput(S.Strict):
    definition_version: int | None = None
    values: dict = Field(default_factory=dict)
    record_id: str = ""
    request_id: str = Field(min_length=8, max_length=100)


class FlowInput(S.Strict):
    payload: dict = Field(default_factory=dict)
    record_id: str = ""
    request_id: str = Field(min_length=8, max_length=100)


class DecisionInput(S.Strict):
    decision: str
    note: str = Field(default="", max_length=1000)
    values: dict = Field(default_factory=dict)


class LinkInput(S.Strict):
    kind: str
    record_id: str
    asset_id: str
    note: str = Field(default="", max_length=1000)


class AddonInput(S.Strict):
    note: str = Field(default="", max_length=1000)


class AddonReview(S.Strict):
    status: str
    note: str = Field(default="", max_length=1000)


def owner(i):
    if "owner" not in i.roles:
        fail("ROLE_FORBIDDEN", "需要机构负责人权限", 403)


@router.get("/operations/settings")
def op_settings(i: Identity = Depends(scoped)):
    cfg = ops.options(i.tenant)
    integration = i.session.exec(
        query(i.session, Integration, i.tenant.id).where(
            Integration.provider == "wecom_notice"
        )
    ).first()
    return {
        **cfg,
        "notice_configured": bool(
            integration and integration.active and integration.secret_cipher
        ),
        "notice_version": i.tenant.settings.get("notice_version", 0),
        "consultation_enabled": ops.enabled(i.tenant),
    }


@router.put("/operations/settings")
def put_settings(body: SettingsInput, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    ids = set()
    metrics = {
        "attrition_rate",
        "attendance_rate",
        "lead_conversion_rate",
        "trial_conversion_rate",
        "feedback_completion_rate",
    }
    for rule in body.rules:
        if (
            not isinstance(rule.get("id"), str)
            or rule["id"] in ids
            or rule.get("metric") not in metrics
            or rule.get("direction", "gte") not in ("gte", "lte")
            or not isinstance(rule.get("threshold"), (float, int))
            or not 0 <= rule["threshold"] <= 100
        ):
            fail("RULE_INVALID", "指标规则无效")
        ids.add(rule["id"])
        if rule.get("class_id"):
            Scope(i).own(rule["class_id"], "class")
    i.tenant.settings = {
        **i.tenant.settings,
        "operations": {
            **ops.options(i.tenant),
            **body.model_dump(),
            "next_tick_at": "",
        },
    }
    i.session.add(i.tenant)
    ops.event(i.session, i.tenant.id, i.user.id, "operations.settings", i.tenant.id)
    i.session.commit()
    return op_settings(i)


@router.post("/operations/baseline")
def baseline(body: BaselineInput, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    if as_utc(body.effective_at) > now():
        fail("DATE_INVALID", "期初日期不能是将来")
    scope = Scope(i)
    for eid in body.enrollment_ids:
        e = scope.own(eid, "enrollment")
        d = dict(e.data)
        if d.get("history_calibrated"):
            continue
        d.update(
            started_at=body.effective_at.isoformat(),
            history_calibrated=True,
            history=[
                {
                    "class_id": d.get("class_id", ""),
                    "start": body.effective_at.isoformat(),
                    "end": d.get("ended_at"),
                }
            ],
        )
        e.data = d
        i.session.add(e)
    remaining = [
        e for e in scope.list("enrollment") if not e.data.get("history_calibrated")
    ]
    if remaining:
        fail("BASELINE_INCOMPLETE", "仍有未核对的历史报名，请将期初在读名单完整确认")
    i.tenant.settings = {
        **i.tenant.settings,
        "operations": {**ops.options(i.tenant), "baseline_confirmed": True},
    }
    i.session.add(i.tenant)
    ops.event(i.session, i.tenant.id, i.user.id, "baseline.confirmed", i.tenant.id)
    i.session.commit()
    return {"status": "confirmed"}


@router.get("/operations/class-choices")
def class_choices(i: Identity = Depends(scoped)):
    if not any(has(i, x) for x in ("lead.read", "finance.read", "class.read")):
        fail("ROLE_FORBIDDEN", "没有班级选择权限", 403)
    scope = Scope(i)
    return [
        {"id": r.id, "data": {"name": r.data["name"]}}
        for r in scope.rows.values()
        if r.kind == "class"
        and (has(i, "lead.read") or has(i, "finance.read") or scope.visible(r))
    ]


@router.get("/classes/students")
def grouped_students(
    q: str = "",
    teacher_id: str = "",
    status: str = "active",
    i: Identity = Depends(scoped),
):
    permit(i, "student.read")
    if status not in ("active", "withdrawn", "all"):
        fail("STATE_INVALID", "状态错误")
    return ops.class_view(i, q, teacher_id, status)


@router.get("/students/{student_id}/profile")
def student_profile(student_id: str, i: Identity = Depends(scoped)):
    scope = Scope(i)
    r = scope.own(student_id, "student")
    profile = scope.project(r)
    ens = [
        e
        for e in scope.rows.values()
        if e.kind == "enrollment"
        and e.data["student_id"] == r.id
        and (
            scope.visible(e)
            or (
                has(i, "order.read")
                and e.data.get("order_id") in {x.id for x in scope.list("order")}
            )
        )
    ]
    profile["enrollments"] = [
        {
            **scope.project(e),
            "data": {
                **(
                    scope.project(e)["data"]
                    if scope.visible(e)
                    else {
                        k: v
                        for k, v in e.data.items()
                        if k
                        in (
                            "program_name",
                            "student_id",
                            "status",
                            "started_at",
                            "ended_at",
                        )
                    }
                ),
                "remaining": credit_balance(i.session, i.tenant.id, e.id),
            },
        }
        for e in ens
    ]
    allowed = {e.id for e in ens if scope.visible(e)}
    lessons = {
        r.id for r in scope.rows.values() if r.kind == "lesson" and scope.visible(r)
    }
    profile["attendance"] = (
        [
            c.model_dump()
            for c in i.session.exec(
                query(i.session, CreditEntry, i.tenant.id).where(
                    CreditEntry.kind == "attendance"
                )
            ).all()
            if c.enrollment_id in allowed and c.lesson_id in lessons
        ]
        if has(i, "attendance.read")
        else []
    )
    if has(i, "finance.read"):
        profile["orders"] = [
            scope.project(o)
            for o in scope.list("order")
            if o.data["student_id"] == r.id
        ]
    profile["family_feedback_allowed"] = has(i, "family_feedback.read") and (
        bool(i.roles & {"owner", "academic_admin"}) or r.id in scope.students
    )
    return profile


@router.get("/education/feedback-kpis")
def get_kpis(i: Identity = Depends(scoped)):
    rows = ops.kpi_rows(i)
    i.session.commit()
    lessons = {x.id: x for x in Scope(i).list("lesson")}
    return [
        {
            **x.model_dump(),
            "lesson_name": lessons[x.lesson_id].data["name"]
            if x.lesson_id in lessons
            else "历史课次",
            "overdue": x.completed_at is None and as_utc(x.due_at) < now(),
        }
        for x in rows
    ]


@router.patch("/education/feedback-kpis/{kpi_id}")
def update_kpi(kpi_id: str, body: KPIInput, i: Identity = Depends(scoped)):
    writable(i)
    r = ops.set_kpi(i, kpi_id, body.completed, body.version, body.note)
    i.session.commit()
    return r


@router.post("/enrollments/{enrollment_id}/transfer")
def transfer(enrollment_id: str, body: TransferInput, i: Identity = Depends(scoped)):
    writable(i)
    payload = body.model_dump(mode="json", exclude={"workflow_id"})
    studio.guard_action(i, "transfer", enrollment_id, payload, body.workflow_id)
    r = ops.transfer(i, enrollment_id, body.class_id, body.effective_at, body.reason)
    i.session.commit()
    return view_record(i.session, r)


@router.get("/orders/{order_id}/refund-context")
def get_refund_context(order_id: str, i: Identity = Depends(scoped)):
    permit(i, "finance.read")
    return ops.refund_context(i.session, i.tenant.id, order_id)


@router.get("/finance/overview")
def finance_overview(
    start: str = "",
    end: str = "",
    class_id: str = "",
    channel: str = "",
    i: Identity = Depends(scoped),
):
    local = now().astimezone(reports.TZ)
    try:
        if start:
            ops.dt(start)
        if end:
            ops.dt(end)
    except ValueError:
        fail("PERIOD_INVALID", "日期格式错误")
    a = (
        ops.dt(start)
        if start
        else local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    )
    b = ops.dt(end) if end else now() + timedelta(seconds=1)
    if a >= b:
        fail("PERIOD_INVALID", "结束时间必须晚于开始时间")
    return reports.clean(reports.financial(i, a, b, class_id, channel))


@router.get("/revenue/overview")
def revenue_overview(start: str = "", end: str = "", i: Identity = Depends(scoped)):
    permit(i, "revenue.read")
    local = now().astimezone(reports.TZ)
    try:
        a = (
            ops.dt(start)
            if start
            else local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        )
        b = ops.dt(end) if end else now() + timedelta(seconds=1)
    except ValueError:
        fail("PERIOD_INVALID", "日期格式错误")
    if a >= b:
        fail("PERIOD_INVALID", "结束时间必须晚于开始时间")
    return reports.clean(reports.financial(i, a, b, details=False))


@router.get("/finance/options")
def finance_options(i: Identity = Depends(scoped)):
    permit(i, "finance.read")
    rows = i.session.exec(query(i.session, Record, i.tenant.id)).all()
    return {
        "classes": [
            {"id": r.id, "name": r.data["name"]} for r in rows if r.kind == "class"
        ],
        "channels": [
            {"id": r.id, "name": r.data["name"]} for r in rows if r.kind == "channel"
        ],
    }


@router.get("/finance/details/{kind}/{record_id}")
def finance_detail(kind: str, record_id: str, i: Identity = Depends(scoped)):
    permit(i, "finance.read")
    s = i.session
    t = i.tenant.id
    if kind == "ledger":
        record = own(s, LedgerEntry, t, record_id).model_dump()
        order_id = record["order_id"]
    elif kind in ("order", "expense"):
        r = own(s, Record, t, record_id)
        if r.kind != kind:
            fail("NOT_FOUND", "财务记录不存在", 404)
        record = view_record(s, r)
        order_id = r.id if kind == "order" else ""
    else:
        fail("KIND_INVALID", "财务记录类型错误")
    links = s.exec(
        query(s, ReceiptLink, t).where(
            ReceiptLink.record_id == record_id, ReceiptLink.kind == kind
        )
    ).all()
    if kind in ("order", "expense") and record["data"].get("asset_id"):
        aid = record["data"]["asset_id"]
        if not any(l.asset_id == aid for l in links):
            links.append(
                ReceiptLink(
                    tenant_id=t,
                    kind=kind,
                    record_id=record_id,
                    asset_id=aid,
                    actor_id="legacy",
                )
            )
    assets = [own(s, Asset, t, l.asset_id) for l in links]
    context = (
        s.exec(
            query(s, BusinessEvent, t).where(
                BusinessEvent.kind == "finance.refund.context",
                BusinessEvent.record_id == record_id,
            )
        ).first()
        if kind == "ledger"
        else None
    )
    runs = s.exec(query(s, AgentRun, t).where(AgentRun.kind == "ocr")).all()
    return {
        "record": record,
        "refund_context": context.payload if context else None,
        "order": view_record(s, own(s, Record, t, order_id)) if order_id else None,
        "assets": [a.model_dump() for a in assets],
        "approvals": [
            {
                "id": f.id,
                "binding": f.binding,
                "status": f.status,
                "definition_version": f.definition_version,
                "created_at": f.created_at,
            }
            for f in s.exec(query(s, FlowInstance, t)).all()
            if f.binding in ("expense", "refund", "reversal")
            and f.record_id in (record_id, order_id)
        ],
        "ocr": [
            {"status": r.status, "output": r.output}
            for r in runs
            if r.input.get("asset_id") in {a.id for a in assets}
        ],
        "audit": [
            a.model_dump()
            for a in s.exec(
                query(s, AuditEvent, t).where(AuditEvent.target_id == record_id)
            ).all()
        ],
    }


@router.post("/finance/receipt-links")
def receipt_link(body: LinkInput, i: Identity = Depends(scoped)):
    permit(i, "finance.write")
    writable(i)
    finance_detail(body.kind, body.record_id, i)
    a = own(i.session, Asset, i.tenant.id, body.asset_id)
    check_asset(i, a)
    if "/receipt/" not in a.object_key:
        fail("PURPOSE_INVALID", "请选择财务票据")
    old = i.session.exec(
        query(i.session, ReceiptLink, i.tenant.id).where(
            ReceiptLink.kind == body.kind,
            ReceiptLink.record_id == body.record_id,
            ReceiptLink.asset_id == a.id,
        )
    ).first()
    if old:
        return old
    link = ReceiptLink(tenant_id=i.tenant.id, actor_id=i.user.id, **body.model_dump())
    i.session.add(link)
    ops.event(i.session, i.tenant.id, i.user.id, "receipt.linked", body.record_id)
    i.session.commit()
    return link


@router.get("/reports/{kind}")
def report(
    kind: str, period: str = "", class_id: str = "", i: Identity = Depends(scoped)
):
    if kind not in ("weekly", "monthly"):
        fail("PERIOD_INVALID", "报表类型错误")
    local = now().astimezone(reports.TZ)
    period = period or (
        (local - timedelta(days=local.weekday())).date().isoformat()
        if kind == "weekly"
        else local.strftime("%Y-%m")
    )
    out = reports.build(i, kind, period, class_id)
    i.session.commit()
    return out


@router.post("/report-snapshots/{kind}")
def generate_snapshot(kind: str, period: str, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    row = reports.snapshot(i, kind, period)
    i.session.commit()
    return row


@router.get("/report-snapshots")
def snapshots(i: Identity = Depends(scoped)):
    owner(i)
    return i.session.exec(
        query(i.session, ReportSnapshot, i.tenant.id)
        .order_by(ReportSnapshot.created_at.desc())
        .limit(200)
    ).all()


@router.get("/operations/alerts")
def alerts(i: Identity = Depends(scoped)):
    owner(i)
    rows = reports.evaluate_alerts(i, now().astimezone(reports.TZ).strftime("%Y-%m"))
    i.session.commit()
    return i.session.exec(
        query(i.session, OpsAlert, i.tenant.id).order_by(OpsAlert.updated_at.desc())
    ).all()


@router.patch("/operations/alerts/{alert_id}")
def acknowledge(alert_id: str, body: Note, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    r = own(i.session, OpsAlert, i.tenant.id, alert_id)
    r.note = body.note
    r.owner_id = i.user.id
    if r.status == "open":
        r.status = "acknowledged"
    i.session.add(r)
    ops.event(i.session, i.tenant.id, i.user.id, "alert.acknowledged", r.id)
    i.session.commit()
    return r


@router.put("/notifications/wecom")
def set_webhook(body: WebhookInput, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    if body.active:
        reports.webhook_valid(body.webhook)
    r = i.session.exec(
        query(i.session, Integration, i.tenant.id).where(
            Integration.provider == "wecom_notice"
        )
    ).first()
    if not r:
        r = Integration(tenant_id=i.tenant.id, provider="wecom_notice")
    r.secret_cipher = encrypt(i.tenant.id, body.webhook) if body.active else ""
    r.active = body.active
    i.session.add(r)
    i.tenant.settings = {
        **i.tenant.settings,
        "notice_version": i.tenant.settings.get("notice_version", 0) + 1,
    }
    i.session.add(i.tenant)
    ops.event(i.session, i.tenant.id, i.user.id, "notice.configured", r.id)
    i.session.commit()
    return {"configured": body.active}


@router.post("/notifications/test")
def test_notice(i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    r = reports.enqueue(
        i.session, i.tenant, "test:" + uid(), "test", "负责人管理群通知连接测试。"
    )
    i.session.commit()
    reports.delivery(i.session, i.tenant, r)
    return r


@router.get("/notifications")
def notifications(i: Identity = Depends(scoped)):
    owner(i)
    return i.session.exec(
        query(i.session, NotificationOutbox, i.tenant.id)
        .order_by(NotificationOutbox.created_at.desc())
        .limit(100)
    ).all()


@router.post("/notifications/{notice_id}/retry")
def retry_notice(notice_id: str, body: Note, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    r = own(i.session, NotificationOutbox, i.tenant.id, notice_id)
    if r.status not in ("failed", "unknown", "unconfigured", "cancelled"):
        fail("STATE_INVALID", "当前通知不可重试")
    if r.status == "unknown" and not body.verified_not_sent:
        fail("VERIFY_REQUIRED", "请先在企微核实未发送，避免重复消息")
    r.status = "queued"
    r.config_version = i.tenant.settings.get("notice_version", 0)
    r.next_attempt_at = now()
    r.error = ""
    i.session.add(r)
    i.session.commit()
    return r


@router.get("/admissions/template/{format}")
def template(format: str, definition_id: str = "", i: Identity = Depends(scoped)):
    permit(i, "lead.read")
    from .admission_import import xlsx_template, pdf_template

    if format == "xlsx":
        raw = xlsx_template(i, definition_id)
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif format == "pdf":
        raw = pdf_template(i, definition_id)
        mime = "application/pdf"
    else:
        fail("FORMAT_INVALID", "模板仅支持xlsx或pdf")
    return Response(
        raw,
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="admissions-template.{format}"'
        },
    )


def dispatch_import(t, bid):
    from .worker import pool, celery

    if settings().task_mode == "celery":
        celery.send_task("ops.admission_import", args=[bid, t], queue="ocr")
    elif settings().task_mode == "local" or (settings().demo_mode and settings().task_mode == "demo"):
        from .admission_import import execute

        pool.submit(execute, bid, t)


@router.post("/admissions/imports", status_code=201)
async def upload_import(
    file: UploadFile = File(...),
    definition_id: str = Form(""),
    i: Identity = Depends(scoped),
):
    permit(i, "lead.write")
    writable(i)
    raw = await file.read(25 * 1024 * 1024 + 1)
    if len(raw) > 25 * 1024 * 1024:
        fail("FILE_TOO_LARGE", "文件最大25MB")
    from .integrations.storage import upload_mime, save_asset

    mime = upload_mime(raw, file.filename or "scan")
    allowed = {
        "image/png",
        "image/jpeg",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }
    if mime not in allowed:
        fail("FILE_INVALID", "支持Excel、PNG、JPG和PDF")
    if settings().demo_mode and mime != "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
        fail("DEMO_OCR_PAUSED", "本演示可实际导入Excel招生表；扫描图片与PDF的真实OCR需单独启用和验收。", 409)
    key = hashlib.sha256(raw).hexdigest() + ":" + i.user.id
    previous = i.session.exec(
        query(i.session, AdmissionImport, i.tenant.id).where(
            AdmissionImport.request_id == key
        )
    ).first()
    if previous:
        return {
            "id": previous.id,
            "status": previous.status,
            "version": previous.version,
        }
    asset = save_asset(
        i.session, i.tenant.id, file.filename or "scan", raw, mime, purpose="document"
    )
    asset.uploaded_by = i.user.id
    i.session.add(asset)
    template_version = "admissions-1"
    if definition_id:
        from .admission_import import template_fields

        _, template_version = template_fields(i, definition_id)
    batch = AdmissionImport(
        tenant_id=i.tenant.id,
        actor_id=i.user.id,
        asset_id=asset.id,
        request_id=key,
        template_version=template_version,
    )
    i.session.add(batch)
    i.session.commit()
    dispatch_import(i.tenant.id, batch.id)
    return {"id": batch.id, "status": batch.status, "version": batch.version}


@router.get("/admissions/imports")
def imports(i: Identity = Depends(scoped)):
    permit(i, "lead.read")
    return [
        {
            "id": b.id,
            "status": b.status,
            "created_at": b.created_at,
            "progress": b.progress,
            "error": b.error,
            "version": b.version,
        }
        for b in i.session.exec(
            query(i.session, AdmissionImport, i.tenant.id)
            .order_by(AdmissionImport.created_at.desc())
            .limit(100)
        ).all()
        if b.actor_id == i.user.id or "owner" in i.roles
    ]


@router.get("/admissions/imports/{batch_id}")
def import_detail(batch_id: str, i: Identity = Depends(scoped)):
    permit(i, "lead.read")
    b = own(i.session, AdmissionImport, i.tenant.id, batch_id)
    if b.actor_id != i.user.id and "owner" not in i.roles:
        fail("NOT_FOUND", "导入不存在", 404)
    return {k: v for k, v in b.model_dump().items() if k != "rows_cipher"} | {
        "rows": studio.unseal(i.tenant.id, b.rows_cipher) if b.rows_cipher else []
    }


@router.post("/admissions/imports/{batch_id}/confirm")
def confirm_import(batch_id: str, body: ImportConfirm, i: Identity = Depends(scoped)):
    writable(i)
    from .admission_import import confirm

    b = own(i.session, AdmissionImport, i.tenant.id, batch_id)
    b = i.session.exec(
        query(i.session, AdmissionImport, i.tenant.id)
        .where(AdmissionImport.id == b.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    result = confirm(i, b, body.rows, body.version)
    i.session.commit()
    return result


@router.post("/admissions/imports/{batch_id}/retry")
def retry_import(batch_id: str, i: Identity = Depends(scoped)):
    permit(i, "lead.write")
    writable(i)
    b = own(i.session, AdmissionImport, i.tenant.id, batch_id)
    if b.actor_id != i.user.id and "owner" not in i.roles:
        fail("NOT_FOUND", "导入不存在", 404)
    if b.status == "processing" and as_utc(b.updated_at) < now() - timedelta(
        minutes=15
    ):
        b.status = "failed"
    if b.status != "failed":
        fail("STATE_INVALID", "只有失败识别可重新执行")
    b.status = "queued"
    b.updated_at = now()
    b.error = ""
    b.version += 1
    i.session.add(b)
    i.session.commit()
    dispatch_import(i.tenant.id, b.id)
    return {"id": b.id, "status": b.status}


@router.get("/studio/templates")
def studio_templates(i: Identity = Depends(scoped)):
    owner(i)
    return studio.templates()


@router.get("/studio/definitions")
def definitions(kind: str = "", i: Identity = Depends(scoped)):
    rows = i.session.exec(query(i.session, StudioDefinition, i.tenant.id)).all()
    out = []
    for r in rows:
        if kind and r.kind != kind:
            continue
        if "owner" in i.roles:
            out.append(r.model_dump())
        elif r.published_version:
            try:
                studio.check_binding(i, r.binding, "", True)
            except Exception:
                continue
            spec = studio.definition_version(i.session, i.tenant.id, r).spec
            out.append(
                {
                    **r.model_dump(exclude={"draft"}),
                    "draft": {
                        "fields": studio.visible_fields(i, spec.get("fields", []))
                    }
                    if r.kind == "form"
                    else {},
                }
            )
    return out


@router.post("/studio/definitions", status_code=201)
def create_definition(body: DefinitionInput, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    if body.kind not in ("form", "workflow") or body.binding not in studio.BINDINGS:
        fail("SCHEMA_INVALID", "定义类型或绑定业务错误")
    row = StudioDefinition(
        tenant_id=i.tenant.id,
        created_by=i.user.id,
        name=body.name,
        kind=body.kind,
        binding=body.binding,
        draft=body.spec,
        enabled=False,
    )
    i.session.add(row)
    i.session.commit()
    return row


@router.patch("/studio/definitions/{definition_id}")
def edit_definition(
    definition_id: str, body: DefinitionInput, i: Identity = Depends(scoped)
):
    owner(i)
    writable(i)
    r = own(i.session, StudioDefinition, i.tenant.id, definition_id)
    r = studio.lock_definition(i, r.id)
    if body.version != r.version:
        fail("VERSION_CONFLICT", "定义已更新，请刷新", 409)
    if body.kind != r.kind or body.binding != r.binding:
        fail("SCHEMA_INVALID", "发布对象绑定不可变更，请复制新建")
    if body.enabled and not r.published_version:
        fail("VERSION_REQUIRED", "先发布后启用")
    if body.enabled and r.kind == "workflow":
        other = i.session.exec(
            query(i.session, StudioDefinition, i.tenant.id).where(
                StudioDefinition.binding == r.binding,
                StudioDefinition.kind == "workflow",
                StudioDefinition.enabled == True,
                StudioDefinition.id != r.id,
            )
        ).first()
        if other:
            fail("FLOW_CONFLICT", "该业务已有启用的流程，请先停用旧流程")
    r.name = body.name
    r.draft = body.spec
    r.enabled = body.enabled
    r.version += 1
    i.session.add(r)
    ops.event(i.session, i.tenant.id, i.user.id, "definition.updated", r.id)
    i.session.commit()
    return r


@router.post("/studio/definitions/{definition_id}/publish")
def publish_definition(definition_id: str, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    r = studio.publish(i, own(i.session, StudioDefinition, i.tenant.id, definition_id))
    i.session.commit()
    return r


@router.get("/studio/definitions/{definition_id}/versions")
def versions(definition_id: str, i: Identity = Depends(scoped)):
    owner(i)
    own(i.session, StudioDefinition, i.tenant.id, definition_id)
    return i.session.exec(
        query(i.session, StudioVersion, i.tenant.id)
        .where(StudioVersion.definition_id == definition_id)
        .order_by(StudioVersion.version.desc())
    ).all()


@router.post("/studio/definitions/{definition_id}/restore/{version}")
def restore_version(definition_id: str, version: int, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    d = own(i.session, StudioDefinition, i.tenant.id, definition_id)
    v = studio.definition_version(i.session, i.tenant.id, d, version)
    d.draft = v.spec
    d.version += 1
    i.session.add(d)
    i.session.commit()
    return d


@router.post("/studio/definitions/{definition_id}/preview")
def preview_definition(
    definition_id: str, body: SubmissionInput, i: Identity = Depends(scoped)
):
    owner(i)
    d = own(i.session, StudioDefinition, i.tenant.id, definition_id)
    studio.validate_spec(d.kind, d.draft)
    if d.kind == "form":
        return {
            "valid": True,
            "values": studio.values_for(i, d.draft["fields"], body.values, True),
        }
    decisions = {
        n["id"]: "yes"
        if studio.condition(n["data"].get("condition", {}), body.values)
        else "no"
        for n in d.draft["nodes"]
        if n["data"]["kind"] == "condition"
    }
    _, reachable, _ = studio.graph_state(d.draft, {"decisions": decisions}, body.values)
    return {
        "valid": True,
        "reachable_nodes": sorted(reachable),
        "decisions": decisions,
        "side_effects": False,
    }


@router.get("/studio/forms/{definition_id}")
def published_form(definition_id: str, i: Identity = Depends(scoped)):
    d = own(i.session, StudioDefinition, i.tenant.id, definition_id)
    if d.kind != "form":
        fail("KIND_INVALID", "不是表单")
    studio.check_binding(i, d.binding, "", True)
    v = studio.definition_version(i.session, i.tenant.id, d)
    return {
        "definition": d.model_dump(exclude={"draft"}),
        "version": v.version,
        "fields": studio.visible_fields(i, v.spec.get("fields", [])),
    }


@router.post("/studio/forms/{definition_id}/submissions", status_code=201)
def submit_form(
    definition_id: str, body: SubmissionInput, i: Identity = Depends(scoped)
):
    writable(i)
    d = own(i.session, StudioDefinition, i.tenant.id, definition_id)
    if d.kind != "form":
        fail("KIND_INVALID", "请选择表单")
    studio.check_binding(i, d.binding, body.record_id, True)
    v = studio.definition_version(i.session, i.tenant.id, d)
    values = studio.values_for(i, v.spec.get("fields", []), body.values, True)
    old = i.session.exec(
        query(i.session, FormSubmission, i.tenant.id).where(
            FormSubmission.request_id == body.request_id
        )
    ).first()
    if old:
        if (
            old.actor_id != i.user.id
            or old.definition_id != d.id
            or studio.fingerprint(studio.unseal(i.tenant.id, old.values_cipher))
            != studio.fingerprint(values)
        ):
            fail("IDEMPOTENCY_CONFLICT", "请求编号已使用", 409)
        return {"id": old.id, "status": old.status}
    if body.definition_version is not None and body.definition_version != v.version:
        fail("VERSION_CONFLICT", "表单版本已更新，请刷新后提交", 409)
    row = FormSubmission(
        tenant_id=i.tenant.id,
        definition_id=d.id,
        definition_version=v.version,
        actor_id=i.user.id,
        values_cipher=studio.seal(i.tenant.id, values),
        binding=d.binding,
        record_id=body.record_id,
        request_id=body.request_id,
    )
    i.session.add(row)
    i.session.flush()
    if v.spec.get("workflow_id"):
        flow = own(i.session, StudioDefinition, i.tenant.id, v.spec["workflow_id"])
        instance = studio.submit(
            i,
            flow,
            {"_form_submission_id": row.id, "values": values},
            "",
            "form:" + row.id,
            v.spec.get("workflow_version"),
        )
        row.status = instance.status
        i.session.add(row)
    ops.event(i.session, i.tenant.id, i.user.id, "form.submitted", row.id)
    i.session.commit()
    return {"id": row.id, "status": row.status}


@router.get("/studio/submissions")
def form_submissions(i: Identity = Depends(scoped)):
    out = []
    for row in i.session.exec(
        query(i.session, FormSubmission, i.tenant.id)
        .order_by(FormSubmission.created_at.desc())
        .limit(200)
    ).all():
        if row.actor_id != i.user.id and "owner" not in i.roles:
            continue
        try:
            studio.check_binding(i, row.binding, row.record_id)
        except Exception:
            continue
        d = own(i.session, StudioDefinition, i.tenant.id, row.definition_id)
        v = studio.definition_version(i.session, i.tenant.id, d, row.definition_version)
        out.append(
            {k: x for k, x in row.model_dump().items() if k != "values_cipher"}
            | {
                "name": d.name,
                "values": studio.values_for(
                    i,
                    v.spec.get("fields", []),
                    studio.unseal(i.tenant.id, row.values_cipher),
                ),
            }
        )
    return out


@router.post("/studio/workflows/{definition_id}/instances", status_code=201)
def submit_workflow(definition_id: str, body: FlowInput, i: Identity = Depends(scoped)):
    writable(i)
    d = own(i.session, StudioDefinition, i.tenant.id, definition_id)
    if d.kind != "workflow":
        fail("KIND_INVALID", "请选择流程")
    if any(k.startswith("_") for k in body.payload):
        fail("FIELD_FORBIDDEN", "保留字段不可由客户端设置", 403)
    row = studio.submit(i, d, body.payload, body.record_id, body.request_id)
    i.session.commit()
    return studio.instance_public(i, row)


@router.get("/studio/instances")
def instances(i: Identity = Depends(scoped)):
    out = []
    for r in i.session.exec(
        query(i.session, FlowInstance, i.tenant.id)
        .order_by(FlowInstance.created_at.desc())
        .limit(200)
    ).all():
        if studio.can_view_instance(i, r):
            d = own(i.session, StudioDefinition, i.tenant.id, r.definition_id)
            out.append(
                {k: v for k, v in r.model_dump().items() if k != "payload_cipher"}
                | {"name": d.name}
            )
    return out


@router.get("/studio/instances/{instance_id}")
def instance_detail(instance_id: str, i: Identity = Depends(scoped)):
    r = own(i.session, FlowInstance, i.tenant.id, instance_id)
    if not studio.can_view_instance(i, r):
        fail("NOT_FOUND", "流程不可访问", 404)
    return studio.instance_public(i, r, True) | {
        "tasks": i.session.exec(
            query(i.session, FlowTask, i.tenant.id).where(FlowTask.instance_id == r.id)
        ).all()
    }


@router.post("/studio/instances/{instance_id}/apply")
def apply_approved(instance_id: str, body: dict, i: Identity = Depends(scoped)):
    writable(i)
    inst = studio.lock_instance(i, instance_id)
    if not inst or not studio.can_view_instance(i, inst):
        fail("NOT_FOUND", "流程不可访问", 404)
    studio.check_binding(i, inst.binding, inst.record_id, True)
    studio.check_binding(
        studio.actor(i.session, i.tenant.id, inst.actor_id),
        inst.binding,
        inst.record_id,
        True,
    )
    if inst.status in ("completed", "consumed"):
        return studio.instance_public(i, inst)
    if inst.status != "approved":
        fail("WORKFLOW_REQUIRED", "流程尚未通过", 409)
    if (
        inst.record_id
        and inst.binding != "reversal"
        and own(i.session, Record, i.tenant.id, inst.record_id).version
        != inst.state.get("record_version")
    ):
        fail("WORKFLOW_STALE", "业务已变更，请重新提交", 409)
    if inst.binding in ("refund", "expense", "reversal"):
        permit(i, "finance.write")
        if body.get("actual_confirmed") is not True:
            fail("ACTUAL_CONFIRMATION_REQUIRED", "请确认实际发生")
        inst.state = {**inst.state, "actual_confirmed": True}
    if inst.binding != "independent":
        studio.apply_action(i, inst, {"action": inst.binding})
    inst.status = "completed"
    i.session.add(inst)
    ops.event(i.session, i.tenant.id, i.user.id, "workflow.applied", inst.id)
    i.session.commit()
    return studio.instance_public(i, inst)


@router.get("/studio/tasks")
def tasks(i: Identity = Depends(scoped)):
    out = []
    for r in i.session.exec(
        query(i.session, FlowTask, i.tenant.id).where(
            FlowTask.status.in_(["pending", "unassigned"])
        )
    ).all():
        if r.assignee_id != i.user.id and "owner" not in i.roles:
            continue
        inst = own(i.session, FlowInstance, i.tenant.id, r.instance_id)
        if inst.status != "running" or not studio.can_view_instance(i, inst):
            continue
        d = own(i.session, StudioDefinition, i.tenant.id, inst.definition_id)
        spec = studio.definition_version(
            i.session, i.tenant.id, d, inst.definition_version
        ).spec
        node = next(n["data"] for n in spec["nodes"] if n["id"] == r.node_id)
        allowed = studio.eligible(i.session, i.tenant.id, node)
        override = inst.state.get("assignee_overrides", {}).get(r.id)
        if override:
            try:
                replacement = studio.actor(i.session, i.tenant.id, override)
                studio.check_binding(replacement, inst.binding, inst.record_id, True)
                allowed.append(override)
            except Exception:
                pass
        valid = not r.assignee_id or r.assignee_id in allowed
        if not valid:
            r.status = "unassigned"
            r.assignee_id = ""
            i.session.add(r)
            if "owner" not in i.roles:
                continue
        if r.status == "unassigned" and "owner" not in i.roles:
            continue
        out.append(
            {
                **r.model_dump(),
                "name": d.name,
                "node_label": node.get("label", r.node_id),
                "can_decide": valid
                and r.status == "pending"
                and r.assignee_id == i.user.id,
                "binding": inst.binding,
            }
        )
    i.session.commit()
    return out


@router.post("/studio/tasks/{task_id}/decision")
def task_decision(task_id: str, body: DecisionInput, i: Identity = Depends(scoped)):
    writable(i)
    r = studio.decide(i, task_id, body.decision, body.note, body.values)
    i.session.commit()
    return studio.instance_public(i, r)


@router.post("/studio/tasks/{task_id}/assign")
def assign_task(task_id: str, user_id: str, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    r = own(i.session, FlowTask, i.tenant.id, task_id)
    inst = studio.lock_instance(i, r.instance_id)
    i.session.refresh(r)
    if r.status not in ("pending", "unassigned") or inst.status != "running":
        fail("STATE_INVALID", "待办已经处理")
    d = own(i.session, StudioDefinition, i.tenant.id, inst.definition_id)
    spec = studio.definition_version(
        i.session, i.tenant.id, d, inst.definition_version
    ).spec
    node = next(n["data"] for n in spec["nodes"] if n["id"] == r.node_id)
    if user_id not in studio.eligible(i.session, i.tenant.id, node):
        if r.status != "unassigned":
            fail("ROLE_FORBIDDEN", "所选人员不具备节点要求的岗位", 403)
        replacement = studio.actor(i.session, i.tenant.id, user_id)
        studio.check_binding(replacement, inst.binding, inst.record_id, True)
        inst.state = {
            **inst.state,
            "assignee_overrides": {
                **inst.state.get("assignee_overrides", {}),
                r.id: user_id,
            },
        }
        i.session.add(inst)
    duplicate = i.session.exec(
        query(i.session, FlowTask, i.tenant.id).where(
            FlowTask.instance_id == inst.id,
            FlowTask.node_id == r.node_id,
            FlowTask.assignee_id == user_id,
            FlowTask.id != r.id,
        )
    ).first()
    if duplicate:
        fail("ASSIGNEE_EXISTS", "该人员已有同一节点的待办，请勿重复分配", 409)
    r.assignee_id = user_id
    r.status = "pending"
    i.session.add(r)
    ops.event(i.session, i.tenant.id, i.user.id, "workflow.assigned", inst.id)
    i.session.commit()
    return r


@router.post("/studio/instances/{instance_id}/withdraw")
def withdraw_flow(instance_id: str, i: Identity = Depends(scoped)):
    writable(i)
    r = own(i.session, FlowInstance, i.tenant.id, instance_id)
    r = studio.lock_instance(i, r.id)
    if r.actor_id != i.user.id and "owner" not in i.roles:
        fail("ROLE_FORBIDDEN", "无权撤回", 403)
    if r.status not in ("running", "returned", "approved"):
        fail("STATE_INVALID", "已执行业务不可撤回，请使用相应冲正流程")
    r.status = "withdrawn"
    i.session.add(r)
    for task in i.session.exec(
        query(i.session, FlowTask, i.tenant.id).where(
            FlowTask.instance_id == r.id, FlowTask.status == "pending"
        )
    ).all():
        task.status = "cancelled"
        i.session.add(task)
    ops.event(i.session, i.tenant.id, i.user.id, "workflow.withdrawn", r.id)
    i.session.commit()
    return {"status": r.status}


@router.post("/studio/instances/{instance_id}/resubmit", status_code=201)
def resubmit_flow(instance_id: str, body: FlowInput, i: Identity = Depends(scoped)):
    writable(i)
    old = own(i.session, FlowInstance, i.tenant.id, instance_id)
    if old.actor_id != i.user.id or old.status not in (
        "returned",
        "rejected",
        "withdrawn",
    ):
        fail("STATE_INVALID", "当前流程不能重新提交")
    d = own(i.session, StudioDefinition, i.tenant.id, old.definition_id)
    if any(k.startswith("_") for k in body.payload):
        fail("FIELD_FORBIDDEN", "保留字段不可由客户端设置", 403)
    payload = dict(body.payload)
    source = studio.unseal(i.tenant.id, old.payload_cipher).get("_form_submission_id")
    if source:
        form = own(i.session, FormSubmission, i.tenant.id, source)
        studio.check_binding(i, form.binding, form.record_id, True)
        fd = own(i.session, StudioDefinition, i.tenant.id, form.definition_id)
        fv = studio.definition_version(
            i.session, i.tenant.id, fd, form.definition_version
        )
        values = studio.values_for(
            i, fv.spec.get("fields", []), payload.get("values", payload), True
        )
        key = "resubmit:" + body.request_id
        replacement = i.session.exec(
            query(i.session, FormSubmission, i.tenant.id).where(
                FormSubmission.request_id == key
            )
        ).first()
        if replacement:
            if replacement.actor_id != i.user.id or studio.fingerprint(
                studio.unseal(i.tenant.id, replacement.values_cipher)
            ) != studio.fingerprint(values):
                fail("IDEMPOTENCY_CONFLICT", "重新提交的内容不一致", 409)
        else:
            replacement = FormSubmission(
                tenant_id=i.tenant.id,
                definition_id=fd.id,
                definition_version=fv.version,
                actor_id=i.user.id,
                values_cipher=studio.seal(i.tenant.id, values),
                binding=form.binding,
                record_id=form.record_id,
                request_id=key,
                revision=form.revision + 1,
            )
            i.session.add(replacement)
            i.session.flush()
        payload = {"_form_submission_id": replacement.id, "values": values}
    r = studio.submit(
        i, d, payload, body.record_id, body.request_id, old.definition_version
    )
    r.revision = old.revision + 1
    i.session.add(r)
    i.session.commit()
    return studio.instance_public(i, r)


@router.get("/addons/digital-human")
def addon(i: Identity = Depends(scoped)):
    return {
        "name": "数字人直播",
        "provider_connected": False,
        "state": "pending_integration",
        "price_label": "申请报价",
        "description": "付费增值服务，供应商和真实直播尚待接入。",
        "requests": i.session.exec(query(i.session, AddOnRequest, i.tenant.id)).all()
        if "owner" in i.roles
        else [],
    }


@router.post("/addons/digital-human/requests", status_code=201)
def apply_addon(body: AddonInput, i: Identity = Depends(scoped)):
    owner(i)
    writable(i)
    r = AddOnRequest(tenant_id=i.tenant.id, actor_id=i.user.id, note=body.note)
    i.session.add(r)
    i.session.commit()
    return r


@router.get("/platform/addon-requests")
def platform_addons(i: Identity = Depends(platform)):
    # Explicit platform metadata only; never returns institution business rows.
    result = []
    for t in i.session.exec(select(Tenant)).all():
        set_scope(i.session, t.id, i.user.id)
        result.extend(
            [
                {**r.model_dump(), "tenant_name": t.name}
                for r in i.session.exec(query(i.session, AddOnRequest, t.id)).all()
            ]
        )
    set_scope(i.session, i.auth.tenant_id or "", i.user.id)
    return result


@router.patch("/platform/addon-requests/{tenant_id}/{request_id}")
def review_addon(
    tenant_id: str, request_id: str, body: AddonReview, i: Identity = Depends(platform)
):
    if body.status not in (
        "requested",
        "quoted",
        "approved_pending_integration",
        "declined",
    ):
        fail("STATE_INVALID", "权益状态无效")
    set_scope(i.session, tenant_id, i.user.id)
    r = own(i.session, AddOnRequest, tenant_id, request_id)
    r.status = body.status
    r.platform_note = body.note
    i.session.add(r)
    i.session.commit()
    return r


@router.get("/operations/events")
async def events(
    request: Request, tenant_id: str, i: Identity = Depends(scoped, scope="function")
):
    if tenant_id != i.tenant.id:
        fail("TENANT_FORBIDDEN", "机构已变更", 403)

    async def stream():
        last = request.headers.get("last-event-id", "")
        yield "event: refresh\ndata: {}\n\n"
        while not await request.is_disconnected():
            try:
                with Session(engine()) as s:
                    fresh = current(request, s)
                    if (
                        not fresh.tenant
                        or fresh.tenant.id != tenant_id
                        or fresh.tenant.status != "active"
                    ):
                        break
                    latest = s.exec(
                        query(s, BusinessEvent, tenant_id)
                        .order_by(
                            BusinessEvent.created_at.desc(), BusinessEvent.id.desc()
                        )
                        .limit(1)
                    ).first()
                    marker = latest.id if latest else ""
                    if marker != last:
                        last = marker
                        yield "id: " + marker + "\nevent: refresh\ndata: {}\n\n"
                    else:
                        yield ": heartbeat\n\n"
            except Exception:
                break
            await asyncio.sleep(2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

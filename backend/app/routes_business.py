import csv, io, json
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import Response
from sqlmodel import select
from .models import *
from . import schemas as S
from .auth import Identity, scoped, require, writable
from .domain import *
from .security import fail
from .permissions import Scope, permit, has, permissions

from .routes_operations import RefundInput
from . import operations, studio

router = APIRouter(prefix="/api/v1", tags=["招生、教务与财务"])


@router.get("/dashboard")
def dashboard(i: Identity = Depends(scoped)):
    scope = Scope(i)
    visible = [r for r in scope.rows.values() if scope.visible(r)]
    from collections import Counter

    result = {
        "counts": dict(Counter(r.kind for r in visible)),
        "chart": [],
        "followups": [],
    }
    if has(i, "lead.read"):
        result["followups"] = [
            scope.project(r)
            for r in visible
            if r.kind == "lead"
            and r.data.get("followup_at")
            and r.data.get("stage") not in ("won", "lost")
        ][:6]
    if has(i, "finance.read"):
        full = summary(i.session, i.tenant.id)
        for key in ("net_revenue_fen", "expense_fen", "commission_fen", "chart"):
            result[key] = full[key]
    if has(i, "revenue.read"):
        from .reports import financial, TZ

        local = now().astimezone(TZ)
        result["revenue"] = financial(
            i,
            local.replace(day=1, hour=0, minute=0, second=0, microsecond=0),
            now(),
            details=False,
        )
    if has(i, "publish.read"):
        jobs = i.session.exec(query(i.session, PublishJob, i.tenant.id)).all()
        result.update(
            published=sum(j.status == "succeeded" for j in jobs),
            pending_jobs=sum(j.status not in ("succeeded", "cancelled") for j in jobs),
        )
    if has(i, "education.read"):
        rows = operations.kpi_rows(i)
        result["feedback_kpi"] = {
            "expected": len(rows),
            "completed": sum(r.completed_at is not None for r in rows),
            "overdue": sum(
                r.completed_at is None and as_utc(r.due_at) < now() for r in rows
            ),
        }
    if "owner" in i.roles:
        result["alert_count"] = len(
            i.session.exec(
                query(i.session, OpsAlert, i.tenant.id).where(
                    OpsAlert.status.in_(["open", "acknowledged"])
                )
            ).all()
        )
    i.session.commit()
    result["permissions"] = sorted(permissions(i.roles))
    return result


@router.get("/records/{kind}")
def records(
    kind: str,
    q: str = "",
    skip: int = 0,
    limit: int = 100,
    i: Identity = Depends(scoped),
):
    if skip < 0 or not 1 <= limit <= 200:
        fail("PAGINATION_INVALID", "分页参数错误")
    scope = Scope(i)
    rows = sorted(scope.list(kind), key=lambda r: r.created_at, reverse=True)
    items = [scope.project(r) for r in rows]
    if q:
        items = [
            r
            for r in items
            if q.lower() in json.dumps(r["data"], ensure_ascii=False).lower()
        ]
    return {"items": items[skip : skip + limit], "total": len(items)}


@router.post("/records/{kind}", status_code=201)
def add_record(kind: str, body: S.RecordInput, i: Identity = Depends(scoped)):
    writable(i)
    scope = Scope(i)
    data = scope.validate_write(kind, dict(body.data))
    studio.guard_action(i, kind, "", body.data, body.workflow_id)
    record = create_record(i.session, i.tenant.id, i.user.id, kind, data)
    i.session.commit()
    return Scope(i).project(record)


@router.patch("/records/{kind}/{record_id}")
def edit_record(
    kind: str, record_id: str, body: S.RecordInput, i: Identity = Depends(scoped)
):
    writable(i)
    scope = Scope(i)
    old = scope.own(record_id, kind, "write")
    data = scope.validate_write(kind, dict(body.data), old)
    studio.guard_action(i, kind, record_id, body.data, body.workflow_id)
    record = update_record(
        i.session, i.tenant.id, i.user.id, record_id, data, body.version
    )
    i.session.commit()
    return Scope(i).project(record)


@router.post("/orders/{order_id}/payments")
def payment(order_id: str, body: S.MoneyAction, i: Identity = Depends(scoped)):
    permit(i, "finance.write")
    writable(i)
    entry = record_money(
        i.session,
        i.tenant.id,
        i.user.id,
        order_id,
        "payment",
        body.amount_fen,
        body.request_id,
        body.note,
    )
    i.session.commit()
    return entry


@router.post("/orders/{order_id}/refunds")
def refund(order_id: str, body: RefundInput, i: Identity = Depends(scoped)):
    permit(i, "finance.write")
    writable(i)
    entry = operations.refund(i, order_id, body)
    i.session.commit()
    return entry


class ReversalInput(S.ActionId):
    workflow_id: str = ""
    note: str = ""


@router.post("/ledger/{entry_id}/reverse")
def reversal(entry_id: str, body: ReversalInput, i: Identity = Depends(scoped)):
    permit(i, "finance.write")
    writable(i)
    studio.guard_action(i, "reversal", entry_id, {"note": body.note}, body.workflow_id)
    entry = reverse_money(i.session, i.tenant.id, i.user.id, entry_id, body.request_id)
    i.session.commit()
    return entry


@router.get("/ledger")
def ledger(i: Identity = Depends(scoped)):
    permit(i, "finance.write")
    return i.session.exec(
        query(i.session, LedgerEntry, i.tenant.id)
        .order_by(LedgerEntry.created_at.desc())
        .limit(500)
    ).all()


class AttendInput(S.ActionId):
    lesson_id: str


@router.post("/enrollments/{enrollment_id}/attendance")
def attendance(enrollment_id: str, body: AttendInput, i: Identity = Depends(scoped)):
    permit(i, "education.read")
    writable(i)
    permit(i, "attendance.write")
    scope = Scope(i)
    scope.own(enrollment_id, "enrollment")
    scope.own(body.lesson_id, "lesson")
    entry = attend(
        i.session,
        i.tenant.id,
        i.user.id,
        enrollment_id,
        body.lesson_id,
        body.request_id,
    )
    i.session.commit()
    return entry


@router.get("/attendance")
def attendances(i: Identity = Depends(scoped)):
    permit(i, "attendance.read")
    ids = {r.id for r in Scope(i).list("enrollment")}
    return i.session.exec(
        query(i.session, CreditEntry, i.tenant.id)
        .where(CreditEntry.enrollment_id.in_(ids))
        .order_by(CreditEntry.created_at.desc())
        .limit(500)
    ).all()


@router.get("/settlements")
def settlements(i: Identity = Depends(scoped)):
    permit(i, "finance.write")
    orders = i.session.exec(
        query(i.session, Record, i.tenant.id).where(Record.kind == "order")
    ).all()
    result = []
    for order in orders:
        net = balance(i.session, i.tenant.id, order.id)
        result.append(
            {
                "order_id": order.id,
                "name": order.data["name"],
                "channel_id": order.data.get("channel_id", ""),
                "net_fen": net,
                "commission_bps": order.data.get("commission_bps", 0),
                "commission_fen": commission_for(order, net),
            }
        )
    return result


def safe_cell(value):
    if isinstance(value, (int, float, bool)):
        return value
    value = str(value if value is not None else "")
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        else value
    )


@router.get("/exports/{kind}")
def export(kind: str, format: str = "csv", i: Identity = Depends(scoped)):
    scope = Scope(i)
    records = scope.list(kind)
    rows = [{"id": r.id, **scope.project(r)["data"]} for r in records]
    fields = list(dict.fromkeys(k for row in rows for k in row)) or ["id"]
    if format == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "机构台账"
        ws.append(fields)
        for row in rows:
            ws.append([safe_cell(row.get(k, "")) for k in fields])
        out = io.BytesIO()
        wb.save(out)
        audit(i.session, i.tenant.id, i.user.id, "export", kind, count=len(rows))
        i.session.commit()
        return Response(
            out.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{kind}.xlsx"'},
        )
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: safe_cell(row.get(k, "")) for k in fields})
    audit(i.session, i.tenant.id, i.user.id, "export", kind, count=len(rows))
    i.session.commit()
    return Response(
        ("\ufeff" + out.getvalue()).encode(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'},
    )


@router.post("/imports/payments")
async def import_payments(file: UploadFile = File(...), i: Identity = Depends(scoped)):
    permit(i, "finance.write")
    writable(i)
    raw = await file.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        fail("FILE_TOO_LARGE", "账单请控制在1MB以内")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        if len(rows) > 500:
            fail("IMPORT_TOO_LARGE", "每次最多500笔")
        result = []
        for row in rows:
            amount = Decimal(row["amount_yuan"])
            if not amount.is_finite() or amount <= 0 or amount > 1000000:
                fail("AMOUNT_INVALID", "金额需大于0且不超过100万元")
            if amount.as_tuple().exponent < -2:
                fail("AMOUNT_INVALID", "Amount must have at most two decimal places")
            if not row["transaction_id"] or len(row["transaction_id"]) > 80:
                fail(
                    "TRANSACTION_INVALID",
                    "Transaction identifier required, at most 80 characters",
                )
            fen = int(amount * 100)
            if fen <= 0:
                fail("AMOUNT_INVALID", "收款金额必须大于0")
            entry = record_money(
                i.session,
                i.tenant.id,
                i.user.id,
                row["order_id"],
                "payment",
                fen,
                "import:" + row["transaction_id"],
                row.get("note", ""),
            )
            result.append(entry.id)
        i.session.commit()
        return {"imported": len(result), "ids": result}
    except (KeyError, UnicodeDecodeError, InvalidOperation, ValueError):
        fail(
            "CSV_INVALID",
            "CSV需要 order_id、amount_yuan、transaction_id 三列，金额必须有效",
        )


@router.get("/audit")
def audit_events(i: Identity = Depends(scoped)):
    permit(i, "audit.read")
    return i.session.exec(
        query(i.session, AuditEvent, i.tenant.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(200)
    ).all()


@router.get("/subscription")
def subscription(i: Identity = Depends(scoped)):
    permit(i, "usage.read")
    return {
        **entitlement(i.session, i.tenant),
        "quotas": i.tenant.settings.get("quotas", {}),
        "funding": i.tenant.settings.get("funding", "platform"),
        "payment_enabled": False,
        "plan_id": i.tenant.settings.get("plan_id", ""),
        "plans": (i.session.get(PlatformSettings, 1) or PlatformSettings()).plans.get(
            "catalog", []
        ),
    }


@router.get("/usage", response_model=S.UsageView)
def usage(i: Identity = Depends(scoped)):
    permit(i, "usage.read")
    rows = i.session.exec(
        query(i.session, UsageRecord, i.tenant.id)
        .order_by(UsageRecord.created_at.desc())
        .limit(200)
    ).all()
    buckets = i.session.exec(
        query(i.session, BudgetBucket, i.tenant.id).where(
            BudgetBucket.period == now().strftime("%Y-%m")
        )
    ).all()
    return {
        "items": rows,
        "buckets": buckets,
        "quotas": i.tenant.settings.get("quotas", {}),
    }


@router.get("/tenant/booking-qr")
def booking_qr(i: Identity = Depends(scoped)):
    permit(i, "booking.read")
    import qrcode
    from .config import settings

    out = io.BytesIO()
    qrcode.make(
        settings().public_url.rstrip("/") + "/book/" + i.tenant.slug + "?source=qr"
    ).save(out, format="PNG")
    return Response(
        out.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store"},
    )


@router.post("/enrollments/{enrollment_id}/adjust")
def adjust_credit(
    enrollment_id: str, body: S.CreditAdjustment, i: Identity = Depends(scoped)
):
    permit(i, "credit.write")
    writable(i)
    if body.delta == 0:
        fail("ADJUSTMENT_ZERO", "调整课时不能为0")
    enrollment = ref(i.session, i.tenant.id, enrollment_id, "enrollment")
    i.session.exec(
        query(i.session, Record, i.tenant.id)
        .where(Record.id == enrollment.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    prior = i.session.exec(
        query(i.session, CreditEntry, i.tenant.id).where(
            CreditEntry.request_id == body.request_id
        )
    ).first()
    if prior:
        if prior.enrollment_id != enrollment_id or prior.delta != body.delta:
            fail("IDEMPOTENCY_CONFLICT", "调整参数不同", 409)
        return prior
    if credit_balance(i.session, i.tenant.id, enrollment_id) + body.delta < 0:
        fail("CREDIT_NEGATIVE", "调整后剩余课时不能为负数")
    entry = CreditEntry(
        tenant_id=i.tenant.id,
        enrollment_id=enrollment_id,
        delta=body.delta,
        kind="adjustment",
        request_id=body.request_id,
        actor_id=i.user.id,
    )
    i.session.add(entry)
    audit(
        i.session,
        i.tenant.id,
        i.user.id,
        "education.adjust",
        enrollment_id,
        delta=body.delta,
        reason=body.reason,
    )
    i.session.commit()
    return entry


@router.get("/education/alerts")
def education_alerts(i: Identity = Depends(scoped)):
    permit(i, "education.read")
    enrollments = i.session.exec(
        query(i.session, Record, i.tenant.id).where(Record.kind == "enrollment")
    ).all()
    lessons = i.session.exec(
        query(i.session, Record, i.tenant.id).where(Record.kind == "lesson")
    ).all()
    credits = i.session.exec(
        query(i.session, CreditEntry, i.tenant.id).where(
            CreditEntry.kind == "attendance"
        )
    ).all()
    scope = Scope(i)
    enrollments = [r for r in enrollments if scope.visible(r)]
    lessons = [r for r in lessons if scope.visible(r)]
    credits = [r for r in credits if r.enrollment_id in {e.id for e in enrollments}]
    attended = {(x.enrollment_id, x.lesson_id) for x in credits}
    low = []
    absent = []
    for enrollment in enrollments:
        remaining = credit_balance(i.session, i.tenant.id, enrollment.id)
        if remaining < 2:
            low.append(
                {
                    "enrollment_id": enrollment.id,
                    "student_id": enrollment.data["student_id"],
                    "remaining": remaining,
                }
            )
        for lesson in lessons:
            if lesson.data["status"] != "completed" or lesson.data[
                "class_id"
            ] != enrollment.data.get("class_id"):
                continue
            if (enrollment.id, lesson.id) not in attended:
                absent.append(
                    {
                        "enrollment_id": enrollment.id,
                        "student_id": enrollment.data["student_id"],
                        "lesson_id": lesson.id,
                        "lesson": lesson.data["name"],
                    }
                )
    leaves = i.session.exec(
        query(i.session, Record, i.tenant.id).where(Record.kind == "leave")
    ).all()
    return {
        "low_credits": low,
        "absent": absent,
        "makeup_pending": [
            scope.project(r)
            for r in leaves
            if scope.visible(r) and r.data["status"] == "approved"
        ],
    }


class SettlementInput(S.Strict):
    channel_id: str
    period: str = S.Field(pattern=r"^\d{4}-\d{2}$")


@router.get("/settlement-statements")
def settlement_statements(i: Identity = Depends(scoped)):
    permit(i, "finance.write")
    return i.session.exec(
        query(i.session, Settlement, i.tenant.id).order_by(Settlement.period.desc())
    ).all()


@router.post("/settlement-statements", status_code=201)
def close_settlement(body: SettlementInput, i: Identity = Depends(scoped)):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from decimal import ROUND_DOWN

    permit(i, "finance.write")
    writable(i)
    try:
        year, month = map(int, body.period.split("-"))
        start = datetime(year, month, 1, tzinfo=ZoneInfo("Asia/Shanghai"))
        end = datetime(
            year + (month == 12),
            1 if month == 12 else month + 1,
            1,
            tzinfo=ZoneInfo("Asia/Shanghai"),
        )
    except ValueError:
        fail("PERIOD_INVALID", "结算月份无效")
    if end > now():
        fail("PERIOD_NOT_CLOSED", "月份结束后才能生成固定结算单")
    channel = ref(i.session, i.tenant.id, body.channel_id, "channel")
    i.session.exec(
        query(i.session, Record, i.tenant.id)
        .where(Record.id == channel.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    prior = i.session.exec(
        query(i.session, Settlement, i.tenant.id).where(
            Settlement.channel_id == channel.id, Settlement.period == body.period
        )
    ).first()
    if prior:
        return prior
    orders = i.session.exec(
        query(i.session, Record, i.tenant.id).where(Record.kind == "order")
    ).all()
    entries = []
    for order in orders:
        if order.data.get("channel_id") != channel.id:
            continue
        ledger = i.session.exec(
            query(i.session, LedgerEntry, i.tenant.id).where(
                LedgerEntry.order_id == order.id,
                LedgerEntry.created_at >= start,
                LedgerEntry.created_at < end,
            )
        ).all()
        if not ledger:
            continue
        # Round each order's monthly net cash toward zero; later refunds appear as negative adjustments.
        net = sum(x.amount_fen for x in ledger)
        before = i.session.exec(
            query(i.session, LedgerEntry, i.tenant.id).where(
                LedgerEntry.order_id == order.id, LedgerEntry.created_at < start
            )
        ).all()
        previous_net = sum(x.amount_fen for x in before)
        commission = commission_for(order, previous_net + net) - commission_for(
            order, previous_net
        )
        entries.append(
            {
                "order_id": order.id,
                "order": order.data["name"],
                "ledger_ids": [x.id for x in ledger],
                "net_fen": net,
                "commission_bps": order.data["commission_bps"],
                "commission_fen": commission,
            }
        )
    statement = Settlement(
        tenant_id=i.tenant.id,
        channel_id=channel.id,
        period=body.period,
        amount_fen=sum(x["commission_fen"] for x in entries),
        entries=entries,
        actor_id=i.user.id,
    )
    i.session.add(statement)
    audit(
        i.session,
        i.tenant.id,
        i.user.id,
        "finance.settlement",
        statement.id,
        period=body.period,
    )
    i.session.commit()
    return statement


@router.get("/education/weekly-report")
def weekly_report(i: Identity = Depends(scoped)):
    permit(i, "education.read")
    from datetime import timedelta

    start = now() - timedelta(days=7)
    classes = i.session.exec(
        query(i.session, Record, i.tenant.id).where(Record.kind == "class")
    ).all()
    lessons = i.session.exec(
        query(i.session, Record, i.tenant.id).where(Record.kind == "lesson")
    ).all()
    credits = i.session.exec(
        query(i.session, CreditEntry, i.tenant.id).where(
            CreditEntry.kind == "attendance", CreditEntry.created_at >= start
        )
    ).all()
    scope = Scope(i)
    classes = [r for r in classes if scope.visible(r)]
    lessons = [r for r in lessons if scope.visible(r)]
    credits = [
        r
        for r in credits
        if r.enrollment_id in {e.id for e in scope.list("enrollment")}
    ]
    alerts = education_alerts(i)
    return {
        "from": start,
        "to": now(),
        "classes": [
            {
                "name": c.data["name"],
                "lessons_completed": sum(
                    l.data["class_id"] == c.id
                    and l.data["status"] == "completed"
                    and as_utc(
                        __import__("datetime").datetime.fromisoformat(
                            l.data["starts_at"]
                        )
                    )
                    >= start
                    for l in lessons
                ),
                "attendance_count": sum(
                    any(
                        l.id == a.lesson_id and l.data["class_id"] == c.id
                        for l in lessons
                    )
                    for a in credits
                ),
            }
            for c in classes
        ],
        "low_credits": alerts["low_credits"],
        "absent": alerts["absent"],
        "makeup_pending": alerts["makeup_pending"],
    }

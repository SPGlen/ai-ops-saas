import json, hashlib, re
from collections import Counter, defaultdict
from datetime import timedelta, datetime
from sqlalchemy import func, update
from sqlmodel import Session, select
from .models import *
from .schemas import RECORD_SCHEMAS
from .security import fail, encrypt, decrypt
from .auth import entitlement


def query(session, model, tenant_id):
    return select(model).where(model.tenant_id == tenant_id)


def lock_record(session, tenant_id, record_id):
    # A no-op write also serializes mutating operations in the SQLite preview.
    session.exec(
        update(Record)
        .where(Record.id == record_id, Record.tenant_id == tenant_id)
        .values(updated_at=Record.updated_at)
        .execution_options(synchronize_session=False)
    )
    return session.exec(
        query(session, Record, tenant_id)
        .where(Record.id == record_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()


def own(session, model, tenant_id, object_id):
    item = session.exec(
        query(session, model, tenant_id).where(model.id == object_id)
    ).first()
    if not item:
        fail("NOT_FOUND", "记录不存在", 404)
    return item


def audit(session, tenant_id, actor_id, action, target_id, **detail):
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            target_id=target_id,
            detail=detail,
        )
    )


def ref(session, tenant_id, object_id, kind):
    record = own(session, Record, tenant_id, object_id)
    if record.kind != kind:
        fail("REFERENCE_INVALID", "关联记录类型错误")
    return record


def balance(session, tenant_id, order_id):
    entries = session.exec(
        query(session, LedgerEntry, tenant_id).where(LedgerEntry.order_id == order_id)
    ).all()
    return sum(e.amount_fen for e in entries)


def credit_balance(session, tenant_id, enrollment_id):
    return session.exec(
        select(func.coalesce(func.sum(CreditEntry.delta), 0)).where(
            CreditEntry.tenant_id == tenant_id,
            CreditEntry.enrollment_id == enrollment_id,
        )
    ).one()


def plain_data(tenant_id, data):
    data = dict(data)
    if data.get("contact_cipher"):
        data["contact"] = decrypt(tenant_id, data.pop("contact_cipher"))
    if data.get("guardians_cipher"):
        data["guardians"] = json.loads(decrypt(tenant_id, data.pop("guardians_cipher")))
    for field in ("body", "resolution"):
        if data.get(field + "_cipher"):
            data[field] = decrypt(tenant_id, data.pop(field + "_cipher"))
    return data


def view_record(session, record):
    data = plain_data(record.tenant_id, record.data)
    if record.kind == "order":
        data["paid_fen"] = balance(session, record.tenant_id, record.id)
        data["due_fen"] = data.get("price_fen", 0) - data.get("discount_fen", 0)
    if record.kind == "enrollment":
        data["name"] = (
            ref(session, record.tenant_id, data["student_id"], "student").data["name"]
            + " · "
            + (
                data.get("program_name")
                or (
                    ref(session, record.tenant_id, data["course_id"], "course").data[
                        "name"
                    ]
                    if data.get("course_id")
                    else "报名"
                )
            )
        )
        data["remaining"] = credit_balance(session, record.tenant_id, record.id)
    return {
        "id": record.id,
        "kind": record.kind,
        "data": data,
        "version": record.version,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def create_record(session, tenant_id, actor_id, kind, values):
    if kind not in RECORD_SCHEMAS:
        fail("KIND_INVALID", "不支持的记录类型")
    data = RECORD_SCHEMAS[kind].model_validate(values).model_dump(mode="json")
    from .operations import prepare

    data = prepare(session, tenant_id, actor_id, kind, data)
    for name, target in [
        ("student_id", "student"),
        ("course_id", "course"),
        ("class_id", "class"),
        ("lesson_id", "lesson"),
        ("order_id", "order"),
        ("channel_id", "channel"),
        ("enrollment_id", "enrollment"),
        ("makeup_lesson_id", "lesson"),
    ]:
        if data.get(name):
            ref(session, tenant_id, data[name], target)
    if data.get("owner_id") or data.get("teacher_id"):
        user_id = data.get("owner_id") or data.get("teacher_id")
        if not session.exec(
            select(Membership).where(
                Membership.tenant_id == tenant_id, Membership.user_id == user_id
            )
        ).first():
            fail("REFERENCE_INVALID", "负责人不属于当前机构")
    if kind == "expense" and data.get("asset_id"):
        own(session, Asset, tenant_id, data["asset_id"])
    if kind == "order":
        if data.get("course_id"):
            course = ref(session, tenant_id, data["course_id"], "course")
            data["price_fen"] = course.data["price_fen"]
            data["course_lessons"] = course.data["lessons"]
            data["program_name"] = course.data["name"]
            data["purchased_units"] = course.data["lessons"]
        if data["discount_fen"] > data["price_fen"]:
            fail("DISCOUNT_INVALID", "优惠不能超过课程原价")
        if data.get("channel_id"):
            channel = ref(session, tenant_id, data["channel_id"], "channel")
            if not channel.data["confirmed"]:
                fail("COMMISSION_UNCONFIRMED", "请先确认渠道结算规则")
            if (
                channel.data.get("effective_from")
                and as_utc(datetime.fromisoformat(channel.data["effective_from"]))
                > now()
            ):
                fail("CHANNEL_NOT_EFFECTIVE", "渠道规则尚未生效")
            data["commission_bps"] = channel.data["commission_bps"]
            data["commission_basis"] = channel.data.get("basis", "net_cash")
            data["commission_deduction_fen"] = channel.data.get("deduction_fen", 0)
        else:
            data["commission_bps"] = 0
    if data.get("contact"):
        data["contact_cipher"] = encrypt(tenant_id, data.pop("contact"))
    if kind == "enrollment" and data.get("order_id"):
        existing = session.exec(
            query(session, Record, tenant_id).where(Record.kind == "enrollment")
        ).all()
        if any(e.data.get("order_id") == data["order_id"] for e in existing):
            fail("ENROLLMENT_EXISTS", "该订单已开通课时", 409)
    record = Record(tenant_id=tenant_id, kind=kind, data=data, created_by=actor_id)
    session.add(record)
    session.flush()
    if kind == "enrollment":
        course = (
            ref(session, tenant_id, data["course_id"], "course")
            if data.get("course_id")
            else None
        )
        if data.get("class_id"):
            cls = ref(session, tenant_id, data["class_id"], "class")
            session.exec(
                query(session, Record, tenant_id)
                .where(Record.id == cls.id)
                .execution_options(populate_existing=True)
                .with_for_update()
            ).first()
            enrolled = session.exec(
                query(session, Record, tenant_id).where(Record.kind == "enrollment")
            ).all()
            if (
                len(
                    {
                        x.data["student_id"]
                        for x in enrolled
                        if x.data.get("class_id") == cls.id
                        and x.data.get("status", "active") == "active"
                    }
                )
                > cls.data["capacity"]
            ):
                fail("CLASS_FULL", "班级已满，请选择其他班级")
            if (
                course
                and cls.data.get("course_id")
                and cls.data["course_id"] != course.id
            ):
                fail("COURSE_MISMATCH", "班级与报名课程不一致")
        if not data.get("order_id"):
            fail("PAYMENT_REQUIRED", "请关联已收款订单后开通课时")
        order = ref(session, tenant_id, data["order_id"], "order")
        session.exec(
            query(session, Record, tenant_id)
            .where(Record.id == order.id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).first()
        if order.data["student_id"] != data["student_id"] or (
            data.get("course_id") and order.data.get("course_id") != data["course_id"]
        ):
            fail("ORDER_MISMATCH", "订单与学员课程不匹配")
        if (
            balance(session, tenant_id, order.id)
            < order.data["price_fen"] - order.data["discount_fen"]
        ):
            fail("PAYMENT_REQUIRED", "订单尚未付清")
        existing = session.exec(
            query(session, Record, tenant_id).where(Record.kind == "enrollment")
        ).all()
        if any(
            x.id != record.id and x.data.get("order_id") == order.id for x in existing
        ):
            fail("ENROLLMENT_EXISTS", "该订单已开通课时", 409)
        session.add(
            CreditEntry(
                tenant_id=tenant_id,
                enrollment_id=record.id,
                delta=order.data["course_lessons"],
                kind="grant",
                request_id="grant:" + order.id,
                actor_id=actor_id,
            )
        )
    if kind == "leave":
        validate_leave(session, tenant_id, data)
    if kind == "knowledge":
        update_knowledge(session, record)
    from .operations import after_record

    after_record(session, record, actor_id)
    audit(session, tenant_id, actor_id, "record.create", record.id, kind=kind)
    return record


def update_knowledge(session, record):
    old = session.exec(
        query(session, KnowledgeChunk, record.tenant_id).where(
            KnowledgeChunk.record_id == record.id
        )
    ).all()
    for chunk in old:
        session.delete(chunk)
    if record.data.get("approved"):
        body = record.data["body"]
        for i in range(0, len(body), 1000):
            session.add(
                KnowledgeChunk(
                    tenant_id=record.tenant_id,
                    record_id=record.id,
                    title=record.data["name"],
                    body=body[i : i + 1200],
                    version=record.version,
                )
            )


def update_record(session, tenant_id, actor_id, record_id, values, version):
    record = own(session, Record, tenant_id, record_id)
    session.exec(
        query(session, Record, tenant_id)
        .where(Record.id == record_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    session.refresh(record)
    if version != record.version:
        fail("VERSION_CONFLICT", "记录已更新，请刷新后重试", 409)
    if record.kind == "enrollment":
        fail("IMMUTABLE_ENROLLMENT", "报名课时请通过调整操作维护")
    if (
        record.kind == "order"
        and session.exec(
            query(session, LedgerEntry, tenant_id).where(
                LedgerEntry.order_id == record.id
            )
        ).first()
    ):
        fail("PAID_ORDER_LOCKED", "已收款订单请通过退款或冲正调整")
    schema = RECORD_SCHEMAS[record.kind]
    merged = {
        k: v
        for k, v in plain_data(tenant_id, record.data).items()
        if k in schema.model_fields
    }
    data = schema.model_validate({**merged, **values}).model_dump(mode="json")
    from .operations import prepare

    data = prepare(session, tenant_id, actor_id, record.kind, data, record)
    for name, target in [
        ("student_id", "student"),
        ("course_id", "course"),
        ("class_id", "class"),
        ("lesson_id", "lesson"),
        ("channel_id", "channel"),
        ("enrollment_id", "enrollment"),
        ("makeup_lesson_id", "lesson"),
    ]:
        if data.get(name):
            ref(session, tenant_id, data[name], target)
    if record.kind == "order":
        if data.get("course_id"):
            course = ref(session, tenant_id, data["course_id"], "course")
            data["price_fen"] = course.data["price_fen"]
            data["course_lessons"] = course.data["lessons"]
            data["program_name"] = course.data["name"]
            data["purchased_units"] = course.data["lessons"]
        if data["discount_fen"] > data["price_fen"]:
            fail("DISCOUNT_INVALID", "优惠超过原价")
        channel = (
            ref(session, tenant_id, data["channel_id"], "channel")
            if data.get("channel_id")
            else None
        )
        if channel and not channel.data["confirmed"]:
            fail("COMMISSION_UNCONFIRMED", "请确认分润规则")
        if (
            channel
            and channel.data.get("effective_from")
            and as_utc(datetime.fromisoformat(channel.data["effective_from"])) > now()
        ):
            fail("CHANNEL_NOT_EFFECTIVE", "渠道规则尚未生效")
        data["commission_bps"] = channel.data["commission_bps"] if channel else 0
        data["commission_basis"] = (
            channel.data.get("basis", "net_cash") if channel else "net_cash"
        )
        data["commission_deduction_fen"] = (
            channel.data.get("deduction_fen", 0) if channel else 0
        )
    for name in ("owner_id", "teacher_id"):
        if (
            data.get(name)
            and not session.exec(
                select(Membership).where(
                    Membership.tenant_id == tenant_id, Membership.user_id == data[name]
                )
            ).first()
        ):
            fail(
                "REFERENCE_INVALID",
                "Responsible member must belong to the organization",
            )
    if record.kind == "expense" and data.get("asset_id"):
        own(session, Asset, tenant_id, data["asset_id"])
    if data.get("contact"):
        data["contact_cipher"] = encrypt(tenant_id, data.pop("contact"))
    if record.kind == "leave":
        validate_leave(session, tenant_id, data)
    previous = dict(record.data)
    changed = session.exec(
        update(Record)
        .where(
            Record.id == record.id,
            Record.tenant_id == tenant_id,
            Record.version == version,
        )
        .values(data=data, version=version + 1, updated_at=now())
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        fail("VERSION_CONFLICT", "记录已更新，请刷新后重试", 409)
    session.refresh(record)
    if record.kind == "knowledge":
        update_knowledge(session, record)
    if (
        record.kind == "lesson"
        and previous.get("status") != "cancelled"
        and data["status"] == "cancelled"
    ):
        charges = session.exec(
            query(session, CreditEntry, tenant_id).where(
                CreditEntry.lesson_id == record.id, CreditEntry.kind == "attendance"
            )
        ).all()
        for charge in charges:
            if not session.exec(
                query(session, CreditEntry, tenant_id).where(
                    CreditEntry.reverses_id == charge.id
                )
            ).first():
                session.add(
                    CreditEntry(
                        tenant_id=tenant_id,
                        enrollment_id=charge.enrollment_id,
                        lesson_id=record.id,
                        delta=1,
                        kind="reversal",
                        request_id="cancel:" + charge.id,
                        reverses_id=charge.id,
                        actor_id=actor_id,
                    )
                )
    from .operations import after_record

    after_record(session, record, actor_id, previous)
    audit(
        session,
        tenant_id,
        actor_id,
        "record.update",
        record.id,
        kind=record.kind,
        version=record.version,
    )
    return record


def record_money(
    session, tenant_id, actor_id, order_id, kind, amount, request_id, note=""
):
    order = own(session, Record, tenant_id, order_id)
    if order.kind != "order":
        fail("ORDER_REQUIRED", "需要订单记录")
    lock_record(session, tenant_id, order_id)
    session.exec(
        query(session, Record, tenant_id)
        .where(Record.id == order_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    previous = session.exec(
        query(session, LedgerEntry, tenant_id).where(
            LedgerEntry.request_id == request_id
        )
    ).first()
    signed = amount if kind == "payment" else -amount
    if previous:
        if (
            previous.order_id != order_id
            or previous.amount_fen != signed
            or previous.entry_type != kind
        ):
            fail("IDEMPOTENCY_CONFLICT", "请求编号已用于其他操作", 409)
        return previous
    net = balance(session, tenant_id, order_id)
    due = order.data["price_fen"] - order.data["discount_fen"]
    if kind == "payment" and net + amount > due:
        fail("OVERPAYMENT", "收款超过订单应收金额")
    if kind == "refund" and amount > net:
        fail("OVER_REFUND", "退款超过当前净收款")
    entry = LedgerEntry(
        tenant_id=tenant_id,
        order_id=order_id,
        entry_type=kind,
        amount_fen=signed,
        request_id=request_id,
        note=note,
        actor_id=actor_id,
    )
    session.add(entry)
    from .operations import event

    event(
        session,
        tenant_id,
        actor_id,
        "finance." + kind,
        order_id,
        {"amount_fen": signed},
    )
    audit(session, tenant_id, actor_id, "finance." + kind, order_id, amount_fen=signed)
    return entry


def reverse_money(session, tenant_id, actor_id, entry_id, request_id):
    entry = own(session, LedgerEntry, tenant_id, entry_id)
    order = own(session, Record, tenant_id, entry.order_id)
    lock_record(session, tenant_id, order.id)
    session.exec(
        query(session, Record, tenant_id)
        .where(Record.id == order.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    existing = session.exec(
        query(session, LedgerEntry, tenant_id).where(
            LedgerEntry.reverses_id == entry.id
        )
    ).first()
    if existing:
        return existing
    net = balance(session, tenant_id, order.id) - entry.amount_fen
    if net < 0 or net > order.data["price_fen"] - order.data["discount_fen"]:
        fail("REVERSAL_INVALID", "冲正会导致订单金额异常，请先处理相关退款")
    reversal = LedgerEntry(
        tenant_id=tenant_id,
        order_id=entry.order_id,
        entry_type="reversal",
        amount_fen=-entry.amount_fen,
        reverses_id=entry.id,
        request_id=request_id,
        note="冲正原流水",
        actor_id=actor_id,
    )
    session.add(reversal)
    from .operations import event

    event(
        session,
        tenant_id,
        actor_id,
        "finance.reverse",
        entry.order_id,
        {"entry_id": entry.id},
    )
    audit(session, tenant_id, actor_id, "finance.reverse", entry.id)
    return reversal


def attend(session, tenant_id, actor_id, enrollment_id, lesson_id, request_id):
    enrollment = ref(session, tenant_id, enrollment_id, "enrollment")
    lock_record(session, tenant_id, enrollment_id)
    if enrollment.data.get("status", "active") != "active":
        fail("ENROLLMENT_CLOSED", "报名已结束，不能签到")
    from .operations import capture_rosters

    capture_rosters(session, tenant_id)
    session.exec(
        query(session, Record, tenant_id)
        .where(Record.id == enrollment_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    lesson = ref(session, tenant_id, lesson_id, "lesson")
    if enrollment.data.get("order_id"):
        order = ref(session, tenant_id, enrollment.data["order_id"], "order")
        if (
            order.data["price_fen"] - order.data["discount_fen"] > 0
            and balance(session, tenant_id, order.id) <= 0
        ):
            fail("ENROLLMENT_REFUNDED", "订单已全额退款，课时账户暂停签到")
    if lesson.data["status"] == "cancelled":
        fail("LESSON_CANCELLED", "课程已取消")
    if enrollment.data.get("class_id") != lesson.data["class_id"]:
        fail("CLASS_MISMATCH", "学员不属于该班级")
    student_id = enrollment.data["student_id"]
    session.exec(
        query(session, Record, tenant_id)
        .where(Record.id == student_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    accounts = session.exec(
        query(session, Record, tenant_id).where(Record.kind == "enrollment")
    ).all()
    ids = [r.id for r in accounts if r.data["student_id"] == student_id]
    prior = session.exec(
        query(session, CreditEntry, tenant_id).where(
            CreditEntry.enrollment_id.in_(ids),
            CreditEntry.lesson_id == lesson_id,
            CreditEntry.kind == "attendance",
        )
    ).first()
    if prior:
        return prior
    leaves = session.exec(
        query(session, Record, tenant_id).where(Record.kind == "leave")
    ).all()
    if any(
        x.data["enrollment_id"] == enrollment_id
        and x.data["lesson_id"] == lesson_id
        and x.data["status"] == "approved"
        for x in leaves
    ):
        fail("ON_LEAVE", "Approved leave cannot be charged")
    if credit_balance(session, tenant_id, enrollment_id) < 1:
        fail("CREDITS_EMPTY", "剩余课时不足")
    entry = CreditEntry(
        tenant_id=tenant_id,
        enrollment_id=enrollment_id,
        student_id=student_id,
        lesson_id=lesson_id,
        delta=-1,
        kind="attendance",
        request_id=request_id,
        actor_id=actor_id,
    )
    session.add(entry)
    audit(
        session,
        tenant_id,
        actor_id,
        "education.attend",
        enrollment_id,
        lesson_id=lesson_id,
    )
    return entry


def reserve(session, tenant_id, request_id, resource, units, funding="platform"):
    tenant = session.exec(
        select(Tenant)
        .where(Tenant.id == tenant_id)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).one()
    if not entitlement(session, tenant)["active"]:
        fail("ENTITLEMENT_EXPIRED", "使用期已结束", 402)
    if units < 0:
        fail("USAGE_INVALID", "用量不能为负数")
    previous = session.exec(
        query(session, UsageRecord, tenant_id).where(
            UsageRecord.request_id == request_id, UsageRecord.resource == resource
        )
    ).first()
    if previous:
        if previous.funding != funding or previous.reserved != units:
            fail(
                "IDEMPOTENCY_CONFLICT",
                "Usage reservation has different parameters",
                409,
            )
        return previous
    period = now().strftime("%Y-%m")
    if funding == "platform":
        quota = int(tenant.settings.get("quotas", {}).get(resource, 0))
        bucket = session.exec(
            query(session, BudgetBucket, tenant_id)
            .where(BudgetBucket.period == period, BudgetBucket.resource == resource)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).first()
        if not bucket:
            bucket = BudgetBucket(tenant_id=tenant_id, resource=resource, period=period)
        if bucket.used + bucket.reserved + units > quota:
            fail("QUOTA_EXCEEDED", "平台额度不足，请增加额度或主动切换自带 Key", 402)
        bucket.reserved += units
        session.add(bucket)
    usage = UsageRecord(
        tenant_id=tenant_id,
        request_id=request_id,
        resource=resource,
        funding=funding,
        reserved=units,
        period=period,
    )
    session.add(usage)
    session.flush()
    return usage


def settle(session, tenant_id, request_id, resource, actual, cost_fen=0):
    usage = session.exec(
        query(session, UsageRecord, tenant_id)
        .where(UsageRecord.request_id == request_id, UsageRecord.resource == resource)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    if not usage or usage.state != "reserved":
        return
    actual = max(0, int(actual))
    if usage.funding == "platform":
        bucket = session.exec(
            query(session, BudgetBucket, tenant_id)
            .where(
                BudgetBucket.period == usage.period, BudgetBucket.resource == resource
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        ).one()
        bucket.reserved -= usage.reserved
        bucket.used += actual
        session.add(bucket)
    usage.actual = actual
    usage.cost_fen = cost_fen
    usage.state = "settled"
    usage.updated_at = now()
    session.add(usage)
    charge = session.exec(query(session, MatrixCharge, tenant_id).where(MatrixCharge.request_id == request_id, MatrixCharge.resource == resource)).first()
    if charge:
        charge.actual_fen = cost_fen
        charge.state = "settled"
        session.add(charge)


def record_consumption(session, tenant_id, request_id, resource, units, additive=False):
    usage = session.exec(
        query(session, UsageRecord, tenant_id)
        .where(UsageRecord.request_id == request_id, UsageRecord.resource == resource)
        .execution_options(populate_existing=True)
        .with_for_update()
    ).first()
    if not usage or usage.state != "reserved":
        return
    if units is None:
        units = 20000
        usage.estimated = True
    usage.actual = usage.actual + units if additive else max(usage.actual, units)
    session.add(usage)


def release_reservations(session, tenant_id, request_id):
    import math

    records = session.exec(
        query(session, UsageRecord, tenant_id).where(
            UsageRecord.request_id == request_id
        )
    ).all()
    cost = 0
    for record in records:
        if record.resource == "cost_fen":
            continue
        from .model_router import actual_cost
        amount = actual_cost(record)
        cost += amount
        if record.state == "reserved":
            settle(
                session, tenant_id, request_id, record.resource, record.actual, amount
            )
    settle(session, tenant_id, request_id, "cost_fen", cost)


def content_hash(title, body, assets):
    return hashlib.sha256(
        json.dumps(
            {"title": title, "body": body, "assets": assets},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def policy_notes(session, tenant_id, title, body, assets):
    notes = []
    if len(title) > 20:
        notes.append("发布标题超过20字符，请缩短")
    if len(body) > 1000:
        notes.append("正文超过通用发布限长1000字符，请缩短")
    text = title + body
    for phrase in (
        "保获奖",
        "保证获奖",
        "保证提分",
        "智力预测",
        "天赋排名",
        "教育厅指定",
        "官方保送",
    ):
        if phrase in text:
            notes.append("宣传表述需要核实：" + phrase)
    if re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", text):
        notes.append("正文含疑似个人手机号")
    courses = session.exec(
        query(session, Record, tenant_id).where(Record.kind == "course")
    ).all()
    for course in courses:
        if course.data.get("approved") and course.data["name"] in text:
            prices = re.findall(r"(\d+(?:\.\d{1,2})?)\s*元", text)
            if any(
                len(value) > 12 or round(float(value) * 100) != course.data["price_fen"]
                for value in prices
            ):
                notes.append("课程价格与当前确认资料不一致：" + course.data["name"])
    confirmed = session.exec(
        query(session, Record, tenant_id).where(
            Record.kind.in_(["knowledge", "course"])
        )
    ).all()
    counts = {
        r.data["lessons"]
        for r in confirmed
        if r.kind == "course" and r.data.get("approved")
    }
    for r in confirmed:
        if r.kind == "knowledge" and r.data.get("approved"):
            counts.update(
                int(x)
                for x in re.findall(
                    r"(\d{1,4})\s*(?:节课|次课程|次课)", r.data.get("body", "")
                )
            )
    claims = re.findall(r"(\d{1,4})\s*(?:节课|次课程|次课)", text)
    if counts and any(int(x) not in counts for x in claims):
        notes.append("课程次数未在已确认资料中出现，请核对")
    for asset_id in assets:
        asset = own(session, Asset, tenant_id, asset_id)
        if not asset.consent:
            notes.append("素材尚未确认使用授权：" + asset.name)
    return notes


def save_content(session, tenant_id, actor_id, values, content_id=None):
    data = values
    for asset_id in data.assets:
        asset = own(session, Asset, tenant_id, asset_id)
        if "/content/" not in asset.object_key:
            fail(
                "ASSET_PURPOSE_INVALID",
                "只有发布素材可以关联内容，票据和内部文件不能用于发布",
                403,
            )
    if data.form == "image_text" and len(data.assets) > 8:
        fail("ASSET_LIMIT", "图文成品最多8张卡片")
    if content_id:
        content = own(session, Content, tenant_id, content_id)
        session.exec(
            query(session, Content, tenant_id)
            .where(Content.id == content_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).first()
        session.refresh(content)
        if data.version != content.current_version:
            fail("VERSION_CONFLICT", "内容已更新", 409)
        if data.form != content.form:
            fail("FORM_IMMUTABLE", "内容形式不同，请新建作品以保留各版本评分依据")
        content.current_version += 1
        content.title = data.title
        content.status = "draft"
    else:
        content = Content(
            tenant_id=tenant_id, title=data.title, form=data.form, created_by=actor_id
        )
    session.add(content)
    session.flush()
    notes = policy_notes(session, tenant_id, data.title, data.body, data.assets)
    version = ContentVersion(
        tenant_id=tenant_id,
        content_id=content.id,
        version=content.current_version,
        title=data.title,
        body=data.body,
        assets=data.assets,
        content_hash=content_hash(data.title, data.body, data.assets),
        policy_checked=not notes,
        policy_notes=notes,
    )
    session.add(version)
    audit(
        session,
        tenant_id,
        actor_id,
        "content.version",
        content.id,
        version=content.current_version,
    )
    return content, version


def summary(session, tenant_id):
    records = session.exec(query(session, Record, tenant_id)).all()
    counts = Counter(r.kind for r in records)
    ledger = session.exec(query(session, LedgerEntry, tenant_id)).all()
    net = sum(e.amount_fen for e in ledger)
    expenses = sum(
        r.data["amount_fen"]
        for r in records
        if r.kind == "expense" and r.data["status"] == "confirmed"
    )
    leads = [r for r in records if r.kind == "lead"]
    chart = []
    for i in range(13, -1, -1):
        day = (now() - timedelta(days=i)).date()
        chart.append(
            {
                "date": day.isoformat()[5:],
                "leads": sum(r.created_at.date() == day for r in leads),
                "revenue": sum(
                    e.amount_fen for e in ledger if e.created_at.date() == day
                )
                / 100,
            }
        )
    jobs = session.exec(query(session, PublishJob, tenant_id)).all()
    commission = sum(
        commission_for(r, balance(session, tenant_id, r.id))
        for r in records
        if r.kind == "order"
    )
    return {
        "counts": dict(counts),
        "net_revenue_fen": net,
        "expense_fen": expenses,
        "commission_fen": commission,
        "published": sum(j.status == "succeeded" for j in jobs),
        "pending_jobs": sum(j.status not in ("succeeded", "cancelled") for j in jobs),
        "chart": chart,
        "followups": [
            view_record(session, r)
            for r in leads
            if r.data.get("stage") not in ("won", "lost") and r.data.get("followup_at")
        ][:6],
    }


def validate_leave(session, tenant_id, data):
    enrollment = ref(session, tenant_id, data["enrollment_id"], "enrollment")
    lesson = ref(session, tenant_id, data["lesson_id"], "lesson")
    if enrollment.data.get("class_id") != lesson.data["class_id"]:
        fail("CLASS_MISMATCH", "Leave lesson must belong to the enrolled class")
    charged = session.exec(
        query(session, CreditEntry, tenant_id).where(
            CreditEntry.enrollment_id == enrollment.id,
            CreditEntry.lesson_id == lesson.id,
            CreditEntry.kind == "attendance",
        )
    ).first()
    if charged and data["status"] == "approved":
        fail(
            "ATTENDANCE_EXISTS",
            "Already attended; reverse attendance before approving leave",
        )
    if data.get("makeup_lesson_id"):
        makeup = ref(session, tenant_id, data["makeup_lesson_id"], "lesson")
        if makeup.data["class_id"] != lesson.data["class_id"] or makeup.id == lesson.id:
            fail("MAKEUP_INVALID", "Choose another lesson from the same class")
    if data["status"] == "made_up":
        if not data.get("makeup_lesson_id"):
            fail("MAKEUP_REQUIRED", "Makeup lesson required")
        attendance = session.exec(
            query(session, CreditEntry, tenant_id).where(
                CreditEntry.enrollment_id == enrollment.id,
                CreditEntry.lesson_id == data["makeup_lesson_id"],
                CreditEntry.kind == "attendance",
            )
        ).first()
        if not attendance:
            fail(
                "MAKEUP_ATTENDANCE_REQUIRED",
                "Record makeup attendance before completing the leave",
            )


def commission_for(order, net):
    deduction = (
        order.data.get("commission_deduction_fen", 0)
        if order.data.get("commission_basis") == "after_fixed_cost"
        else 0
    )
    return max(0, net - deduction) * order.data.get("commission_bps", 0) // 10000

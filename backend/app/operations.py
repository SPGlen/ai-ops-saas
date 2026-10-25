"""Institution operations: durable events, historical enrollment, KPI and refunds."""

import json, hashlib
from datetime import datetime, timedelta
from sqlmodel import select
from sqlalchemy import update
from .models import *
from .domain import query, own, ref, balance, credit_balance, audit, plain_data
from .security import fail, encrypt, decrypt
from .permissions import Scope, has, permit, identity_for

DEFAULT_OPS = {
    "feedback_hours": 24,
    "timezone": "Asia/Shanghai",
    "week_day": 0,
    "week_hour": 9,
    "month_day": 1,
    "month_hour": 9,
    "baseline_confirmed": False,
    "rules": [
        {
            "id": "attrition",
            "metric": "attrition_rate",
            "threshold": 30,
            "direction": "gte",
            "class_id": "",
        }
    ],
}


def options(t):
    return {**DEFAULT_OPS, **t.settings.get("operations", {})}


def enabled(t):
    return bool(t.settings.get("consultation_enabled", False))


def consultation(t):
    if not enabled(t):
        fail("FEATURE_PAUSED", "咨询接待本期暂停，历史资料保留", 403)


def dt(value):
    return (
        as_utc(datetime.fromisoformat(value))
        if isinstance(value, str)
        else as_utc(value)
    )


def event(s, t, actor, kind, rid, payload=None, at=None, key=None):
    row = BusinessEvent(
        tenant_id=t,
        actor_id=actor,
        kind=kind,
        record_id=rid,
        payload=json.loads(
            json.dumps(
                payload or {},
                default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x),
            )
        ),
        occurred_at=at or now(),
        request_id=key or uid(),
    )
    s.add(row)
    s.flush()
    return row


def prepare(s, t, actor, kind, data, old=None):
    if kind == "order" and not data.get("course_id"):
        data["program_name"] = data.get("program_name") or data.get("name", "报名")
        data["course_lessons"] = data.get("purchased_units", 8)
    if kind == "lead":
        if data.get("stage") == "lost" and not data.get("loss_reason", "").strip():
            fail("REASON_REQUIRED", "请填写未成交原因")
        if data.get("stage") == "won" and not (old and old.data.get("won_at")):
            fail("ENROLLMENT_REQUIRED", "正式报名由缴清学费并开通课时确认")
    if old:
        for k in (
            "lost_at",
            "won_at",
            "first_attended_at",
            "effective_at",
            "lead_id",
            "program_name",
            "history_calibrated",
            "history",
            "status",
            "started_at",
            "ended_at",
            "withdrawal_reason",
            "kpi_eligible",
            "external_row_id",
            "import_batch_id",
        ):
            if k in old.data and k not in data:
                data[k] = old.data[k]
    if kind == "family_feedback":
        recorded = dt(data["recorded_at"]) if data.get("recorded_at") else now()
        if recorded > now() + timedelta(minutes=5):
            fail("FEEDBACK_DATE_INVALID", "反馈时间不能在未来")
        data["recorded_at"] = recorded.isoformat()
        if data.get("status") == "resolved" and not data.get("resolution", "").strip():
            fail("REASON_REQUIRED", "请填写反馈处理结果")
        for field in ("body", "resolution"):
            value = data.pop(field, "")
            data[field + "_cipher"] = encrypt(t, value)
    guardians = data.pop("guardians", None)
    if guardians:
        data["guardians_cipher"] = encrypt(t, json.dumps(guardians, ensure_ascii=False))
        data["guardian"] = guardians[0]["name"]
        data["contact"] = guardians[0].get("contact", "")
    elif old and old.data.get("guardians_cipher"):
        data["guardians_cipher"] = old.data["guardians_cipher"]
    return data


def after_record(s, r, actor, previous=None):
    data = dict(r.data)
    kind = r.kind
    if kind == "enrollment" and not previous:
        order = ref(s, r.tenant_id, data["order_id"], "order")
        started = now().isoformat()
        data.update(
            status="active",
            program_name=order.data.get("program_name", order.data.get("name", "报名")),
            started_at=started,
            history_calibrated=True,
            history=[
                {"class_id": data.get("class_id", ""), "start": started, "end": None}
            ],
        )
        r.data = data
        s.add(r)
        event(
            s,
            r.tenant_id,
            actor,
            "enrollment.started",
            r.id,
            {
                "student_id": data["student_id"],
                "class_id": data.get("class_id", ""),
                "order_id": order.id,
                "lead_id": order.data.get("lead_id", ""),
            },
        )
        lid = order.data.get("lead_id")
        if lid and not ref(s, r.tenant_id, lid, "lead").data.get("won_at"):
            lead = ref(s, r.tenant_id, lid, "lead")
            lead.data = {**lead.data, "stage": "won", "won_at": started}
            lead.version += 1
            lead.updated_at = now()
            s.add(lead)
            event(
                s,
                r.tenant_id,
                actor,
                "lead.won",
                lead.id,
                {"student_id": data["student_id"]},
                key="lead-won:" + lead.id,
            )
    if (
        kind == "lead"
        and data.get("stage") == "lost"
        and (previous is None or previous.get("stage") != "lost")
    ):
        data["lost_at"] = now().isoformat()
        r.data = data
        s.add(r)
    if (
        kind == "lead"
        and data.get("stage") == "attended"
        and not data.get("first_attended_at")
    ):
        data["first_attended_at"] = now().isoformat()
        r.data = data
        s.add(r)
        event(s, r.tenant_id, actor, "lead.attended", r.id)
    if kind == "expense" and previous is not None:
        fields = ("amount_fen", "date", "category", "status", "asset_id")
        event(
            s,
            r.tenant_id,
            actor,
            "expense.revised",
            r.id,
            {
                "before": {k: previous.get(k) for k in fields},
                "after": {k: data.get(k) for k in fields},
            },
        )
    event(
        s,
        r.tenant_id,
        actor,
        "record." + ("updated" if previous is not None else "created"),
        r.id,
        {"kind": kind, "version": r.version},
    )
    if kind == "lesson":
        if previous is None or previous.get("status") != data.get("status"):
            r.data = {**r.data, "kpi_eligible": True}
            s.add(r)
        capture_rosters(s, r.tenant_id)


def class_at(e, when):
    history = e.data.get("history", [])
    if not history:
        return (
            e.data.get("class_id", "")
            if e.data.get("history_calibrated")
            and dt(e.data.get("started_at", e.created_at)) <= when
            else None
        )
    for h in history:
        if dt(h["start"]) <= when and (not h.get("end") or when < dt(h["end"])):
            return h["class_id"]
    return None


def capture_rosters(s, t):
    rows = s.exec(query(s, Record, t)).all()
    classes = {r.id: r for r in rows if r.kind == "class"}
    enroll = [r for r in rows if r.kind == "enrollment"]
    existing = {
        (r.lesson_id, r.enrollment_id) for r in s.exec(query(s, LessonRoster, t)).all()
    }
    roster_students = {
        (r.lesson_id, r.student_id) for r in s.exec(query(s, LessonRoster, t)).all()
    }
    kpis = {r.lesson_id for r in s.exec(query(s, FeedbackKPI, t)).all()}
    tenant = s.get(Tenant, t)
    for lesson in [r for r in rows if r.kind == "lesson"]:
        starts = dt(lesson.data["starts_at"])
        cls = classes.get(lesson.data["class_id"])
        if not cls or starts > now() or lesson.data.get("status") == "cancelled":
            continue
        for en in enroll:
            if (
                (lesson.id, en.data["student_id"]) not in roster_students
                and (lesson.id, en.id) not in existing
                and class_at(en, starts) == cls.id
            ):
                s.add(
                    LessonRoster(
                        tenant_id=t,
                        lesson_id=lesson.id,
                        class_id=cls.id,
                        teacher_id=cls.data.get("teacher_id", ""),
                        student_id=en.data["student_id"],
                        enrollment_id=en.id,
                        starts_at=starts,
                    )
                )
                existing.add((lesson.id, en.id))
                roster_students.add((lesson.id, en.data["student_id"]))
        end = starts + timedelta(minutes=lesson.data.get("duration_minutes", 90))
        if (
            lesson.data.get("kpi_eligible")
            and end <= now()
            and lesson.id not in kpis
            and cls.data.get("teacher_id")
        ):
            s.add(
                FeedbackKPI(
                    tenant_id=t,
                    lesson_id=lesson.id,
                    class_id=cls.id,
                    teacher_id=cls.data["teacher_id"],
                    due_at=end + timedelta(hours=options(tenant)["feedback_hours"]),
                )
            )
            kpis.add(lesson.id)
    s.flush()


def kpi_rows(i):
    permit(i, "education.read")
    capture_rosters(i.session, i.tenant.id)
    cancelled = {
        r.id
        for r in Scope(i).rows.values()
        if r.kind == "lesson" and r.data.get("status") == "cancelled"
    }
    rows = i.session.exec(query(i.session, FeedbackKPI, i.tenant.id)).all()
    return [
        x
        for x in rows
        if x.lesson_id not in cancelled
        and (
            "owner" in i.roles
            or "academic_admin" in i.roles
            or x.teacher_id == i.user.id
        )
    ]


def set_kpi(i, kid, completed, version, note):
    rows = {x.id: x for x in kpi_rows(i)}
    r = rows.get(kid)
    if not r:
        fail("NOT_FOUND", "课返考核不在负责范围内", 404)
    if r.version != version:
        fail("VERSION_CONFLICT", "记录已更新", 409)
    if r.teacher_id != i.user.id and not i.roles & {"owner", "academic_admin"}:
        fail("ROLE_FORBIDDEN", "只能确认自己的课返", 403)
    if (not completed or r.teacher_id != i.user.id) and not note.strip():
        fail("REASON_REQUIRED", "纠正记录需要填写原因")
    if not completed and not i.roles & {"owner", "academic_admin"}:
        fail("ROLE_FORBIDDEN", "撤销完成请联系教务", 403)
    lesson = ref(i.session, i.tenant.id, r.lesson_id, "lesson")
    if lesson.data["status"] == "cancelled":
        fail("LESSON_CANCELLED", "已取消课程不考核")
    if completed and r.completed_at is not None:
        return r
    changed = i.session.exec(
        update(FeedbackKPI)
        .where(
            FeedbackKPI.tenant_id == i.tenant.id,
            FeedbackKPI.id == r.id,
            FeedbackKPI.version == version,
        )
        .values(
            completed_at=now() if completed else None, notes=note, version=version + 1
        )
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        fail("VERSION_CONFLICT", "考核已更新，请刷新", 409)
    i.session.refresh(r)
    event(
        i.session,
        i.tenant.id,
        i.user.id,
        "feedback.kpi",
        r.id,
        {
            "completed": completed,
            "note": note,
            "teacher_id": r.teacher_id,
            "version": r.version,
        },
    )
    return r


def transfer(i, enrollment_id, class_id, effective_at, reason):
    permit(i, "enrollment.write")
    e = Scope(i).own(enrollment_id, "enrollment")
    from .domain import lock_record

    lock_record(i.session, i.tenant.id, e.id)
    if e.data.get("status", "active") != "active":
        fail("ENROLLMENT_CLOSED", "已结束报名不能调班")
    cls = Scope(i).own(class_id, "class") if class_id else None
    at = dt(effective_at) if effective_at else now()
    if at > now() + timedelta(minutes=1):
        fail("DATE_INVALID", "请在调班生效时登记")
    if not reason.strip():
        fail("REASON_REQUIRED", "请填写调班原因")
    if at < dt(e.data.get("started_at", e.created_at)):
        fail("DATE_INVALID", "不能早于报名开始时间")
    if cls:
        lock_record(i.session, i.tenant.id, cls.id)
        occupants = [
            x
            for x in i.session.exec(
                query(i.session, Record, i.tenant.id).where(Record.kind == "enrollment")
            ).all()
            if x.id != e.id
            and x.data.get("status", "active") == "active"
            and x.data.get("class_id") == class_id
        ]
        if (
            len({x.data["student_id"] for x in occupants} | {e.data["student_id"]})
            > cls.data["capacity"]
        ):
            fail("CLASS_FULL", "班级已满")
    capture_rosters(i.session, i.tenant.id)
    d = dict(e.data)
    history = list(d.get("history", []))
    if not history:
        history = [
            {
                "class_id": d.get("class_id", ""),
                "start": d.get("started_at", e.created_at.isoformat()),
                "end": None,
            }
        ]
    if dt(history[-1]["start"]) > at:
        fail("DATE_INVALID", "不能覆盖已存在的调班历史")
    history[-1] = {**history[-1], "end": at.isoformat()}
    history.append({"class_id": class_id, "start": at.isoformat(), "end": None})
    e.data = {**d, "class_id": class_id, "history": history}
    e.version += 1
    i.session.add(e)
    event(
        i.session,
        i.tenant.id,
        i.user.id,
        "enrollment.transferred",
        e.id,
        {
            "from_class": d.get("class_id", ""),
            "class_id": class_id,
            "student_id": d["student_id"],
            "reason": reason,
        },
        at,
    )
    return e


def refund_context(s, t, order_id):
    order = ref(s, t, order_id, "order")
    ens = [
        e
        for e in s.exec(query(s, Record, t).where(Record.kind == "enrollment")).all()
        if e.data.get("order_id") == order.id
    ]
    credits = s.exec(query(s, CreditEntry, t)).all()
    rev = {x.reverses_id for x in credits if x.reverses_id}
    result = []
    for e in ens:
        owncredits = [x for x in credits if x.enrollment_id == e.id]
        result.append(
            {
                "enrollment_id": e.id,
                "student_id": e.data["student_id"],
                "class_id": e.data.get("class_id", ""),
                "status": e.data.get("status", "active"),
                "purchased_units": order.data.get(
                    "purchased_units", order.data.get("course_lessons", 0)
                ),
                "attended_units": sum(
                    -x.delta
                    for x in owncredits
                    if x.kind == "attendance" and x.id not in rev
                ),
                "remaining_units": sum(x.delta for x in owncredits),
                "adjustments": [
                    {"kind": x.kind, "delta": x.delta, "created_at": x.created_at}
                    for x in owncredits
                    if x.kind not in ("attendance", "grant")
                ],
            }
        )
    return {
        "order_id": order.id,
        "net_paid_fen": balance(s, t, order.id),
        "enrollments": result,
        "purchased_units": order.data.get(
            "purchased_units", order.data.get("course_lessons", 0)
        ),
    }


def refund(i, order_id, body):
    from .domain import record_money

    s = i.session
    t = i.tenant.id
    from .domain import lock_record

    order = ref(s, t, order_id, "order")
    lock_record(s, t, order.id)
    for e in s.exec(query(s, Record, t).where(Record.kind == "enrollment")).all():
        if e.data.get("order_id") == order_id:
            lock_record(s, t, e.id)
    old = s.exec(
        query(s, LedgerEntry, t).where(LedgerEntry.request_id == body.request_id)
    ).first()
    snapshot = refund_context(s, t, order_id)
    if old:
        if old.order_id != order_id or old.amount_fen != -body.amount_fen:
            fail("IDEMPOTENCY_CONFLICT", "请求编号已使用", 409)
        prior = s.exec(
            query(s, BusinessEvent, t).where(
                BusinessEvent.request_id == "refund:" + body.request_id
            )
        ).first()
        if prior and (
            prior.payload.get("withdrawal") != body.withdrawal
            or prior.payload.get("reason") != body.reason
            or sorted(prior.payload.get("enrollment_ids", []))
            != sorted(body.enrollment_ids)
        ):
            fail("IDEMPOTENCY_CONFLICT", "退款内容不一致", 409)
        return old
    if not body.reason.strip():
        fail("REASON_REQUIRED", "请填写退款原因")
    from .studio import guard_action

    guard_action(
        i,
        "refund",
        order_id,
        {
            "amount_fen": body.amount_fen,
            "reason": body.reason,
            "withdrawal": body.withdrawal,
            "enrollment_ids": sorted(body.enrollment_ids),
        },
        body.workflow_id,
    )
    if (
        not body.withdrawal
        and body.amount_fen >= snapshot["net_paid_fen"]
        and any(e["status"] == "active" for e in snapshot["enrollments"])
    ):
        fail("REFUND_MODE_INVALID", "已在读报名全额退费时，请明确选择退读关系")
    if body.withdrawal and not body.enrollment_ids:
        fail("ENROLLMENT_REQUIRED", "退读请选择要结束的报名关系")
    ids = {e["enrollment_id"] for e in snapshot["enrollments"]}
    if not set(body.enrollment_ids) <= ids:
        fail("REFERENCE_INVALID", "退读报名不属于此订单")
    capture_rosters(s, t)
    entry = record_money(
        s,
        t,
        i.user.id,
        order_id,
        "refund",
        body.amount_fen,
        body.request_id,
        body.reason,
    )
    s.flush()
    if body.withdrawal:
        for eid in body.enrollment_ids:
            e = ref(s, t, eid, "enrollment")
            if e.data.get("status", "active") != "active":
                fail("ENROLLMENT_CLOSED", "所选报名已经结束")
            history = list(e.data.get("history", []))
            if history:
                history[-1] = {**history[-1], "end": now().isoformat()}
            remaining = credit_balance(s, t, eid)
            if remaining:
                s.add(
                    CreditEntry(
                        tenant_id=t,
                        enrollment_id=eid,
                        delta=-remaining,
                        kind="withdrawal",
                        request_id="withdraw:" + entry.id + ":" + eid,
                        actor_id=i.user.id,
                    )
                )
            e.data = {
                **e.data,
                "status": "withdrawn",
                "ended_at": now().isoformat(),
                "history": history,
                "withdrawal_reason": body.reason,
            }
            e.version += 1
            s.add(e)
            event(
                s,
                t,
                i.user.id,
                "enrollment.closed",
                eid,
                {
                    "student_id": e.data["student_id"],
                    "class_id": e.data.get("class_id", ""),
                    "reason": body.reason,
                    "order_id": order_id,
                },
            )
    event(
        s,
        t,
        i.user.id,
        "finance.refund.context",
        entry.id,
        {
            "order_id": order_id,
            "snapshot": snapshot,
            "withdrawal": body.withdrawal,
            "enrollment_ids": body.enrollment_ids,
            "reason": body.reason,
        },
        key="refund:" + body.request_id,
    )
    return entry


def class_view(i, q="", teacher_id="", status="active"):
    scope = Scope(i)
    students = {r.id: r for r in scope.list("student")}
    classes = (
        scope.list("class")
        if has(i, "class.read")
        else [r for r in scope.rows.values() if r.kind == "class"]
    )
    ens = [
        e
        for e in scope.rows.values()
        if e.kind == "enrollment" and e.data.get("student_id") in students
    ]
    if "teacher" in i.roles and not i.roles & {"owner", "academic_admin"}:
        ens = [e for e in ens if e.id in scope.enrollments]
        students = {
            sid: student for sid, student in students.items() if sid in scope.students
        }
    result = []
    for cls in classes + [None]:
        if teacher_id and (not cls or cls.data.get("teacher_id") != teacher_id):
            continue
        members = []
        for student in students.values():
            assigned = [
                e
                for e in ens
                if e.data.get("student_id") == student.id
                and (e.data.get("class_id", "") == (cls.id if cls else ""))
                and (status == "all" or e.data.get("status", "active") == status)
            ]
            if not assigned and (
                cls or any(e.data.get("student_id") == student.id for e in ens)
            ):
                continue
            if (
                cls is None
                and "teacher" in i.roles
                and not i.roles & {"owner", "academic_admin", "admissions", "finance"}
            ):
                continue
            view = scope.project(student)
            if (
                q
                and q.lower()
                not in json.dumps(view["data"], ensure_ascii=False).lower()
            ):
                continue
            view["enrollments"] = [
                {
                    "id": e.id,
                    "status": e.data.get("status", "active"),
                    "program_name": e.data.get("program_name", ""),
                    "remaining": credit_balance(i.session, i.tenant.id, e.id),
                }
                for e in assigned
            ]
            members.append(view)
        result.append(
            {
                "id": cls.id if cls else "",
                "name": cls.data["name"] if cls else "未分班",
                "teacher_id": cls.data.get("teacher_id", "") if cls else "",
                "students": members,
                "count": len(members),
            }
        )
    return result

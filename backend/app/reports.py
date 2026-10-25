"""Deterministic cohort reports, versioned snapshots and a transactional notification outbox."""

import json, hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs
import httpx
from sqlmodel import select
from .models import *
from .domain import query, own, plain_data
from .permissions import Scope, has, permit, member_roles, identity_for
from .operations import options, dt, class_at, capture_rosters, event
from .security import fail, encrypt, decrypt
from .config import settings

TZ = ZoneInfo("Asia/Shanghai")


def clean(value):
    return json.loads(
        json.dumps(
            value,
            default=lambda x: x.isoformat() if isinstance(x, datetime) else str(x),
            ensure_ascii=False,
        )
    )


def ratio(a, b):
    return round(a / b * 100, 2) if b else None


def period_range(kind, period):
    try:
        if kind == "weekly":
            x = datetime.fromisoformat(period).replace(tzinfo=TZ)
            x = (x - timedelta(days=x.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = x + timedelta(days=7)
        elif kind == "monthly":
            x = datetime.strptime(period, "%Y-%m").replace(tzinfo=TZ)
            end = (x.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            fail("PERIOD_INVALID", "报表类型错误")
    except ValueError:
        fail("PERIOD_INVALID", "日期格式应为YYYY-MM-DD或YYYY-MM")
    return x.astimezone(__import__("datetime").timezone.utc), end.astimezone(
        __import__("datetime").timezone.utc
    )


def financial(i, start, end, class_id="", channel="", *, details=True):
    permit(i, "finance.read" if details else "revenue.read")
    s = i.session
    t = i.tenant.id
    scope = Scope(i)
    orders = {r.id: r for r in scope.rows.values() if r.kind == "order"}
    ens = [r for r in scope.rows.values() if r.kind == "enrollment"]

    def match(order, at):
        if not order:
            return False
        if channel and order.data.get("channel_id") != channel:
            return False
        return (
            not class_id
            or order.data.get("class_id") == class_id
            or any(
                e.data.get("order_id") == order.id and class_at(e, at) == class_id
                for e in ens
            )
        )

    all_entries = s.exec(query(s, LedgerEntry, t)).all()
    byid = {e.id: e for e in all_entries}
    entries = [
        e
        for e in all_entries
        if start <= as_utc(e.created_at) < end
        and match(orders.get(e.order_id), as_utc(e.created_at))
    ]
    days = defaultdict(
        lambda: {"received_fen": 0, "refund_fen": 0, "expense_fen": 0, "net_fen": 0}
    )
    root_types = {}
    for e in entries:
        day = as_utc(e.created_at).astimezone(TZ).date().isoformat()
        root = e
        seen = set()
        while root.reverses_id in byid and root.id not in seen:
            seen.add(root.id)
            root = byid[root.reverses_id]
        kind = root.entry_type
        root_types[e.id] = kind
        days[day]["received_fen" if kind == "payment" else "refund_fen"] += (
            e.amount_fen if kind == "payment" else -e.amount_fen
        )
    if not details:
        chart = [
            {
                "date": day,
                "received_fen": d["received_fen"],
                "refund_fen": d["refund_fen"],
                "net_fen": d["received_fen"] - d["refund_fen"],
            }
            for day, d in sorted(days.items())
        ]
        return {
            "totals": {
                key: sum(d[key] for d in chart)
                for key in ("received_fen", "refund_fen", "net_fen")
            },
            "chart": chart,
        }
    expenses = []
    for r in [
        r
        for r in scope.rows.values()
        if r.kind == "expense" and r.data.get("status") == "confirmed"
    ]:
        try:
            at = (
                dt(r.data["date"] + "T00:00:00+08:00")
                if r.data.get("date")
                else as_utc(r.created_at)
            )
        except ValueError:
            at = as_utc(r.created_at)
        if (
            not start <= at < end
            or (class_id and r.data.get("class_id") != class_id)
            or (channel and r.data.get("channel_id") != channel)
        ):
            continue
        expenses.append(r)
        days[at.astimezone(TZ).date().isoformat()]["expense_fen"] += r.data[
            "amount_fen"
        ]
    chart = []
    for day, d in sorted(days.items()):
        d["net_fen"] = d["received_fen"] - d["refund_fen"]
        d["cash_difference_fen"] = d["net_fen"] - d["expense_fen"]
        chart.append({"date": day, **d})
    totals = {
        k: sum(d[k] for d in chart)
        for k in (
            "received_fen",
            "refund_fen",
            "net_fen",
            "expense_fen",
            "cash_difference_fen",
        )
    }
    return {
        "totals": totals,
        "chart": chart,
        "transactions": [
            {
                "id": e.id,
                "order_id": e.order_id,
                "name": orders[e.order_id].data["name"],
                "type": e.entry_type,
                "category": root_types.get(e.id, e.entry_type),
                "amount_fen": e.amount_fen,
                "date": e.created_at,
            }
            for e in sorted(entries, key=lambda e: e.created_at, reverse=True)
        ],
        "expenses": [scope.project(e) for e in expenses],
    }


def build(i, kind, period, class_id=""):
    permit(i, "reports.read")
    s = i.session
    t = i.tenant.id
    start, end = period_range(kind, period)
    period = start.astimezone(TZ).strftime("%Y-%m" if kind == "monthly" else "%Y-%m-%d")
    scope = Scope(i)
    capture_rosters(s, t)
    leads = scope.list("lead") if has(i, "lead.read") else []
    enroll = [
        r
        for r in scope.rows.values()
        if r.kind == "enrollment"
        and (
            scope.visible(r)
            or (
                has(i, "order.read")
                and r.data.get("order_id") in {x.id for x in scope.list("order")}
            )
        )
    ]
    if class_id:
        if has(i, "class.read"):
            scope.own(class_id, "class")
        else:
            fail("ROLE_FORBIDDEN", "当前岗位不能读取班级教务报表", 403)

    def present(e, when):
        c = class_at(e, when)
        return c is not None and (not class_id or c == class_id)

    opening = {e.data["student_id"] for e in enroll if present(e, start)}
    during = [
        e
        for e in enroll
        if start <= dt(e.data.get("started_at", e.created_at)) < end
        and (
            not class_id
            or any(h["class_id"] == class_id for h in e.data.get("history", []))
        )
    ]
    additions = {e.data["student_id"] for e in during}
    earliest = {}
    for e in enroll:
        sid = e.data["student_id"]
        date = dt(e.data.get("started_at", e.created_at))
        earliest[sid] = min(earliest.get(sid, date), date)
    first = {sid for sid in additions if start <= earliest[sid] < end}
    closures = s.exec(
        query(s, BusinessEvent, t).where(
            BusinessEvent.kind == "enrollment.closed",
            BusinessEvent.occurred_at >= start,
            BusinessEvent.occurred_at < end,
        )
    ).all()
    allowed_ids = {e.id for e in enroll}
    withdrawn = set()
    withdrawal_reasons = []
    for ev in closures:
        if ev.record_id not in allowed_ids or (
            class_id and ev.payload.get("class_id") != class_id
        ):
            continue
        sid = ev.payload["student_id"]
        at = as_utc(ev.occurred_at) + timedelta(microseconds=1)
        if not any(e.data["student_id"] == sid and present(e, at) for e in enroll):
            withdrawn.add(sid)
        withdrawal_reasons.append(
            {
                "student_id": sid,
                "reason": ev.payload.get("reason", ""),
                "date": ev.occurred_at,
                "class_id": ev.payload.get("class_id", ""),
            }
        )
    newleads = [
        l
        for l in leads
        if start <= as_utc(l.created_at) < end
        and (not class_id or l.data.get("class_id") == class_id)
    ]
    trials = [
        l
        for l in leads
        if l.data.get("first_attended_at")
        and start <= dt(l.data["first_attended_at"]) < end
        and (not class_id or l.data.get("class_id") == class_id)
    ]
    converted = lambda rows: sum(
        bool(l.data.get("won_at") and dt(l.data["won_at"]) <= now()) for l in rows
    )
    classes = {r.id: r for r in (scope.list("class") if has(i, "class.read") else [])}
    lessons = {r.id: r for r in scope.rows.values() if r.kind == "lesson"}
    rosters = [
        r
        for r in s.exec(query(s, LessonRoster, t)).all()
        if (
            r.enrollment_id in allowed_ids
            or ("teacher" in i.roles and r.teacher_id == i.user.id)
        )
        and start <= as_utc(r.starts_at) < end
        and (
            r.class_id in classes
            or ("teacher" in i.roles and r.teacher_id == i.user.id)
        )
        and (not class_id or r.class_id == class_id)
        and r.lesson_id in lessons
        and lessons[r.lesson_id].data.get("status") != "cancelled"
        and as_utc(r.starts_at)
        + timedelta(minutes=lessons[r.lesson_id].data.get("duration_minutes", 90))
        <= now()
    ]
    rosters = list({(r.lesson_id, r.student_id): r for r in rosters}.values())
    credits = s.exec(query(s, CreditEntry, t)).all()
    reversed_ids = {c.reverses_id for c in credits if c.reverses_id}
    attended = {
        (c.student_id or scope.rows[c.enrollment_id].data["student_id"], c.lesson_id)
        for c in credits
        if c.kind == "attendance" and c.id not in reversed_ids
    }
    leaves = [
        r
        for r in scope.rows.values()
        if r.kind == "leave"
        and r.data.get("enrollment_id") in allowed_ids
        and r.data.get("status") in ("approved", "made_up")
    ]
    leavekeys = {
        (scope.rows[l.data["enrollment_id"]].data["student_id"], l.data["lesson_id"])
        for l in leaves
    }
    actual = sum((r.student_id, r.lesson_id) in attended for r in rosters)
    excused = sum(
        (r.student_id, r.lesson_id) in leavekeys
        and (r.student_id, r.lesson_id) not in attended
        for r in rosters
    )
    kpis = [
        k
        for k in s.exec(query(s, FeedbackKPI, t)).all()
        if k.lesson_id in lessons
        and start <= dt(lessons[k.lesson_id].data["starts_at"]) < end
        and (k.class_id in classes or k.teacher_id == i.user.id)
        and (not class_id or k.class_id == class_id)
        and lessons[k.lesson_id].data.get("status") != "cancelled"
        and (
            "owner" in i.roles
            or "academic_admin" in i.roles
            or k.teacher_id == i.user.id
        )
    ]
    calibrated = options(i.tenant)["baseline_confirmed"] or all(
        e.data.get("history_calibrated", False) for e in enroll
    )
    population = opening | additions
    rate = ratio(len(withdrawn & population), len(population)) if calibrated else None
    metrics = {
        "new_leads": len(newleads),
        "trial_attendees": len(trials),
        "lead_converted": converted(newleads),
        "trial_converted": converted(trials),
        "lead_conversion_rate": ratio(converted(newleads), len(newleads)),
        "trial_conversion_rate": ratio(converted(trials), len(trials)),
        "new_students": len(first),
        "additional_enrollments": len(during) - len(first),
        "opening_students": len(opening),
        "population": len(population),
        "withdrawn_students": len(withdrawn & population),
        "attrition_rate": rate,
        "expected_attendance": len(rosters),
        "actual_attendance": actual,
        "attendance_rate": ratio(actual, len(rosters)),
        "excused_absences": excused,
        "unexcused_absences": len(rosters) - actual - excused,
        "feedback_expected": len(kpis),
        "feedback_completed": sum(k.completed_at is not None for k in kpis),
        "feedback_overdue": sum(
            k.completed_at is None and as_utc(k.due_at) < now() for k in kpis
        ),
        "feedback_completion_rate": ratio(
            sum(k.completed_at is not None for k in kpis), len(kpis)
        ),
    }
    if not calibrated:
        for key in (
            "opening_students",
            "population",
            "new_students",
            "withdrawn_students",
            "additional_enrollments",
        ):
            metrics[key] = None
    classrows = []
    for roster in rosters:
        if roster.class_id not in classes and roster.class_id in scope.rows:
            classes[roster.class_id] = scope.rows[roster.class_id]
    for cid, cls in classes.items():
        slots = [r for r in rosters if r.class_id == cid]
        count = sum((r.student_id, r.lesson_id) in attended for r in slots)
        classrows.append(
            {
                "id": cid,
                "name": cls.data["name"],
                "expected": len(slots),
                "actual": count,
                "attendance_rate": ratio(count, len(slots)),
            }
        )
    makeup = [
        l
        for l in leaves
        if any(
            l.data["enrollment_id"] == r.enrollment_id
            and l.data["lesson_id"] == r.lesson_id
            for r in rosters
        )
    ]
    metrics.update(
        makeup_completed=sum(l.data["status"] == "made_up" for l in makeup),
        makeup_pending=sum(l.data["status"] == "approved" for l in makeup),
    )
    refunds = []
    entries = s.exec(query(s, LedgerEntry, t)).all()
    ledger_byid = {e.id: e for e in entries}
    effective = defaultdict(int)
    for entry in entries:
        root = entry
        visited = set()
        while root.reverses_id in ledger_byid and root.id not in visited:
            visited.add(root.id)
            root = ledger_byid[root.reverses_id]
        effective[root.id] += entry.amount_fen
    visibleorders = (
        {r.id for r in scope.list("order")} if has(i, "order.read") else set()
    )
    for ev in s.exec(
        query(s, BusinessEvent, t).where(
            BusinessEvent.kind == "finance.refund.context",
            BusinessEvent.occurred_at >= start,
            BusinessEvent.occurred_at < end,
        )
    ).all():
        if (
            effective.get(ev.record_id, 0) >= 0
            or ev.payload.get("order_id") not in visibleorders
        ):
            continue
        if class_id and not any(
            e.get("class_id") == class_id
            for e in ev.payload.get("snapshot", {}).get("enrollments", [])
        ):
            continue
        refunds.append(
            {
                "entry_id": ev.record_id,
                "reason": ev.payload.get("reason", ""),
                "withdrawal": ev.payload.get("withdrawal", False),
                "date": ev.occurred_at,
            }
        )
    metrics["refund_count"] = len(refunds)
    out = {
        "kind": kind,
        "period": period,
        "from": start,
        "to": end,
        "as_of": now(),
        "baseline_status": "confirmed" if calibrated else "needs_calibration",
        "metrics": metrics,
        "classes": classrows,
        "withdrawals": withdrawal_reasons,
        "refunds": refunds,
        "lost_leads": [
            {
                "id": l.id,
                "name": l.data["name"],
                "reason": l.data.get("loss_reason", "历史原因缺失"),
            }
            for l in leads
            if l.data.get("stage") == "lost"
            and start <= dt(l.data.get("lost_at", l.updated_at)) < end
        ],
    }
    if has(i, "finance.read"):
        out["finance"] = financial(i, start, end, class_id)
    elif has(i, "revenue.read"):
        out["revenue"] = financial(i, start, end, class_id, details=False)
    if not has(i, "lead.read"):
        for key in (
            "new_leads",
            "trial_attendees",
            "lead_converted",
            "trial_converted",
            "lead_conversion_rate",
            "trial_conversion_rate",
        ):
            metrics.pop(key, None)
    if not (has(i, "education.read") or has(i, "order.read")):
        metrics.clear()
    if has(i, "family_feedback.read"):
        items = [
            r
            for r in scope.list("family_feedback")
            if start <= dt(r.data.get("recorded_at", r.created_at)) < end
            and (not class_id or r.data.get("class_id") == class_id)
        ]
        ratings = [r.data["rating"] for r in items if r.data.get("rating") is not None]
        categories = defaultdict(int)
        for r in items:
            categories[r.data.get("category", "other")] += 1
        out["family_feedback"] = {
            "count": len(items),
            "rated_count": len(ratings),
            "average_rating": round(sum(ratings) / len(ratings), 2)
            if ratings
            else None,
            "unresolved": sum(r.data.get("status") == "open" for r in items),
            "attention": sum(
                r.data.get("rating") is not None and r.data["rating"] <= 2
                for r in items
            ),
            "parents": sum(r.data.get("respondent") == "parent" for r in items),
            "students": sum(r.data.get("respondent") == "student" for r in items),
            "categories": dict(categories),
            "record_ids": [r.id for r in items],
        }
    if has(i, "content.read") and not class_id:
        from .matrix_worker import matrix_overview
        media = matrix_overview(i.session, i.tenant, start=start, end=end)
        out["self_media"] = {k: media[k] for k in ("published", "exceptions", "cost_fen", "reserved_fen", "shared_cost_fen", "platforms", "attributed_leads", "attributed_enrollments")}
        out["self_media"]["generated"] = len(i.session.exec(query(i.session, AutomationAccountTask, i.tenant.id).where(AutomationAccountTask.version_id != "", AutomationAccountTask.created_at >= start, AutomationAccountTask.created_at < end)).all())
    out["summary"] = report_summary(out)
    return clean(out)


def report_summary(data):
    """Facts from authorized deterministic sections, without customer text or identities."""
    lines = []
    metrics = data.get("metrics", {})
    if "new_leads" in metrics:
        rate = metrics.get("lead_conversion_rate")
        lines.append(
            f"新增线索{metrics['new_leads']}条，线索转化率"
            + (f"{rate}%" if rate is not None else "暂无数据")
            + "。"
        )
    if "new_students" in metrics:
        new, lost = metrics.get("new_students"), metrics.get("withdrawn_students")
        lines.append(
            f"新增在读{new if new is not None else '待校准'}人，退读{lost if lost is not None else '待校准'}人。"
        )
    money = data.get("finance", data.get("revenue"))
    if money:
        totals = money["totals"]
        lines.append(
            f"实收{totals['received_fen'] / 100:.2f}元，退款{totals['refund_fen'] / 100:.2f}元，净收{totals['net_fen'] / 100:.2f}元。"
        )
        if "expense_fen" in totals:
            lines.append(
                f"已确认费用{totals['expense_fen'] / 100:.2f}元，收支差额{totals['cash_difference_fen'] / 100:.2f}元。"
            )
    media = data.get("self_media")
    if media:
        lines.append(f"自媒体发布{media['published']}条，发布异常{media['exceptions']}项，模型费用{media['cost_fen']/100:.2f}元。")
    feedback = data.get("family_feedback")
    if feedback:
        lines.append(
            f"记录学员及家长反馈{feedback['count']}条，待处理{feedback['unresolved']}条，低评分反馈{feedback['attention']}条。"
        )
    return lines


def snapshot(i, kind, period):
    data = build(i, kind, period)
    period = data["period"]
    fingerprint = hashlib.sha256(
        json.dumps(
            {k: v for k, v in data.items() if k != "as_of"},
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    existing = i.session.exec(
        query(i.session, ReportSnapshot, i.tenant.id)
        .where(ReportSnapshot.kind == kind, ReportSnapshot.period == period)
        .order_by(ReportSnapshot.version.desc())
    ).first()
    if existing and existing.digest == fingerprint:
        return existing
    row = ReportSnapshot(
        tenant_id=i.tenant.id,
        kind=kind,
        period=period,
        version=existing.version + 1 if existing else 1,
        digest=fingerprint,
        payload=data,
    )
    i.session.add(row)
    i.session.flush()
    return row


def enqueue(s, t, key, kind, body):
    old = s.exec(
        query(s, NotificationOutbox, t.id).where(NotificationOutbox.request_id == key)
    ).first()
    if old:
        return old
    row = NotificationOutbox(
        tenant_id=t.id,
        request_id=key,
        kind=kind,
        body=body,
        config_version=t.settings.get("notice_version", 0),
    )
    s.add(row)
    s.flush()
    return row


def evaluate_alerts(i, month):
    cfg = options(i.tenant)
    result = []
    for rule in cfg["rules"]:
        report = build(i, "monthly", month, rule.get("class_id", ""))
        value = report["metrics"].get(rule["metric"])
        threshold = rule["threshold"]
        row = i.session.exec(
            query(i.session, OpsAlert, i.tenant.id).where(
                OpsAlert.rule_id == rule["id"], OpsAlert.period == month
            )
        ).first()
        hit = value is not None and (
            value >= threshold
            if rule.get("direction", "gte") == "gte"
            else value <= threshold
        )
        if hit and not row:
            row = OpsAlert(
                tenant_id=i.tenant.id,
                rule_id=rule["id"],
                period=month,
                metric=rule["metric"],
                value=value,
                threshold=threshold,
                class_id=rule.get("class_id", ""),
                owner_id=i.user.id,
                detail={
                    "population": report["metrics"].get("population"),
                    "baseline_status": report["baseline_status"],
                },
            )
            i.session.add(row)
            i.session.flush()
            enqueue(
                i.session,
                i.tenant,
                "alert:" + row.id,
                "alert",
                f"经营异常：{month}，{rule['metric']}为{value}%，阈值{threshold}%。请负责人登录查看原因及明细。",
            )
        elif row:
            recovered = row.status == "recovered"
            row.value = value if value is not None else row.value
            row.threshold = threshold
            row.updated_at = now()
            if value is not None and not hit:
                row.status = "recovered"
            elif recovered:
                row.status = "open"
                enqueue(
                    i.session,
                    i.tenant,
                    "alert-reopen:" + row.id + ":" + now().date().isoformat(),
                    "alert",
                    "经营指标再次触发异常，请负责人登录查看。",
                )
            i.session.add(row)
        if row:
            result.append(row)
    return result


def webhook_valid(url):
    u = urlparse(url)
    if (
        u.scheme != "https"
        or u.hostname != "qyapi.weixin.qq.com"
        or u.path != "/cgi-bin/webhook/send"
        or u.username
        or u.password
        or u.port not in (None, 443)
        or set(parse_qs(u.query)) != {"key"}
        or len(parse_qs(u.query)["key"][0]) < 10
    ):
        fail("WEBHOOK_INVALID", "请填写官方企业微信群机器人Webhook地址")


def delivery(s, t, row):
    if row.status not in ("queued", "retrying") or as_utc(row.next_attempt_at) > now():
        return
    if row.config_version != t.settings.get("notice_version", 0):
        row.status = "cancelled"
        row.error = "通知配置已变更，请核对后重新发送"
        s.add(row)
        s.commit()
        return
    integration = s.exec(
        query(s, Integration, t.id).where(
            Integration.provider == "wecom_notice", Integration.active == True
        )
    ).first()
    if not integration or not integration.secret_cipher:
        row.status = "unconfigured"
        row.error = "负责人管理群机器人未配置"
        s.add(row)
        s.commit()
        return
    if not any(
        member_roles(m) & {"owner"}
        and s.get(User, m.user_id)
        and not s.get(User, m.user_id).disabled
        for m in s.exec(select(Membership).where(Membership.tenant_id == t.id)).all()
    ):
        row.status = "cancelled"
        s.add(row)
        s.commit()
        return
    recent = s.exec(
        query(s, NotificationOutbox, t.id).where(
            NotificationOutbox.updated_at >= now() - timedelta(minutes=1),
            NotificationOutbox.status == "sent",
        )
    ).all()
    if len(recent) >= 10:
        row.status = "retrying"
        row.next_attempt_at = now() + timedelta(minutes=1)
        s.add(row)
        s.commit()
        return
    url = decrypt(t.id, integration.secret_cipher)
    webhook_valid(url)
    from sqlalchemy import update

    claimed = s.exec(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.id == row.id,
            NotificationOutbox.tenant_id == t.id,
            NotificationOutbox.status.in_(["queued", "retrying"]),
            NotificationOutbox.attempts == row.attempts,
        )
        .values(status="sending", attempts=row.attempts + 1, updated_at=now())
    )
    s.commit()
    if claimed.rowcount != 1:
        return
    s.refresh(row)
    row.status = "sending"
    row.updated_at = now()
    s.add(row)
    s.commit()
    try:
        with httpx.Client(
            timeout=10, follow_redirects=False, trust_env=False
        ) as client:
            response = client.post(
                url,
                json={
                    "msgtype": "markdown",
                    "markdown": {
                        "content": "### 知营经营通知\n"
                        + row.body
                        + "\n[登录工作台查看]("
                        + settings().public_url
                        + "/#reports)"
                    },
                },
            )
        data = response.json()
        if response.status_code == 429 or data.get("errcode") in (45009, 45000):
            row.status = "retrying" if row.attempts < 5 else "failed"
            row.next_attempt_at = now() + timedelta(
                seconds=min(3600, 60 * 2**row.attempts)
            )
            row.error = "平台限流"
        elif response.status_code == 200 and data.get("errcode") == 0:
            row.status = "sent"
            row.error = ""
        else:
            row.status = "failed"
            row.error = "企业微信拒绝消息，请检查机器人配置"
    except Exception:
        row.status = "unknown"
        row.error = "发送结果未知，请在企微核实后处理"
    row.updated_at = now()
    s.add(row)
    s.commit()


def tick(s, t):
    from .domain import entitlement

    if t.status != "active" or not entitlement(s, t)["active"]:
        return
    for stale in s.exec(
        query(s, NotificationOutbox, t.id).where(
            NotificationOutbox.status == "sending",
            NotificationOutbox.updated_at < now() - timedelta(minutes=5),
        )
    ).all():
        stale.status = "unknown"
        stale.error = "发送期间服务重启，须核实发送结果"
        s.add(stale)
    cfg = options(t)
    due = cfg.get("next_tick_at")
    if due and dt(due) > now():
        return
    owners = [
        m.user_id
        for m in s.exec(select(Membership).where(Membership.tenant_id == t.id)).all()
        if "owner" in member_roles(m)
        and s.get(User, m.user_id)
        and s.get(User, m.user_id).verified
        and not s.get(User, m.user_id).disabled
    ]
    if not owners:
        return
    try:
        i = identity_for(s, t, owners[0])
    except Exception:
        return
    local = now().astimezone(TZ)
    month = local.strftime("%Y-%m")
    evaluate_alerts(i, month)
    monday = (local - timedelta(days=local.weekday())).date()
    periods = []
    if local.weekday() >= cfg["week_day"] and local.hour >= cfg["week_hour"]:
        periods.append(("weekly", (monday - timedelta(days=7)).isoformat()))
    if local.day >= cfg["month_day"] and local.hour >= cfg["month_hour"]:
        periods.append(
            ("monthly", (local.replace(day=1) - timedelta(days=1)).strftime("%Y-%m"))
        )
    existing = s.exec(query(s, ReportSnapshot, t.id)).all()
    periods = list(set(periods) | {(r.kind, r.period) for r in existing})
    for kind, period in periods:
        report = snapshot(i, kind, period)
        key = (
            "report:"
            + kind
            + ":"
            + period
            + (
                ":first"
                if report.version == 1
                else ":correction:" + str(report.version)
            )
        )
        body = (
            f"{'周报' if kind == 'weekly' else '月报'} {period} 第{report.version}版："
            + " ".join(report.payload.get("summary", []))
        )
        enqueue(s, t, key, "report", body)
    t.settings = {
        **t.settings,
        "operations": {
            **cfg,
            "next_tick_at": (now() + timedelta(seconds=60)).isoformat(),
        },
    }
    s.add(t)
    s.commit()
    for row in s.exec(
        query(s, NotificationOutbox, t.id).where(
            NotificationOutbox.status.in_(["queued", "retrying"])
        )
    ).all():
        delivery(s, t, row)
    for row in s.exec(
        query(s, NotificationOutbox, t.id).where(
            NotificationOutbox.status == "sending",
            NotificationOutbox.updated_at < now() - timedelta(minutes=5),
        )
    ).all():
        row.status = "unknown"
        row.error = "发送任务中断，请先核实"
        s.add(row)
    s.commit()

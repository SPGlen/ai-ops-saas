"""Shared authorization for HTTP, workers, exports and UI."""

from types import SimpleNamespace
from sqlmodel import select
from .models import Membership, Record, User
from .security import fail

ROLE_LABELS = {
    "owner": "机构负责人",
    "admissions": "招生",
    "content_ops": "内容运营",
    "academic_admin": "教务",
    "teacher": "授课",
    "scheduler": "排班",
    "revenue_viewer": "整体营收查看",
    "finance": "财务",
}
LEGACY = {"operator": ["admissions", "content_ops", "academic_admin", "scheduler"]}
GRANTS = {
    "admissions": {
        "lead.read",
        "lead.write",
        "student.read",
        "student.write",
        "order.read",
        "order.write",
        "course.read",
        "conversation.read",
        "conversation.write",
        "booking.read",
        "reports.read",
    },
    "content_ops": {
        f"{k}.{a}"
        for k in ("content", "publish", "knowledge", "topic", "campaign", "community")
        for a in ("read", "write")
    }
    | {
        "social.read",
        "social.reply",
        "conversation.read",
        "conversation.write",
        "course.read",
        "usage.read",
    },
    "academic_admin": {
        f"{k}.{a}"
        for k in (
            "student",
            "class",
            "lesson",
            "enrollment",
            "leave",
            "feedback",
            "course",
        )
        for a in ("read", "write")
    }
    | {
        "attendance.read",
        "attendance.write",
        "education.read",
        "reports.read",
        "credit.write",
        "family_feedback.read",
        "family_feedback.write",
        "order.read",
        "knowledge.read",
        "booking.read",
        "reports.read",
    },
    "teacher": {
        f"{k}.read"
        for k in (
            "student",
            "class",
            "lesson",
            "enrollment",
            "leave",
            "feedback",
            "course",
            "knowledge",
        )
    }
    | {
        "attendance.read",
        "attendance.write",
        "education.read",
        "reports.read",
        "feedback.write",
        "leave.write",
        "family_feedback.read",
        "family_feedback.write",
    },
    "scheduler": {"class.read", "lesson.read", "lesson.write", "schedule.read"},
    "revenue_viewer": {"revenue.read", "reports.read"},
    "finance": {
        f"{k}.{a}" for k in ("order", "expense", "channel") for a in ("read", "write")
    }
    | {
        "finance.read",
        "finance.write",
        "revenue.read",
        "student.read",
        "course.read",
        "usage.read",
        "reports.read",
    },
}
# Existing education staff retain scheduling via the compatibility migration.
GRANTS["academic_admin"].discard("lesson.write")
ALL = set().union(*GRANTS.values()) | {
    "members.manage",
    "tenant.manage",
    "audit.read",
    "integration.manage",
    "social.manage",
    "lead.assign",
    "rubric.manage",
}


def member_roles(m):
    if not m or getattr(m, "status", "active") != "active":
        return set()
    return set(m.roles) if m.roles is not None else set(LEGACY.get(m.role, [m.role]))


def permissions(roles):
    return (
        ALL if "owner" in roles else set().union(*(GRANTS.get(r, set()) for r in roles))
    )


def has(i, p):
    return p in permissions(i.roles)


def permit(i, p):
    if not has(i, p):
        fail("ROLE_FORBIDDEN", "当前岗位无权执行此操作", 403)


def validate_roles(values):
    values = sorted(set(values))
    if not values or set(values) - ROLE_LABELS.keys():
        fail("ROLES_INVALID", "请选择有效岗位")
    return values


ROLE_DETAILS = {
    "owner": ("全部机构业务及成员授权", "本机构全部业务；只有负责人可调整授权"),
    "admissions": (
        "招生、预约、报名订单",
        "本人负责的线索、订单和关联学员；不可收退款",
    ),
    "teacher": (
        "授课、签到、课返KPI、反馈登记",
        "本人任教班级和学员；不可排班或改课时余额",
    ),
    "scheduler": (
        "查看班级、创建和调整排课",
        "本机构排课；不含学员联系方式、签到和财务",
    ),
    "academic_admin": (
        "学员档案、分班、请假补课、课返和家庭反馈",
        "本机构教务；排课修改须另授排班权限",
    ),
    "revenue_viewer": (
        "营收总额、趋势和汇总报表",
        "仅汇总数据；不含订单、支出、票据及家长资料",
    ),
    "finance": ("订单、收退款、费用、票据和结算", "本机构财务；不含教学内容及家庭反馈"),
    "content_ops": ("内容生产、自媒体发布和复盘", "本机构自媒体；不含教务和财务"),
}


def authorization_catalog():
    return [
        {
            "key": key,
            "label": ROLE_LABELS[key],
            "description": detail[0],
            "scope": detail[1],
            "permissions": sorted(permissions({key})),
        }
        for key, detail in ROLE_DETAILS.items()
    ]


def identity_for(s, t, user_id):
    m = s.exec(
        select(Membership).where(
            Membership.tenant_id == t.id, Membership.user_id == user_id
        ).execution_options(populate_existing=True)
    ).first()
    u = s.get(User, user_id, populate_existing=True)
    rs = member_roles(m)
    if not u or u.disabled or not u.verified or not rs:
        fail("ROLE_REVOKED", "任务发起人的权限已失效", 403)
    return SimpleNamespace(session=s, tenant=t, user=u, roles=rs)


class Scope:
    def __init__(self, i):
        self.i = i
        self.roles = i.roles
        self.rows = {
            r.id: r
            for r in i.session.exec(
                select(Record).where(Record.tenant_id == i.tenant.id)
            ).all()
        }
        self.classes = {
            r.id
            for r in self.rows.values()
            if r.kind == "class" and r.data.get("teacher_id") == i.user.id
        }
        self.enrollments = {
            r.id
            for r in self.rows.values()
            if r.kind == "enrollment" and r.data.get("class_id") in self.classes
        }
        self.students = {self.rows[x].data.get("student_id") for x in self.enrollments}
        self.sales_students = {
            r.data.get("student_id")
            for r in self.rows.values()
            if r.kind == "order" and r.data.get("owner_id") == i.user.id
        }

    def visible(self, r, action="read"):
        if not has(self.i, f"{r.kind}.{action}"):
            return False
        k, d, rs = r.kind, r.data, self.roles
        if "owner" in rs:
            return True
        if k == "knowledge" and not rs & {"content_ops", "academic_admin"}:
            return bool(d.get("approved"))
        if k in ("lead", "order"):
            return (
                (k == "order" and "finance" in rs)
                or (k == "order" and "academic_admin" in rs and action == "read")
                or ("admissions" in rs and d.get("owner_id") == self.i.user.id)
            )
        if k == "student":
            return (
                "academic_admin" in rs
                or ("finance" in rs and action == "read")
                or ("teacher" in rs and r.id in self.students and action == "read")
                or (
                    "admissions" in rs
                    and (r.id in self.sales_students or r.created_by == self.i.user.id)
                )
            )
        if k == "family_feedback":
            return "academic_admin" in rs or (
                "teacher" in rs
                and d.get("class_id") in self.classes
                and d.get("student_id") in self.students
                and (
                    action == "read"
                    or (r.created_by == self.i.user.id and d.get("status") == "open")
                )
            )
        if k == "feedback" and "academic_admin" not in rs:
            if action == "write" and d.get("status", "draft") != "draft":
                return False
            lesson = self.rows.get(d.get("lesson_id"))
            if lesson and lesson.data.get("class_id") not in self.classes:
                return False
            if not lesson and r.created_by != self.i.user.id:
                return False
        if k in ("class", "lesson", "enrollment", "feedback", "leave"):
            if "scheduler" in rs and k in ("class", "lesson"):
                return True
            if "academic_admin" in rs:
                return True
            if "teacher" not in rs:
                return False
            return {
                "class": r.id in self.classes,
                "lesson": d.get("class_id") in self.classes,
                "enrollment": r.id in self.enrollments,
                "feedback": d.get("student_id") in self.students,
                "leave": d.get("enrollment_id") in self.enrollments,
            }[k]
        return True

    def own(self, rid, kind=None, action="read"):
        r = self.rows.get(rid)
        if not r or (kind and r.kind != kind) or not self.visible(r, action):
            fail("NOT_FOUND", "记录不存在或不在负责范围内", 404)
        return r

    def list(self, kind):
        permit(self.i, kind + ".read")
        return [r for r in self.rows.values() if r.kind == kind and self.visible(r)]

    def project(self, r):
        from .domain import view_record

        out = view_record(self.i.session, r)
        d = out["data"]
        if r.kind == "family_feedback":
            out["can_edit"] = self.visible(r, "write")
        rs = self.roles
        if "owner" not in rs:
            if r.kind == "order" and not rs & {"admissions", "finance"}:
                out["data"] = {
                    k: v
                    for k, v in d.items()
                    if k in ("name", "student_id", "course_id")
                }
                out["data"]["payment_status"] = (
                    "paid" if d.get("paid_fen", 0) >= d.get("due_fen", 1) else "unpaid"
                )
            elif r.kind == "order" and "finance" not in rs:
                out["data"] = {
                    k: v
                    for k, v in d.items()
                    if not k.startswith("commission") and k != "deduction_fen"
                }
            elif (
                r.kind == "student"
                and "finance" in rs
                and not (
                    "academic_admin" in rs
                    or ("teacher" in rs and r.id in self.students)
                    or (
                        "admissions" in rs
                        and (
                            r.id in self.sales_students
                            or r.created_by == self.i.user.id
                        )
                    )
                )
            ):
                out["data"] = {
                    k: v for k, v in d.items() if k in ("name", "grade", "guardian")
                }
            elif r.kind == "enrollment":
                out["data"] = {k: v for k, v in d.items() if k != "order_id"}
        out["data"].pop("custom_fields", None)
        from .studio import custom_record_values

        full_student = (
            r.kind != "student"
            or "owner" in rs
            or "academic_admin" in rs
            or ("teacher" in rs and r.id in self.students)
            or (
                "admissions" in rs
                and (r.id in self.sales_students or r.created_by == self.i.user.id)
            )
        )
        custom = custom_record_values(self.i, r.id) if full_student else []
        if custom:
            out["data"]["custom_forms"] = custom
        return out

    def validate_write(self, kind, data, old=None):
        permit(self.i, kind + ".write")
        if old:
            from .schemas import RECORD_SCHEMAS

            allowed = RECORD_SCHEMAS[kind].model_fields
            for k in list(data):
                if k not in allowed and k in old.data:
                    if data[k] != old.data[k]:
                        fail("MANAGED_FIELD", "系统业务状态不可直接修改")
                    data.pop(k)
        if data.get("custom_fields"):
            fail("FORM_REQUIRED", "扩展字段请通过已发布表单填写")
        if kind == "family_feedback":
            if old and any(
                data.get(k, old.data.get(k)) != old.data.get(k)
                for k in ("student_id", "class_id")
            ):
                fail("FEEDBACK_REFERENCE_LOCKED", "反馈关联学员和班级不能替换")
            class_id = data.get("class_id", old.data.get("class_id", "") if old else "")
            student_id = data.get(
                "student_id", old.data.get("student_id", "") if old else ""
            )
            if not self.roles & {"owner", "academic_admin"}:
                if class_id not in self.classes or student_id not in self.students:
                    fail("ROLE_FORBIDDEN", "只能登记任教班级内学员的反馈", 403)
                if data.get("status", "open") != "open":
                    fail("ROLE_FORBIDDEN", "反馈处理结果由教务或负责人确认", 403)
            if class_id and not any(
                e.kind == "enrollment"
                and e.data.get("student_id") == student_id
                and (
                    e.data.get("class_id") == class_id
                    or any(
                        h.get("class_id") == class_id for h in e.data.get("history", [])
                    )
                )
                for e in self.rows.values()
            ):
                fail("REFERENCE_INVALID", "学员与所选班级没有在读或历史关联")
        if kind in ("course", "feedback") and not self.i.tenant.settings.get(
            "legacy_maintenance", False
        ):
            fail(
                "FEATURE_RETIRED",
                "课程包和课返内容维护已停用，请使用报名单及课返KPI",
                403,
            )
        if old:
            self.own(old.id, kind, "write")
        if kind == "enrollment" and old:
            for key in ("student_id", "order_id", "course_id"):
                if data.get(key, old.data.get(key, "")) != old.data.get(key, ""):
                    fail("ENROLLMENT_LOCKED", "已确认报名的学员和订单不能替换")
            if data.get("class_id", "") != old.data.get("class_id", ""):
                fail("TRANSFER_REQUIRED", "请使用调班操作，保留生效日期和历史")
        if kind in ("lead", "order"):
            if old and "owner_id" not in data:
                data["owner_id"] = old.data.get("owner_id", "")
            if not old and "admissions" in self.roles and "owner" not in self.roles:
                data["owner_id"] = self.i.user.id
            if (
                old
                and data.get("owner_id", old.data.get("owner_id", ""))
                != old.data.get("owner_id", "")
                and "owner" not in self.roles
            ):
                fail("ROLE_FORBIDDEN", "只有负责人可以转交业务", 403)
            owner = data.get("owner_id")
            if owner:
                m = self.i.session.exec(
                    select(Membership).where(
                        Membership.tenant_id == self.i.tenant.id,
                        Membership.user_id == owner,
                    )
                ).first()
                if not member_roles(m) & {"owner", "admissions"}:
                    fail("OWNER_INVALID", "负责人须为本机构有效招生人员")
        if data.get("lead_id"):
            if has(self.i, "lead.read"):
                self.own(data["lead_id"], "lead")
            elif (
                data["lead_id"] not in self.rows
                or self.rows[data["lead_id"]].kind != "lead"
            ):
                fail("REFERENCE_INVALID", "招生线索不存在")
        for key, target in [
            ("student_id", "student"),
            ("class_id", "class"),
            ("lesson_id", "lesson"),
            ("enrollment_id", "enrollment"),
        ]:
            if data.get(key):
                if (
                    key == "class_id"
                    and kind in ("order", "expense", "lead")
                    and (has(self.i, "finance.write") or has(self.i, "lead.write"))
                ):
                    obj = self.rows.get(data[key])
                    if not obj or obj.kind != "class":
                        fail("REFERENCE_INVALID", "班级不存在", 404)
                else:
                    self.own(data[key], target)
        if data.get("asset_id"):
            from .domain import own
            from .models import Asset

            check_asset(
                self.i, own(self.i.session, Asset, self.i.tenant.id, data["asset_id"])
            )
        if data.get("teacher_id"):
            m = self.i.session.exec(
                select(Membership).where(
                    Membership.tenant_id == self.i.tenant.id,
                    Membership.user_id == data["teacher_id"],
                )
            ).first()
            if not member_roles(m) & {"owner", "teacher"}:
                fail("TEACHER_INVALID", "请选择本机构有效教师")
        if (
            kind == "leave"
            and old
            and "academic_admin" not in self.roles
            and "owner" not in self.roles
            and old.data.get("status") != "requested"
        ):
            fail("ROLE_FORBIDDEN", "已审批的请假只能由教务调整", 403)
        if (
            kind == "leave"
            and self.roles == {"teacher"}
            and data.get("status", "requested") != "requested"
        ):
            fail("ROLE_FORBIDDEN", "请假审批由教务处理", 403)
        if (
            kind == "feedback"
            and "owner" not in self.roles
            and "academic_admin" not in self.roles
            and data.get("status", "draft") != "draft"
        ):
            fail("ROLE_FORBIDDEN", "课堂反馈需教务审核", 403)
        return data


def conversation_visible(i, c):
    if "owner" in i.roles:
        return True
    if "content_ops" in i.roles and c.channel in ("xiaohongshu", "douyin", "channels"):
        return True
    if "admissions" not in i.roles:
        return False
    if c.lead_id:
        r = i.session.get(Record, c.lead_id)
        return bool(
            r and r.tenant_id == i.tenant.id and r.data.get("owner_id") == i.user.id
        )
    return c.owner_id == i.user.id


def check_conversation(i, c):
    permit(i, "conversation.read")
    if not conversation_visible(i, c):
        fail("NOT_FOUND", "会话不存在或未分配给您", 404)
    return c


def run_permission(kind):
    return {
        "connection_test": "integration.manage",
        "report_summary": "tenant.manage",
        "feedback": "feedback.write",
        "ocr": "finance.write",
        "knowledge_index": "knowledge.write",
        "chat": "conversation.write",
        "rubric_review": "rubric.manage",
    }.get(kind, "content.write")


def check_run(i, run):
    permit(i, run_permission(run.kind))
    if run.kind in ("chat", "wecom_event"):
        from .operations import consultation

        consultation(i.tenant)
    if run.kind == "feedback" and not i.tenant.settings.get(
        "legacy_maintenance", False
    ):
        fail("FEATURE_RETIRED", "课返内容生成已停用，请记录课返KPI", 403)
    if run.kind == "feedback":
        Scope(i).own(run.input.get("feedback_id"), "feedback", "write")
    if run.kind == "chat":
        from .models import Conversation

        c = i.session.get(Conversation, run.input.get("conversation_id"))
        if not c or c.tenant_id != i.tenant.id:
            fail("NOT_FOUND", "会话不存在", 404)
        check_conversation(i, c)
    return True


def asset_allowed(i, a):
    if "owner" in i.roles:
        return True
    if "/receipt/" in a.object_key:
        return has(i, "finance.read")
    if "/content/" in a.object_key:
        return has(i, "content.read")
    from .domain import query
    from .models import AdmissionImport
    from .studio import form_asset_access, unseal

    batch = i.session.exec(
        query(i.session, AdmissionImport, i.tenant.id).where(
            AdmissionImport.asset_id == a.id
        )
    ).first()
    if batch:
        if not has(i, "lead.read"):
            return False
        rows = unseal(i.tenant.id, batch.rows_cipher) if batch.rows_cipher else []
        imported = [
            row.get("record_id") for row in rows if row.get("status") == "imported"
        ]
        scope = Scope(i)
        if imported and not all(
            rid in scope.rows and scope.visible(scope.rows[rid]) for rid in imported
        ):
            return False
        return batch.actor_id == i.user.id or (
            bool(imported) and len(imported) == len(rows)
        )
    access = form_asset_access(i, a.id)
    return access if access is not None else a.uploaded_by == i.user.id


def check_asset(i, a):
    if not asset_allowed(i, a):
        fail("NOT_FOUND", "附件不存在或无访问权限", 404)


def check_job(i, kind, obj):
    if kind == "agent":
        return check_run(i, obj)
    permit(i, "publish.read" if kind == "publish" else "content.read")
    return True

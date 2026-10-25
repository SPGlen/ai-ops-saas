"""Synthetic staff fixtures; never available in production."""

from datetime import timedelta
from sqlmodel import select
from .models import *
from .security import password_hash
from .domain import create_record, record_money
from .db import set_scope
from .permissions import ROLE_LABELS

PASSWORD = "Demo-Staff-2026!"


def seed_staff(s):
    for slug, code in [("qinghe-demo", "qinghe"), ("xingguang-demo", "xingguang")]:
        t = s.exec(select(Tenant).where(Tenant.slug == slug)).first()
        if not t:
            continue
        set_scope(s, t.id)
        people = {}
        specs = [
            ("owner", ["owner"]),
            ("admissions1", ["admissions"]),
            ("admissions2", ["admissions"]),
            ("content", ["content_ops"]),
            ("academic", ["academic_admin"]),
            ("teacher1", ["teacher"]),
            ("teacher2", ["teacher"]),
            ("finance", ["finance"]),
            ("scheduler", ["scheduler"]),
            ("revenue", ["revenue_viewer"]),
            ("combined", ["teacher", "finance"]),
        ]
        for name, rs in specs:
            email = name + "." + code + "@zhiying.example"
            u = s.exec(select(User).where(User.email == email)).first()
            if not u:
                u = User(
                    email=email,
                    name=("青禾" if code == "qinghe" else "星光")
                    + " · "
                    + (
                        "教师一"
                        if name == "teacher1"
                        else "教师二"
                        if name == "teacher2"
                        else "招生一"
                        if name == "admissions1"
                        else "招生二"
                        if name == "admissions2"
                        else "教师兼财务"
                        if name == "combined"
                        else ROLE_LABELS[rs[0]]
                    ),
                    verified=True,
                    password_hash=password_hash(PASSWORD),
                )
                s.add(u)
                s.flush()
                s.add(Membership(tenant_id=t.id, user_id=u.id, role=rs[0], roles=rs))
            people[name] = u
        s.flush()
        marker = "员工权限演示课程"
        exists = s.exec(
            select(Record).where(Record.tenant_id == t.id, Record.kind == "course")
        ).all()
        if any(r.data.get("name") == marker for r in exists):
            s.commit()
            continue
        actor = people["owner"].id
        course = create_record(
            s,
            t.id,
            actor,
            "course",
            {
                "name": marker,
                "price_fen": 198000,
                "lessons": 8,
                "approved": True,
                "description": "仅供本地验证机构与岗位权限的虚构课程。",
            },
        )
        for idx in (1, 2):
            teacher = people["teacher" + str(idx)]
            sales = people["admissions" + str(idx)]
            school_class = create_record(
                s,
                t.id,
                actor,
                "class",
                {
                    "name": "权限演示班" + str(idx),
                    "course_id": course.id,
                    "teacher_id": teacher.id,
                },
            )
            lesson = create_record(
                s,
                t.id,
                actor,
                "lesson",
                {
                    "name": "权限演示课" + str(idx),
                    "class_id": school_class.id,
                    "starts_at": (now() + timedelta(days=idx)).isoformat(),
                },
            )
            student = create_record(
                s,
                t.id,
                actor,
                "student",
                {
                    "name": "演示学员" + str(idx),
                    "grade": "二年级",
                    "guardian": "演示家长",
                    "contact": "1390000000" + str(idx),
                    "notes": "虚构教学资料",
                },
            )
            order = create_record(
                s,
                t.id,
                actor,
                "order",
                {
                    "name": "演示报名" + str(idx),
                    "student_id": student.id,
                    "course_id": course.id,
                    "owner_id": sales.id,
                },
            )
            record_money(
                s,
                t.id,
                actor,
                order.id,
                "payment",
                198000,
                "demo-staff-payment-" + str(idx),
                "开发演示，不是真实收款",
            )
            create_record(
                s,
                t.id,
                actor,
                "enrollment",
                {
                    "student_id": student.id,
                    "course_id": course.id,
                    "class_id": school_class.id,
                    "order_id": order.id,
                },
            )
            create_record(
                s,
                t.id,
                actor,
                "lead",
                {
                    "name": "演示线索" + str(idx),
                    "contact": "1390000000" + str(idx),
                    "owner_id": sales.id,
                    "source": "岗位权限演示",
                },
            )
        s.commit()

"""Operator tools; secrets are accepted through prompts or environment, never CLI arguments."""

import argparse, json, os, getpass, re
from pathlib import Path
from datetime import timedelta
from sqlmodel import Session, select
from .config import settings
from .db import engine, initialize, set_scope
from .models import *
from .security import password_hash, password_valid
from .domain import create_record, record_money, attend, save_content, audit
from .schemas import ContentInput


def admin():
    email = input("Administrator email: ").strip().lower()
    password = getpass.getpass("Password (12+ characters): ")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters")
    with Session(engine()) as session:
        user = session.exec(select(User).where(User.email == email)).first()
        if user:
            if (
                not user.verified
                or user.disabled
                or not password_valid(password, user.password_hash)
            ):
                raise SystemExit(
                    "Existing account must be verified, active and authenticated with its current password; no changes made"
                )
            user.platform_admin = True
        else:
            user = User(
                email=email,
                name="平台管理员",
                password_hash=password_hash(password),
                verified=True,
                platform_admin=True,
            )
        session.add(user)
        session.commit()
        print("Administrator configured; existing user password was preserved.")


def demo():
    if settings().production:
        raise SystemExit("Demo initialization is disabled in production")
    initialize()
    with Session(engine(), expire_on_commit=False) as session:
        if session.exec(
            select(User).where(User.email == "demo@zhiying.example")
        ).first():
            from .demo_staff import seed_staff

            seed_staff(session)
            print("Demo exists; staff fixtures verified.")
            return
        config = session.get(PlatformSettings, 1) or PlatformSettings()
        config.free_until = now() + timedelta(days=30)
        config.plans = {
            "catalog": [
                {
                    "id": "foundation",
                    "term_days": 30,
                    "price_fen": 0,
                    "quotas": {},
                    "name": "机构基础版",
                    "enabled": False,
                }
            ],
            "prices": {
                "text_million_fen": 1000,
                "image_fen": 20,
                "video_second_fen": 60,
            },
        }
        session.add(config)
        user = User(
            email="demo@zhiying.example",
            name="林老师",
            password_hash=password_hash("Demo-Zhiying-2026!"),
            verified=True,
            platform_admin=True,
        )
        session.add(user)
        session.flush()
        for n in range(2):
            tenant = Tenant(
                name=["青禾 AI 教育 · 演示机构", "星光课堂 · 演示机构"][n],
                slug=["qinghe-demo", "xingguang-demo"][n],
                settings={
                    "brand": "用真实的课程与创作，帮助孩子认识AI。示例资料，仅供演示。",
                    "audience": "小学1至6年级家长",
                    "tone": "清楚、真实、有用",
                    "quotas": {},
                    "funding": "platform",
                    "publishing_enabled": False,
                    "auto_publish": False,
                },
            )
            session.add(tenant)
            session.flush()
            set_scope(session, tenant.id, user.id)
            session.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))
            course = create_record(
                session,
                tenant.id,
                user.id,
                "course",
                {
                    "name": "AI创想启蒙 · 八次探索课",
                    "price_fen": 198000,
                    "lessons": 8,
                    "approved": True,
                    "description": "在八次创作实践中认识AI，通过观察、提问、作品制作理解工具的能力与边界。示例课程安排，适合小学低年级。",
                },
            )
            cls = create_record(
                session,
                tenant.id,
                user.id,
                "class",
                {
                    "name": "周六创想班",
                    "course_id": course.id,
                    "teacher_id": user.id,
                    "capacity": 15,
                },
            )
            channel = create_record(
                session,
                tenant.id,
                user.id,
                "channel",
                {
                    "name": "社区课程合作点",
                    "commission_bps": 0,
                    "confirmed": True,
                    "notes": "示例渠道，比例待正式合作确认，当前为0。",
                },
            )
            for j in range(2):
                student = create_record(
                    session,
                    tenant.id,
                    user.id,
                    "student",
                    {
                        "name": ["小禾（示例）", "小星（示例）"][j],
                        "grade": ["二年级", "三年级"][j],
                        "guardian": ["禾妈妈", "星爸爸"][j],
                        "contact": "demo-contact-" + str(j),
                        "notes": "虚构示例学员",
                    },
                )
                order = create_record(
                    session,
                    tenant.id,
                    user.id,
                    "order",
                    {
                        "name": "创想课报名 · " + student.data["name"],
                        "student_id": student.id,
                        "course_id": course.id,
                        "channel_id": channel.id,
                        "discount_fen": 0,
                    },
                )
                record_money(
                    session,
                    tenant.id,
                    user.id,
                    order.id,
                    "payment",
                    198000,
                    "demo-payment-" + order.id,
                    "演示收款，非真实交易",
                )
                create_record(
                    session,
                    tenant.id,
                    user.id,
                    "enrollment",
                    {
                        "student_id": student.id,
                        "course_id": course.id,
                        "class_id": cls.id,
                        "order_id": order.id,
                    },
                )
            for j in range(4):
                create_record(
                    session,
                    tenant.id,
                    user.id,
                    "lesson",
                    {
                        "name": "第" + str(j + 1) + "课 · AI的观察与表达",
                        "class_id": cls.id,
                        "starts_at": (now() + timedelta(days=j * 7 + 2)).isoformat(),
                        "duration_minutes": 90,
                    },
                )
            for j in range(6):
                row = create_record(
                    session,
                    tenant.id,
                    user.id,
                    "lead",
                    {
                        "name": [
                            "陈女士",
                            "李先生",
                            "周女士",
                            "许先生",
                            "方女士",
                            "唐先生",
                        ][j]
                        + "（示例）",
                        "contact": "demo-inquiry-" + str(j),
                        "grade": ["一年级", "二年级", "三年级"][j % 3],
                        "source": ["小红书", "合作机构", "家长转介绍"][j % 3],
                        "need": "希望了解AI体验课的安排",
                        "stage": ["new", "booked", "contacted"][j % 3],
                        "followup_at": (now() + timedelta(hours=j + 1)).isoformat(),
                    },
                )
                row.created_at = now() - timedelta(days=j)
                session.add(row)
            create_record(
                session,
                tenant.id,
                user.id,
                "knowledge",
                {
                    "name": "课程与试听说明（演示）",
                    "body": "AI创想启蒙课程共8次，每次90分钟，示例价格1980元。课程围绕观察、提问和作品创作。家长可以预约试听，由老师确认具体时间。不承诺获奖或提分。",
                    "approved": True,
                },
            )
            for title in [
                "孩子学AI，先从提出一个好问题开始",
                "一次亲子小实验：让AI描述窗外的树",
                "如何和孩子聊AI生成的内容",
            ]:
                create_record(
                    session,
                    tenant.id,
                    user.id,
                    "topic",
                    {"name": title, "source": "家长问题整理"},
                )
            save_content(
                session,
                tenant.id,
                user.id,
                ContentInput(
                    title="第一次接触AI，先学会问一个好问题",
                    body="和孩子一起观察身边的事物，试着把看到的颜色、形状和变化说清楚。再请AI补充一个新角度，比较它的回答与真实观察有什么不同。\n\n在AI创想启蒙课程中，我们通过提问与作品创作认识工具的能力与边界。共8次课程，家长可以先预约试听。\n\n演示文案，未连接任何发布账号。",
                ),
            )
            audit(session, tenant.id, user.id, "demo.initialize", tenant.id)
            session.commit()
        print("Development demo ready: demo@zhiying.example / Demo-Zhiying-2026!")


def import_skill(path, tenant_id, actor_id):
    """Allowlisted, read-only schema 1.4 import. No recursive copy or credential discovery."""
    root = Path(path).resolve()
    state = json.loads((root / ".cheat-state.json").read_text(encoding="utf-8-sig"))
    schema = str(state.get("schema_version", state.get("schema", "")))
    if schema != "1.4":
        raise SystemExit("Only schema 1.4 imports are supported")
    docs = [
        "audience.md",
        "script_patterns.md",
        "rubric_notes.md",
        "benchmark.md",
        "candidates.md",
    ]
    imported = []
    with Session(engine(), expire_on_commit=False) as session:
        tenant = session.get(Tenant, tenant_id)
        member = session.exec(
            select(Membership).where(
                Membership.user_id == actor_id,
                Membership.tenant_id == tenant_id,
                Membership.role == "owner",
            )
        ).first()
        if not tenant or not member:
            raise SystemExit("An active owner membership is required")
        set_scope(session, tenant_id, actor_id)
        for filename in docs:
            file = (root / filename).resolve()
            if (
                not file.is_relative_to(root)
                or not file.is_file()
                or file.stat().st_size > 256000
            ):
                continue
            body = file.read_text(encoding="utf-8-sig")
            if re.search(
                r"(?i)(api[_-]?key|access[_-]?token|cookie|password|authorization)\s*[:=]",
                body,
            ):
                raise SystemExit(
                    "Possible credential in "
                    + filename
                    + "; prepare a sanitized import directory"
                )
            record = create_record(
                session,
                tenant_id,
                actor_id,
                "knowledge",
                {
                    "name": "只读导入 · " + filename,
                    "body": body[:30000],
                    "approved": False,
                },
            )
            imported.append(record.id)
        audit(
            session,
            tenant_id,
            actor_id,
            "skill.import",
            tenant_id,
            schema="1.4",
            files=docs,
            records=imported,
        )
        session.commit()
    print(
        json.dumps(
            {
                "imported_records": imported,
                "review_required": True,
                "source_unchanged": True,
            },
            ensure_ascii=False,
        )
    )


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "demo", "admin", "openapi"):
        commands.add_parser(name)
    imp = commands.add_parser("import-skill")
    imp.add_argument("path")
    imp.add_argument("--tenant", required=True)
    imp.add_argument("--owner", required=True)
    args = parser.parse_args()
    settings().validate_runtime()
    if args.command == "init":
        initialize()
    elif args.command == "demo":
        demo()
        from .demo_staff import seed_staff

        with Session(engine()) as session:
            seed_staff(session)
    elif args.command == "admin":
        admin()
    elif args.command == "import-skill":
        import_skill(args.path, args.tenant, args.owner)
    else:
        from .main import app

        target = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
        target.write_text(
            json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf8"
        )
        print("OpenAPI exported to docs/openapi.json")


if __name__ == "__main__":
    main()

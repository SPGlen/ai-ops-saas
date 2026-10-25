from datetime import datetime
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Register(Strict):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    name: str = Field(min_length=1, max_length=50)
    tenant_name: str = Field(min_length=2, max_length=80)


class Login(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Course(Strict):
    name: str = Field(min_length=1, max_length=100)
    price_fen: int = Field(default=198000, ge=0, le=100000000)
    lessons: int = Field(default=8, ge=1, le=500)
    description: str = Field(default="", max_length=10000)
    approved: bool = False


class Guardian(Strict):
    name: str = Field(min_length=1, max_length=50)
    relationship: str = Field(default="家长", max_length=30)
    contact: str = Field(default="", max_length=100)


class Student(Strict):
    name: str = Field(min_length=1, max_length=50)
    grade: str = Field(default="", max_length=20)
    guardians: list[Guardian] = Field(default_factory=list, max_length=10)
    guardian: str = Field(default="", max_length=50)
    contact: str = Field(default="", max_length=100)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=2000)


class Lead(Strict):
    student_name: str = Field(default="", max_length=50)
    relationship: str = Field(default="家长", max_length=30)
    loss_reason: str = Field(default="", max_length=1000)
    class_id: str = ""
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    name: str = Field(min_length=1, max_length=50)
    contact: str = Field(min_length=3, max_length=100)
    grade: str = Field(default="", max_length=20)
    city: str = Field(default="", max_length=50)
    need: str = Field(default="", max_length=2000)
    contact_time: str = Field(default="", max_length=100)
    source: str = Field(default="直接预约", max_length=200)
    stage: Literal["new", "contacted", "booked", "attended", "won", "lost"] = "new"
    owner_id: str = ""
    followup_at: str = ""
    trial_at: str = ""
    notes: str = Field(default="", max_length=2000)


class PublicLead(Strict):
    name: str = Field(min_length=1, max_length=50)
    contact: str = Field(min_length=3, max_length=100)
    grade: str = Field(default="", max_length=20)
    city: str = Field(default="", max_length=50)
    need: str = Field(default="", max_length=2000)
    contact_time: str = Field(default="", max_length=100)
    source: str = Field(default="直接预约", max_length=200)
    consent: Literal[True]
    website: str = Field(default="", max_length=100)


class SchoolClass(Strict):
    program_name: str = Field(default="", max_length=100)
    name: str = Field(min_length=1, max_length=100)
    course_id: str = ""
    teacher_id: str = ""
    capacity: int = Field(default=15, ge=1, le=500)
    notes: str = Field(default="", max_length=2000)


class Lesson(Strict):
    name: str = Field(min_length=1, max_length=100)
    class_id: str
    starts_at: datetime
    duration_minutes: int = Field(default=90, ge=15, le=480)
    status: Literal["scheduled", "completed", "cancelled"] = "scheduled"


class Enrollment(Strict):
    student_id: str
    course_id: str = ""
    class_id: str = ""
    order_id: str = ""


class Order(Strict):
    program_name: str = Field(default="", max_length=100)
    price_fen: int = Field(default=0, ge=0, le=100000000)
    purchased_units: int = Field(default=8, ge=1, le=5000)
    class_id: str = ""
    lead_id: str = ""
    owner_id: str = ""
    name: str = Field(min_length=1, max_length=100)
    student_id: str
    course_id: str = ""
    discount_fen: int = Field(default=0, ge=0, le=100000000)
    channel_id: str = ""
    notes: str = Field(default="", max_length=2000)


class Expense(Strict):
    channel_id: str = ""
    class_id: str = ""
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    name: str = Field(min_length=1, max_length=100)
    amount_fen: int = Field(ge=0, le=100000000)
    category: str = Field(default="运营费用", max_length=50)
    date: str = Field(default="", max_length=30)
    asset_id: str = ""
    status: Literal["draft", "confirmed"] = "draft"
    notes: str = Field(default="", max_length=2000)


class Channel(Strict):
    name: str = Field(min_length=1, max_length=100)
    commission_bps: int = Field(default=0, ge=0, le=10000)
    basis: Literal["net_cash", "after_fixed_cost"] = "net_cash"
    deduction_fen: int = Field(default=0, ge=0, le=100000000)
    effective_from: datetime | None = None
    confirmed: bool = False
    notes: str = Field(default="", max_length=2000)


class Knowledge(Strict):
    name: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=30000)
    approved: bool = False
    source_url: str = Field(default="", max_length=1000)


class Topic(Strict):
    name: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=10000)
    source: str = Field(default="manual", max_length=300)
    form: Literal["image_text", "video"] = "image_text"
    status: Literal["candidate", "selected", "done", "rejected"] = "candidate"


class Campaign(Strict):
    name: str = Field(min_length=1, max_length=100)
    objective: str = Field(default="", max_length=2000)
    platforms: list[Literal["xiaohongshu", "douyin", "channels"]] = Field(
        default_factory=list, max_length=3
    )
    form: Literal["image_text", "video"] = "video"
    enabled: bool = False
    funding: Literal["platform", "byok"] = "platform"
    interval_days: int = Field(default=3, ge=1, le=30)
    hour: int = Field(default=18, ge=0, le=23)
    next_run_at: datetime | None = None


class Feedback(Strict):
    name: str = Field(min_length=1, max_length=100)
    student_id: str
    lesson_id: str = ""
    teacher_note: str = Field(default="", max_length=3000)
    body: str = Field(default="", max_length=5000)
    status: Literal["draft", "approved", "sent"] = "draft"


class FamilyFeedback(Strict):
    name: str = Field(min_length=1, max_length=100)
    student_id: str
    class_id: str = ""
    respondent: Literal["parent", "student"] = "parent"
    category: Literal["teaching", "schedule", "service", "other"] = "teaching"
    rating: int | None = Field(default=None, ge=1, le=5)
    body: str = Field(min_length=1, max_length=3000)
    recorded_at: datetime | None = None
    status: Literal["open", "resolved"] = "open"
    resolution: str = Field(default="", max_length=2000)


class Community(Strict):
    outcome: str = Field(default="", max_length=2000)
    name: str = Field(min_length=1, max_length=100)
    audience: str = Field(default="", max_length=1000)
    body: str = Field(default="", max_length=3000)
    status: Literal["draft", "approved", "sent"] = "draft"
    due_at: str = ""
    channel: str = "manual"


RECORD_SCHEMAS = {
    "course": Course,
    "student": Student,
    "lead": Lead,
    "class": SchoolClass,
    "lesson": Lesson,
    "enrollment": Enrollment,
    "order": Order,
    "expense": Expense,
    "channel": Channel,
    "knowledge": Knowledge,
    "topic": Topic,
    "campaign": Campaign,
    "feedback": Feedback,
    "community": Community,
    "family_feedback": FamilyFeedback,
}
READ_ROLES = {
    "course": {"owner", "operator", "teacher", "finance"},
    "student": {"owner", "operator", "teacher", "finance"},
    "lead": {"owner", "operator"},
    "class": {"owner", "operator", "teacher"},
    "lesson": {"owner", "operator", "teacher"},
    "enrollment": {"owner", "operator", "teacher", "finance"},
    "order": {"owner", "operator", "finance"},
    "expense": {"owner", "finance"},
    "channel": {"owner", "operator", "finance"},
    "knowledge": {"owner", "operator", "teacher"},
    "topic": {"owner", "operator"},
    "campaign": {"owner", "operator"},
    "feedback": {"owner", "operator", "teacher"},
    "community": {"owner", "operator"},
}
WRITE_ROLES = {k: v - {"teacher", "finance"} for k, v in READ_ROLES.items()}
WRITE_ROLES.update(
    {
        "expense": {"owner", "finance"},
        "order": {"owner", "operator", "finance"},
        "channel": {"owner", "finance"},
        "feedback": {"owner", "teacher", "operator"},
        "lesson": {"owner", "operator", "teacher"},
    }
)


class RecordInput(Strict):
    workflow_id: str = ""
    data: dict[str, Any]
    version: int | None = None


class MoneyAction(Strict):
    request_id: str = Field(min_length=8, max_length=100)
    amount_fen: int = Field(gt=0, le=100000000)
    note: str = Field(default="", max_length=500)


class ActionId(Strict):
    request_id: str = Field(min_length=8, max_length=100)


class RunInput(Strict):
    kind: Literal[
        "report_summary",
        "content",
        "predict",
        "feedback",
        "ocr",
        "knowledge_index",
        "rubric_review",
        "retro",
    ]
    request_id: str = Field(min_length=8, max_length=100)
    funding: Literal["platform", "byok"] | None = None
    input: dict[str, Any] = Field(default_factory=dict)


class MediaInput(Strict):
    kind: Literal["image", "video"]
    prompt: str = Field(min_length=2, max_length=4000)
    request_id: str = Field(min_length=8, max_length=100)
    funding: Literal["platform", "byok"] | None = None
    duration: int = Field(default=10, ge=2, le=15)
    content_id: str = ""
    narration: str = Field(default="", max_length=600)
    ratio: Literal["9:16", "16:9", "1:1", "3:4"] = "9:16"


class ContentInput(Strict):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=15000)
    form: Literal["image_text", "video"] = "image_text"
    assets: list[str] = Field(default_factory=list, max_length=20)
    version: int | None = None


class PublishInput(Strict):
    account_id: str
    scheduled_at: datetime
    request_id: str = Field(min_length=8, max_length=100)


class SecretInput(Strict):
    secret: str = Field(min_length=1, max_length=4000)
    config: dict[str, Any] = Field(default_factory=dict)


class ChatInput(Strict):
    body: str = Field(min_length=1, max_length=2000)


class MetricInput(Strict):
    plays: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    inquiries: int | None = Field(default=None, ge=0)
    bookings: int | None = Field(default=None, ge=0)
    enrollments: int | None = Field(default=None, ge=0)


class Leave(Strict):
    name: str = Field(min_length=1, max_length=100)
    enrollment_id: str
    lesson_id: str
    reason: str = Field(default="", max_length=1000)
    status: Literal["requested", "approved", "rejected", "made_up"] = "requested"
    makeup_lesson_id: str = ""


class CreditAdjustment(Strict):
    request_id: str = Field(min_length=8, max_length=100)
    delta: int = Field(ge=-100, le=100)
    reason: str = Field(min_length=5, max_length=500)


RECORD_SCHEMAS["leave"] = Leave
READ_ROLES["leave"] = {"owner", "operator", "teacher"}
WRITE_ROLES["leave"] = {"owner", "operator", "teacher"}


class Entitlement(Strict):
    active: bool
    until: datetime | None
    payment_enabled: bool = False


class TenantView(Strict):
    id: str
    name: str
    slug: str
    settings: dict[str, Any]
    entitlement: Entitlement


class MembershipView(Strict):
    id: str
    user_id: str
    name: str
    email: str
    role: str
    roles: list[str] = Field(default_factory=list)
    status: str = "active"
    authz_version: int = 1
    permissions: list[str] = Field(default_factory=list)


class Plan(Strict):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=80)
    term_days: int = Field(default=30, ge=1, le=3660)
    price_fen: int = Field(default=0, ge=0, le=100000000)
    account_limit: int = Field(default=9, ge=0, le=500)
    quotas: dict[str, int] = Field(default_factory=dict)
    enabled: bool = False


class AgentRunView(Strict):
    id: str
    tenant_id: str
    created_at: datetime
    updated_at: datetime
    kind: str
    status: str
    request_id: str
    actor_id: str
    funding: str
    output: dict[str, Any]
    error_code: str
    error: str


from .models import UsageRecord, BudgetBucket


class UsageView(Strict):
    items: list[UsageRecord]
    buckets: list[BudgetBucket]
    quotas: dict[str, int]

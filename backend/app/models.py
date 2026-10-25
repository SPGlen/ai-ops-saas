from datetime import datetime, timezone
from uuid import uuid4
from typing import Any
from sqlalchemy import Column, JSON, UniqueConstraint, ForeignKeyConstraint, Index, text
from sqlmodel import SQLModel, Field
from pgvector.sqlalchemy import Vector


def now():
    return datetime.now(timezone.utc)


def as_utc(value):
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def uid():
    return uuid4().hex


def json_field():
    return Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class User(SQLModel, table=True):
    __tablename__ = "users"
    id: str = Field(default_factory=uid, primary_key=True)
    email: str = Field(index=True, unique=True)
    name: str
    password_hash: str
    verified: bool = False
    platform_admin: bool = False
    disabled: bool = False
    created_at: datetime = Field(default_factory=now)


class Tenant(SQLModel, table=True):
    __tablename__ = "tenants"
    id: str = Field(default_factory=uid, primary_key=True)
    slug: str = Field(index=True, unique=True)
    name: str
    status: str = "active"
    free_until: datetime | None = None
    settings: dict[str, Any] = json_field()
    created_at: datetime = Field(default_factory=now)


class Membership(SQLModel, table=True):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id"),)
    id: str = Field(default_factory=uid, primary_key=True)
    tenant_id: str = Field(foreign_key="tenants.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    role: str = "operator"
    roles: list[str] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    status: str = "active"
    authz_version: int = 1


class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"
    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    csrf_hash: str
    tenant_id: str | None = None
    expires_at: datetime
    created_at: datetime = Field(default_factory=now)


class EmailToken(SQLModel, table=True):
    __tablename__ = "email_tokens"
    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id")
    purpose: str
    expires_at: datetime
    used_at: datetime | None = None


class PlatformSettings(SQLModel, table=True):
    __tablename__ = "platform_settings"
    id: int = Field(default=1, primary_key=True)
    free_until: datetime | None = None
    registration_open: bool = True
    plans: dict[str, Any] = json_field()


class RateBucket(SQLModel, table=True):
    __tablename__ = "rate_buckets"
    id: str = Field(primary_key=True)
    hits: int = 0
    window_start: datetime = Field(default_factory=now)


class Scoped(SQLModel):
    id: str = Field(default_factory=uid, primary_key=True)
    tenant_id: str = Field(foreign_key="tenants.id", index=True)
    created_at: datetime = Field(default_factory=now)


class Record(Scoped, table=True):
    __tablename__ = "records"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id"),
        Index("ix_record_kind", "tenant_id", "kind"),
    )
    kind: str = Field(index=True)
    data: dict[str, Any] = json_field()
    version: int = 1
    created_by: str
    updated_at: datetime = Field(default_factory=now)


class AuditEvent(Scoped, table=True):
    __tablename__ = "audit_events"
    actor_id: str
    action: str
    target_id: str
    detail: dict[str, Any] = json_field()


class LedgerEntry(Scoped, table=True):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id"),
        ForeignKeyConstraint(
            ["order_id", "tenant_id"], ["records.id", "records.tenant_id"]
        ),
        ForeignKeyConstraint(
            ["reverses_id", "tenant_id"],
            ["ledger_entries.id", "ledger_entries.tenant_id"],
        ),
        UniqueConstraint("id", "tenant_id"),
        UniqueConstraint("tenant_id", "reverses_id"),
    )
    order_id: str
    entry_type: str
    amount_fen: int
    request_id: str
    reverses_id: str | None = None
    note: str = ""
    actor_id: str


class CreditEntry(Scoped, table=True):
    __tablename__ = "credit_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id"),
        ForeignKeyConstraint(
            ["enrollment_id", "tenant_id"], ["records.id", "records.tenant_id"]
        ),
        UniqueConstraint("tenant_id", "reverses_id"),
        UniqueConstraint("tenant_id", "enrollment_id", "lesson_id", "kind"),
        UniqueConstraint("tenant_id", "student_id", "lesson_id", "kind"),
        ForeignKeyConstraint(
            ["student_id", "tenant_id"], ["records.id", "records.tenant_id"]
        ),
    )
    enrollment_id: str
    student_id: str | None = None
    lesson_id: str | None = None
    delta: int
    kind: str
    request_id: str
    reverses_id: str | None = None
    actor_id: str


class Integration(Scoped, table=True):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("tenant_id", "provider"),)
    provider: str
    secret_cipher: str = ""
    config: dict[str, Any] = json_field()
    active: bool = True


class Asset(Scoped, table=True):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("id", "tenant_id"),)
    object_key: str
    name: str
    mime: str
    size: int
    sha256: str
    consent: bool = False
    uploaded_by: str = ""


class Content(Scoped, table=True):
    __tablename__ = "contents"
    __table_args__ = (UniqueConstraint("id", "tenant_id"),)
    title: str
    form: str = "image_text"
    status: str = "draft"
    current_version: int = 1
    topic_id: str | None = None
    created_by: str


class ContentVersion(Scoped, table=True):
    __tablename__ = "content_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "content_id", "version"),
        ForeignKeyConstraint(
            ["content_id", "tenant_id"], ["contents.id", "contents.tenant_id"]
        ),
        UniqueConstraint("id", "tenant_id"),
    )
    content_id: str
    version: int
    title: str
    body: str
    assets: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    content_hash: str
    policy_checked: bool = False
    policy_notes: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )


class Prediction(Scoped, table=True):
    __tablename__ = "predictions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version_id"),
        ForeignKeyConstraint(
            ["version_id", "tenant_id"],
            ["content_versions.id", "content_versions.tenant_id"],
        ),
    )
    version_id: str
    content_hash: str
    rubric_version: str
    payload: dict[str, Any] = json_field()
    blind_status: str = "pre_publish"


class AgentRun(Scoped, table=True):
    __tablename__ = "agent_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "request_id"),)
    kind: str
    status: str = "queued"
    request_id: str
    actor_id: str
    funding: str = "platform"
    input: dict[str, Any] = json_field()
    output: dict[str, Any] = json_field()
    error_code: str = ""
    error: str = ""
    updated_at: datetime = Field(default_factory=now)


class MediaJob(Scoped, table=True):
    __tablename__ = "media_jobs"
    __table_args__ = (UniqueConstraint("tenant_id", "request_id"),)
    kind: str
    status: str = "queued"
    prompt: str
    funding: str = "platform"
    request_id: str
    actor_id: str
    provider_task_id: str | None = None
    provider_request_id: str | None = None
    parameters: dict[str, Any] = json_field()
    asset_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    error_code: str = ""
    error: str = ""
    updated_at: datetime = Field(default_factory=now)


class SocialAccount(Scoped, table=True):
    __tablename__ = "social_accounts"
    __table_args__ = (UniqueConstraint("id", "tenant_id"), UniqueConstraint("tenant_id", "identity_key"), ForeignKeyConstraint(["profile_id", "tenant_id"], ["media_profiles.id", "media_profiles.tenant_id"]))
    platform: str
    name: str
    status: str = "unconfigured"
    config: dict[str, Any] = json_field()
    profile_id: str | None = None
    identity_key: str | None = Field(default=None, index=True)
    paused: bool = False


class PublishJob(Scoped, table=True):
    __tablename__ = "publish_jobs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id"),
        UniqueConstraint("tenant_id", "version_id", "account_id"),
        ForeignKeyConstraint(
            ["version_id", "tenant_id"],
            ["content_versions.id", "content_versions.tenant_id"],
        ),
        ForeignKeyConstraint(
            ["account_id", "tenant_id"],
            ["social_accounts.id", "social_accounts.tenant_id"],
        ),
    )
    version_id: str
    account_id: str
    status: str = "scheduled"
    scheduled_at: datetime = Field(default_factory=now)
    actor_id: str = "scheduler"
    request_id: str
    external_id: str = ""
    external_url: str = ""
    error_code: str = ""
    error: str = ""
    retro_due_at: datetime | None = None
    submitted_at: datetime | None = None
    updated_at: datetime = Field(default_factory=now)


class MetricSnapshot(Scoped, table=True):
    __tablename__ = "metric_snapshots"
    publish_job_id: str
    metrics: dict[str, Any] = json_field()
    source: str = "manual"
    summary: str = ""
    eligible: bool = True


class UsageRecord(Scoped, table=True):
    __tablename__ = "usage_records"
    __table_args__ = (UniqueConstraint("tenant_id", "request_id", "resource"),)
    request_id: str
    resource: str
    funding: str
    reserved: int
    actual: int = 0
    cost_fen: int = 0
    unit_rate_fen: int = 0
    unit_scale: int = 1
    model_usage: dict[str, Any] = json_field()
    estimated: bool = False
    state: str = "reserved"
    period: str
    updated_at: datetime = Field(default_factory=now)


class BudgetBucket(Scoped, table=True):
    __tablename__ = "budget_buckets"
    __table_args__ = (UniqueConstraint("tenant_id", "period", "resource"),)
    period: str
    resource: str
    used: int = 0
    reserved: int = 0


class Conversation(Scoped, table=True):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("id", "tenant_id"),)
    token_hash: str
    channel: str = "web"
    external_user: str = ""
    state: str = "bot"
    title: str = "新咨询"
    owner_id: str = ""
    account_id: str = ""
    external_thread_id: str = ""
    source_work_id: str = ""
    interaction_kind: str = "private_message"
    lead_id: str | None = None
    tags: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )


class Message(Scoped, table=True):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_id"),
        ForeignKeyConstraint(
            ["conversation_id", "tenant_id"],
            ["conversations.id", "conversations.tenant_id"],
        ),
    )
    conversation_id: str
    role: str
    body: str
    external_id: str | None = None
    sources: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    delivery_state: str = "local"


class KnowledgeChunk(Scoped, table=True):
    __tablename__ = "knowledge_chunks"
    record_id: str
    title: str
    body: str
    version: int = 1
    embedding: list[float] | None = Field(
        default=None,
        sa_column=Column(Vector(1024).with_variant(JSON(), "sqlite"), nullable=True),
    )


class WebhookReceipt(Scoped, table=True):
    __tablename__ = "webhook_receipts"
    __table_args__ = (UniqueConstraint("tenant_id", "external_id"),)
    external_id: str
    body_hash: str


class RubricCandidate(Scoped, table=True):
    __tablename__ = "rubric_candidates"
    profile_id: str | None = None
    form: str
    weights: dict[str, Any] = json_field()
    notes: str
    status: str = "queued"
    corpus_hash: str
    report: dict[str, Any] = json_field()
    reviewed_at: datetime | None = None


class Settlement(Scoped, table=True):
    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_id", "period"),
        ForeignKeyConstraint(
            ["channel_id", "tenant_id"], ["records.id", "records.tenant_id"]
        ),
    )
    channel_id: str
    period: str
    amount_fen: int
    entries: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    actor_id: str


class MemberInvitation(Scoped, table=True):
    __tablename__ = "member_invitations"
    email: str
    roles: list[str] = Field(sa_column=Column(JSON, nullable=False))
    inviter_id: str
    expires_at: datetime
    used_at: datetime | None = None
    revoked: bool = False


class SocialEvent(Scoped, table=True):
    __tablename__ = "social_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_id", "external_id"),
        UniqueConstraint("id", "tenant_id"),
        ForeignKeyConstraint(
            ["account_id", "tenant_id"],
            ["social_accounts.id", "social_accounts.tenant_id"],
        ),
        ForeignKeyConstraint(
            ["conversation_id", "tenant_id"],
            ["conversations.id", "conversations.tenant_id"],
        ),
    )
    account_id: str
    external_id: str
    kind: str
    thread_id: str
    work_id: str = ""
    sender_id: str
    sender_name: str = ""
    body: str
    conversation_id: str
    metadata_json: dict[str, Any] = json_field()


class SocialReply(Scoped, table=True):
    __tablename__ = "social_replies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id"),
        ForeignKeyConstraint(
            ["account_id", "tenant_id"],
            ["social_accounts.id", "social_accounts.tenant_id"],
        ),
        ForeignKeyConstraint(
            ["event_id", "tenant_id"], ["social_events.id", "social_events.tenant_id"]
        ),
        ForeignKeyConstraint(
            ["conversation_id", "tenant_id"],
            ["conversations.id", "conversations.tenant_id"],
        ),
    )
    account_id: str
    event_id: str
    conversation_id: str
    request_id: str
    actor_id: str
    automatic: bool = False
    draft_only: bool = False
    body: str = ""
    status: str = "queued"
    external_id: str = ""
    error: str = ""
    sources: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    updated_at: datetime = Field(default_factory=now)


# Operations 0.3: every object remains institution scoped.
class BusinessEvent(Scoped, table=True):
    __tablename__ = "business_events"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id"),
        UniqueConstraint("id", "tenant_id"),
    )
    kind: str = Field(index=True)
    record_id: str = Field(index=True)
    actor_id: str
    occurred_at: datetime = Field(default_factory=now)
    payload: dict[str, Any] = json_field()
    request_id: str = Field(default_factory=uid)


class FeedbackKPI(Scoped, table=True):
    __tablename__ = "feedback_kpis"
    __table_args__ = (
        UniqueConstraint("tenant_id", "lesson_id"),
        ForeignKeyConstraint(
            ["lesson_id", "tenant_id"], ["records.id", "records.tenant_id"]
        ),
    )
    lesson_id: str
    class_id: str
    teacher_id: str
    due_at: datetime
    completed_at: datetime | None = None
    version: int = 1
    notes: str = ""


class LessonRoster(Scoped, table=True):
    __tablename__ = "lesson_rosters"
    __table_args__ = (
        UniqueConstraint("tenant_id", "lesson_id", "enrollment_id"),
        UniqueConstraint("tenant_id", "lesson_id", "student_id"),
    )
    lesson_id: str
    class_id: str
    teacher_id: str
    student_id: str
    enrollment_id: str
    starts_at: datetime


class AdmissionImport(Scoped, table=True):
    __tablename__ = "admission_imports"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id"),
        UniqueConstraint("id", "tenant_id"),
    )
    actor_id: str
    asset_id: str
    request_id: str
    updated_at: datetime = Field(default_factory=now)
    template_version: str = "admissions-1"
    status: str = "queued"
    progress: int = 0
    rows_cipher: str = ""
    error: str = ""
    version: int = 1


class StudioDefinition(Scoped, table=True):
    __tablename__ = "studio_definitions"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id"),
        Index(
            "uq_active_business_workflow",
            "tenant_id",
            "binding",
            unique=True,
            postgresql_where=text("kind = 'workflow' AND enabled"),
            sqlite_where=text("kind = 'workflow' AND enabled = 1"),
        ),
    )
    kind: str
    name: str
    binding: str = "independent"
    draft: dict[str, Any] = json_field()
    version: int = 1
    published_version: int = 0
    enabled: bool = False
    created_by: str


class StudioVersion(Scoped, table=True):
    __tablename__ = "studio_versions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "definition_id", "version"),
        ForeignKeyConstraint(
            ["definition_id", "tenant_id"],
            ["studio_definitions.id", "studio_definitions.tenant_id"],
        ),
    )
    definition_id: str
    kind: str
    version: int
    spec: dict[str, Any] = json_field()


class FormSubmission(Scoped, table=True):
    __tablename__ = "form_submissions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id"),
        UniqueConstraint("id", "tenant_id"),
    )
    definition_id: str
    definition_version: int
    actor_id: str
    values_cipher: str
    binding: str = "independent"
    record_id: str = ""
    request_id: str
    status: str = "submitted"
    revision: int = 1


class FlowInstance(Scoped, table=True):
    __tablename__ = "flow_instances"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id"),
        UniqueConstraint("id", "tenant_id"),
    )
    definition_id: str
    definition_version: int
    actor_id: str
    binding: str
    record_id: str = ""
    payload_cipher: str
    state: dict[str, Any] = json_field()
    request_id: str
    status: str = "running"
    revision: int = 1


class FlowTask(Scoped, table=True):
    __tablename__ = "flow_tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "instance_id", "node_id", "assignee_id"),
        ForeignKeyConstraint(
            ["instance_id", "tenant_id"],
            ["flow_instances.id", "flow_instances.tenant_id"],
        ),
    )
    instance_id: str
    node_id: str
    assignee_id: str
    node_type: str = "approval"
    status: str = "pending"
    decision_note: str = ""
    decided_at: datetime | None = None


class ReportSnapshot(Scoped, table=True):
    __tablename__ = "report_snapshots"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "period", "version"),)
    kind: str
    period: str
    version: int
    digest: str
    payload: dict[str, Any] = json_field()


class OpsAlert(Scoped, table=True):
    __tablename__ = "ops_alerts"
    __table_args__ = (UniqueConstraint("tenant_id", "rule_id", "period"),)
    rule_id: str
    period: str
    metric: str
    value: float
    threshold: float
    status: str = "open"
    class_id: str = ""
    owner_id: str = ""
    note: str = ""
    detail: dict[str, Any] = json_field()
    updated_at: datetime = Field(default_factory=now)


class NotificationOutbox(Scoped, table=True):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id"),
        UniqueConstraint("id", "tenant_id"),
    )
    request_id: str
    kind: str
    body: str
    status: str = "queued"
    attempts: int = 0
    config_version: int = 0
    next_attempt_at: datetime = Field(default_factory=now)
    error: str = ""
    updated_at: datetime = Field(default_factory=now)


class ReceiptLink(Scoped, table=True):
    __tablename__ = "receipt_links"
    __table_args__ = (UniqueConstraint("tenant_id", "kind", "record_id", "asset_id"),)
    kind: str
    record_id: str
    asset_id: str
    actor_id: str
    note: str = ""


class AddOnRequest(Scoped, table=True):
    __tablename__ = "addon_requests"
    actor_id: str
    addon: str = "digital_human"
    status: str = "requested"
    note: str = ""
    platform_note: str = ""


class MediaProfile(Scoped, table=True):
    __tablename__ = "media_profiles"
    __table_args__ = (UniqueConstraint("id", "tenant_id"),)
    name: str
    audience: str
    style: str = ""
    knowledge_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    asset_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    rubrics: dict[str, Any] = json_field()
    version: int = 1
    updated_at: datetime = Field(default_factory=now)


class AccountGroup(Scoped, table=True):
    __tablename__ = "account_groups"
    __table_args__ = (UniqueConstraint("id", "tenant_id"), ForeignKeyConstraint(["profile_id", "tenant_id"], ["media_profiles.id", "media_profiles.tenant_id"]))
    profile_id: str
    name: str
    version: int = 1


class AccountGroupMember(Scoped, table=True):
    __tablename__ = "account_group_members"
    __table_args__ = (UniqueConstraint("tenant_id", "group_id", "account_id"), ForeignKeyConstraint(["group_id", "tenant_id"], ["account_groups.id", "account_groups.tenant_id"]), ForeignKeyConstraint(["account_id", "tenant_id"], ["social_accounts.id", "social_accounts.tenant_id"]))
    group_id: str
    account_id: str


class AutomationPlan(Scoped, table=True):
    __tablename__ = "automation_plans"
    __table_args__ = (UniqueConstraint("id", "tenant_id"), ForeignKeyConstraint(["profile_id", "tenant_id"], ["media_profiles.id", "media_profiles.tenant_id"]))
    profile_id: str
    name: str
    spec: dict[str, Any] = json_field()
    version: int = 1
    enabled: bool = False
    actor_id: str
    authorized_by: str = ""
    last_error: str = ""
    updated_at: datetime = Field(default_factory=now)


class AutomationPlanVersion(Scoped, table=True):
    __tablename__ = "automation_plan_versions"
    __table_args__ = (UniqueConstraint("tenant_id", "plan_id", "version"), ForeignKeyConstraint(["plan_id", "tenant_id"], ["automation_plans.id", "automation_plans.tenant_id"]))
    plan_id: str
    version: int
    snapshot: dict[str, Any] = json_field()


class AutomationRun(Scoped, table=True):
    __tablename__ = "automation_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "request_id"), UniqueConstraint("id", "tenant_id"), ForeignKeyConstraint(["plan_id", "tenant_id"], ["automation_plans.id", "automation_plans.tenant_id"]))
    plan_id: str
    plan_version: int
    request_id: str
    actor_id: str
    trial: bool = True
    status: str = "queued"
    paused: bool = False
    snapshot: dict[str, Any] = json_field()
    slot: datetime
    lease_until: datetime | None = None
    lease_token: str = ""
    revision: int = 1
    error: str = ""
    updated_at: datetime = Field(default_factory=now)


class AutomationAccountTask(Scoped, table=True):
    __tablename__ = "automation_account_tasks"
    __table_args__ = (UniqueConstraint("tenant_id", "run_id", "account_id"), UniqueConstraint("id", "tenant_id"), ForeignKeyConstraint(["run_id", "tenant_id"], ["automation_runs.id", "automation_runs.tenant_id"]), ForeignKeyConstraint(["account_id", "tenant_id"], ["social_accounts.id", "social_accounts.tenant_id"]))
    run_id: str
    account_id: str
    status: str = "queued"
    stage: str = "sources"
    data: dict[str, Any] = json_field()
    content_id: str = ""
    version_id: str = ""
    publish_job_id: str = ""
    error_code: str = ""
    error: str = ""
    updated_at: datetime = Field(default_factory=now)


class AutomationStep(Scoped, table=True):
    __tablename__ = "automation_steps"
    __table_args__ = (UniqueConstraint("tenant_id", "task_id", "key"), ForeignKeyConstraint(["task_id", "tenant_id"], ["automation_account_tasks.id", "automation_account_tasks.tenant_id"]))
    task_id: str
    key: str
    status: str = "queued"
    object_id: str = ""
    detail: dict[str, Any] = json_field()
    updated_at: datetime = Field(default_factory=now)


class MatrixCharge(Scoped, table=True):
    __tablename__ = "matrix_charges"
    __table_args__ = (UniqueConstraint("tenant_id", "request_id", "resource"),)
    request_id: str
    resource: str
    plan_id: str
    run_id: str
    account_id: str = ""
    profile_id: str
    reserved_fen: int
    actual_fen: int = 0
    state: str = "reserved"
    period: str
    day: str

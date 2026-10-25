from typing import Literal
from datetime import datetime
from pydantic import Field, model_validator
from .schemas import Strict


class ProfileInput(Strict):
    name: str = Field(min_length=1, max_length=80)
    audience: str = Field(min_length=1, max_length=1000)
    style: str = Field(default="", max_length=2000)
    knowledge_ids: list[str] = Field(default_factory=list, max_length=100)
    asset_ids: list[str] = Field(default_factory=list, max_length=100)
    version: int | None = None


class GroupInput(Strict):
    profile_id: str
    name: str = Field(min_length=1, max_length=80)
    account_ids: list[str] = Field(default_factory=list, max_length=500)
    version: int | None = None


class AccountConfig(Strict):
    profile_id: str | None = None
    positioning: str = Field(default="", max_length=1000)
    call_to_action: str = Field(default="", max_length=300)
    form: Literal["image_text", "video"] | None = None
    monthly_budget_fen: int = Field(default=0, ge=0, le=100000000)
    paused: bool = False


class PlanSpec(Strict):
    direction: str = Field(min_length=1, max_length=2000)
    account_ids: list[str] = Field(default_factory=list, max_length=500)
    group_ids: list[str] = Field(default_factory=list, max_length=100)
    mode: Literal["matrix", "independent"] = "matrix"
    source_urls: list[str] = Field(default_factory=list, max_length=10)
    xhs_search: bool = False
    weekdays: list[int] = Field(default_factory=lambda: [1, 4], min_length=1, max_length=7)
    times: list[str] = Field(default_factory=lambda: ["18:00"], min_length=1, max_length=12)
    timezone: Literal["Asia/Shanghai"] = "Asia/Shanghai"
    funding: Literal["platform", "byok"] = "platform"
    review: Literal["manual", "auto"] = "manual"
    allowed_render_modes: list[Literal["program", "aigc", "mixed"]] = Field(default_factory=lambda: ["program", "aigc", "mixed"], min_length=1, max_length=3)
    min_video_seconds: int = Field(default=45, ge=45, le=90)
    max_video_seconds: int = Field(default=90, ge=45, le=90)
    run_budget_fen: int = Field(default=0, ge=0, le=100000000)
    daily_budget_fen: int = Field(default=0, ge=0, le=100000000)

    @model_validator(mode="after")
    def valid_schedule(self):
        import re
        if any(d not in range(7) for d in self.weekdays) or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in self.times):
            raise ValueError("请选择有效星期和24小时制时间")
        if self.min_video_seconds > self.max_video_seconds:
            raise ValueError("视频最短时长不能超过最长时长")
        if self.funding == "byok":
            self.funding = "byok"
        return self


class PlanInput(Strict):
    profile_id: str
    name: str = Field(min_length=1, max_length=100)
    spec: PlanSpec
    version: int | None = None


class RunInput(Strict):
    plan_id: str
    request_id: str = Field(min_length=8, max_length=160)
    trial: bool = True
    slot: datetime | None = None


class EnabledInput(Strict):
    enabled: bool
    version: int


class BatchInput(Strict):
    account_ids: list[str] = Field(min_length=1, max_length=500)
    operation: Literal["check", "pause", "resume"]


class MatrixEntitlementInput(Strict):
    account_limit: int = Field(ge=0, le=500)
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any


class MatrixCostView(BaseModel):
    actual_fen: int = 0
    reserved_fen: int = 0
    shared: bool = False


class StepView(BaseModel):
    id: str
    key: str
    status: str
    object_id: str
    detail: dict[str,Any]
    updated_at: datetime
    cost: MatrixCostView


class TaskSummary(BaseModel):
    id: str
    account_id: str
    status: str
    stage: str
    version_id: str
    error: str


class TaskView(TaskSummary):
    run_id: str
    data: dict[str,Any]
    content_id: str
    publish_job_id: str
    error_code: str
    created_at: datetime
    updated_at: datetime
    steps: list[StepView]
    cost: MatrixCostView


class RunBase(BaseModel):
    id: str
    tenant_id: str
    plan_id: str
    plan_version: int
    request_id: str
    actor_id: str
    trial: bool
    paused: bool
    status: str
    snapshot: dict[str,Any]
    slot: datetime
    revision: int
    error: str
    created_at: datetime
    updated_at: datetime


class RunView(RunBase):
    tasks: list[TaskView]
    cost: MatrixCostView
    shared_cost: MatrixCostView


class RunSummary(RunBase):
    tasks: list[TaskSummary]

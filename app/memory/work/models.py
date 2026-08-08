"""后端工作记忆与工作 Agent 的中立数据模型。"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.memory.paths import validate_role_name

from .paths import validate_work_namespace


class WorkModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkMemoryScope(WorkModel):
    role_name_en: str
    work_user_namespace: str

    @field_validator("role_name_en")
    @classmethod
    def validate_role(cls, value: str) -> str:
        return validate_role_name(value)

    @field_validator("work_user_namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        return validate_work_namespace(value)

    @property
    def key(self) -> str:
        return f"{self.role_name_en.casefold()}::{self.work_user_namespace}"

    @classmethod
    def from_identity(
        cls,
        role_name_en: str,
        stable_user_id: str,
        *,
        namespace_secret: str,
    ) -> "WorkMemoryScope":
        if not stable_user_id or not namespace_secret:
            raise ValueError("stable_user_id 和 namespace_secret 不能为空")
        digest = hmac.new(
            namespace_secret.encode("utf-8"),
            stable_user_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return cls(role_name_en=role_name_en, work_user_namespace=f"work_{digest}")


class WorkStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_INPUT = "needs_input"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkEventType(StrEnum):
    JOB_CREATED = "job_created"
    JOB_QUEUED = "job_queued"
    JOB_RUNNING = "job_running"
    JOB_NEEDS_INPUT = "job_needs_input"
    JOB_SUCCEEDED = "job_succeeded"
    JOB_FAILED = "job_failed"
    JOB_CANCELLED = "job_cancelled"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    TOOL_FAILED = "tool_failed"
    SKILL_SELECTED = "skill_selected"


class WorkMemoryKind(StrEnum):
    TOOL_PREFERENCE = "tool_preference"
    SKILL_PREFERENCE = "skill_preference"
    USAGE_FREQUENCY = "usage_frequency"
    TASK_PATTERN = "task_pattern"
    USER_WORK_PREFERENCE = "user_work_preference"
    ENVIRONMENT_FACT = "environment_fact"


class WorkMemoryStatus(StrEnum):
    CURRENT = "current"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkCommand(WorkModel):
    schema_version: Literal["companionheart.work-command.v1"] = (
        "companionheart.work-command.v1"
    )
    command_id: str = Field(..., min_length=8, max_length=128)
    job_id: str = Field(..., min_length=8, max_length=128)
    origin_role_name_en: str
    work_user_namespace: str
    task: str = Field(..., min_length=1, max_length=8000)
    acceptance_criteria: tuple[str, ...] = Field(default=(), max_length=32)
    constraints: tuple[str, ...] = Field(default=(), max_length=32)
    allowed_capabilities: tuple[str, ...] = Field(default=(), max_length=64)
    context_summary: str = Field("", max_length=12000)
    timeout_seconds: int = Field(600, ge=1, le=3600)
    mode: Literal["normal", "developer"] = "normal"
    developer_session_id: str | None = Field(None, min_length=8, max_length=128)
    suppress_normal_memory_updates: bool = False

    @field_validator("origin_role_name_en")
    @classmethod
    def validate_origin_role(cls, value: str) -> str:
        return validate_role_name(value)

    @field_validator("work_user_namespace")
    @classmethod
    def validate_work_user_namespace(cls, value: str) -> str:
        return validate_work_namespace(value)

    @field_validator("acceptance_criteria", "constraints")
    @classmethod
    def validate_text_items(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        for value in values:
            if not value.strip() or len(value) > 1000:
                raise ValueError("验收标准和约束必须是 1..1000 字符的非空文本")
        return values

    @field_validator("allowed_capabilities")
    @classmethod
    def validate_capabilities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("allowed_capabilities 不能重复")
        if any(not _CAPABILITY_RE.fullmatch(value) for value in values):
            raise ValueError("allowed_capabilities 包含非法标识")
        return values

    def model_post_init(self, __context) -> None:
        if self.mode == "developer":
            if not self.developer_session_id or not self.suppress_normal_memory_updates:
                raise ValueError("开发任务必须携带 session 且禁止更新普通工作记忆")
        elif self.developer_session_id is not None:
            raise ValueError("普通任务不能携带 developer_session_id")


class WorkResult(WorkModel):
    schema_version: Literal["companionheart.work-result.v1"] = (
        "companionheart.work-result.v1"
    )
    command_id: str = Field(..., min_length=8, max_length=128)
    job_id: str = Field(..., min_length=8, max_length=128)
    status: WorkStatus
    user_facing_summary: str = Field("", max_length=12000)
    questions: tuple[str, ...] = Field(default=(), max_length=16)
    error_code: str | None = Field(None, max_length=128)
    started_at: str | None = None
    finished_at: str | None = None

    @field_validator("questions")
    @classmethod
    def validate_questions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or len(value) > 1000 for value in values):
            raise ValueError("questions 必须是 1..1000 字符的非空文本")
        return values

    def model_post_init(self, __context) -> None:
        if self.status not in {
            WorkStatus.NEEDS_INPUT,
            WorkStatus.SUCCEEDED,
            WorkStatus.FAILED,
            WorkStatus.CANCELLED,
        }:
            raise ValueError("WorkResult 只允许终态或 needs_input")
        if self.status == WorkStatus.NEEDS_INPUT and not self.questions:
            raise ValueError("needs_input 必须提供 questions")
        if self.status == WorkStatus.FAILED and not self.error_code:
            raise ValueError("failed 必须提供 error_code")


class WorkEvent(WorkModel):
    schema_version: Literal["companionheart.work-event.v1"] = (
        "companionheart.work-event.v1"
    )
    event_id: str = Field(..., min_length=8, max_length=128)
    job_id: str = Field(..., min_length=8, max_length=128)
    command_id: str = Field(..., min_length=8, max_length=128)
    sequence: int = Field(..., ge=1)
    event_type: WorkEventType
    timestamp: str = Field(default_factory=utc_now)
    summary: str = Field("", max_length=12000)
    tool_name: str | None = Field(None, max_length=128)
    skill_name: str | None = Field(None, max_length=128)
    error_code: str | None = Field(None, max_length=128)
    questions: tuple[str, ...] = Field(default=(), max_length=16)
    duration_ms: int | None = Field(None, ge=0)
    idempotency_key: str = Field(..., min_length=8, max_length=256)

    @field_validator("questions")
    @classmethod
    def validate_event_questions(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value.strip() or len(value) > 1000 for value in values):
            raise ValueError("questions 必须是 1..1000 字符的非空文本")
        return values


class WorkMemoryRecord(WorkModel):
    schema_version: Literal["companionheart.work-memory.v1"] = (
        "companionheart.work-memory.v1"
    )
    id: str = Field(..., min_length=8, max_length=128)
    kind: WorkMemoryKind
    key: str = Field(..., min_length=1, max_length=256)
    value: str = Field(..., max_length=12000)
    source: Literal["user_explicit", "usage_inferred", "environment_probe", "system"]
    confidence: float = Field(..., ge=0, le=1)
    status: WorkMemoryStatus = WorkMemoryStatus.CURRENT
    statistics: dict[str, float] = Field(default_factory=dict)
    first_observed_at: str = Field(default_factory=utc_now)
    last_observed_at: str = Field(default_factory=utc_now)
    supersedes: str | None = None
    idempotency_key: str = Field(..., min_length=8, max_length=256)

    @field_validator("statistics")
    @classmethod
    def validate_statistics(cls, value: dict[str, float]) -> dict[str, float]:
        if len(value) > 64:
            raise ValueError("statistics 字段过多")
        for key, number in value.items():
            if not _CAPABILITY_RE.fullmatch(key) or number < 0:
                raise ValueError("statistics 只允许安全键和非负数值")
        return value

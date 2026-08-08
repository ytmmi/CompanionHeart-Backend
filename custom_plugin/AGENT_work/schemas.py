"""AGENT_work 的独立 HTTP 契约。

本插件故意不导入 ``app.memory`` 或生活会话模块。后端与 sidecar 只通过
版本化 JSON 契约通信，避免进程内对象越过安全域。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


_CAPABILITY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_ROLE_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_NAMESPACE_RE = re.compile(r"^work_[0-9a-f]{64}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_INPUT = "needs_input"


class WorkCommand(StrictModel):
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
    def validate_role(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not _ROLE_RE.fullmatch(normalized):
            raise ValueError("角色英文名不合法")
        return normalized

    @field_validator("work_user_namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        if not _NAMESPACE_RE.fullmatch(value):
            raise ValueError("工作用户 namespace 不合法")
        return value

    @field_validator("allowed_capabilities")
    @classmethod
    def validate_capabilities(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("allowed_capabilities 不能重复")
        if any(not _CAPABILITY_RE.fullmatch(value) for value in values):
            raise ValueError("allowed_capabilities 包含非法标识")
        return values

    @model_validator(mode="after")
    def validate_developer_isolation(self) -> "WorkCommand":
        if self.mode == "developer":
            if not self.developer_session_id or not self.suppress_normal_memory_updates:
                raise ValueError("开发任务必须携带 session 且禁止更新普通工作记忆")
        elif self.developer_session_id is not None:
            raise ValueError("普通任务不能携带 developer_session_id")
        return self


class WorkResult(StrictModel):
    schema_version: Literal["companionheart.work-result.v1"] = (
        "companionheart.work-result.v1"
    )
    command_id: str
    job_id: str
    status: WorkStatus
    user_facing_summary: str = Field("", max_length=12000)
    questions: tuple[str, ...] = Field(default=(), max_length=16)
    error_code: str | None = Field(None, max_length=128)
    started_at: str | None = None
    finished_at: str | None = None


class AbortRequest(StrictModel):
    job_id: str = Field(..., min_length=8, max_length=128)

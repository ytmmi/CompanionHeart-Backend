"""Provider 中立的生活长期记忆数据模型。"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.memory.paths import validate_role_name


NAMESPACE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
FactState = Literal["current", "past", "uncertain"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LifeMemoryScope(MemoryModel):
    """服务端构造的角色/用户物理隔离范围。"""

    role_name_en: str
    user_namespace: str

    @field_validator("role_name_en")
    @classmethod
    def validate_role(cls, value: str) -> str:
        return validate_role_name(value)

    @field_validator("user_namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        if not NAMESPACE_PATTERN.fullmatch(value):
            raise ValueError("user_namespace 只能包含字母、数字、点、下划线和连字符")
        return value

    @property
    def key(self) -> str:
        return f"{self.role_name_en.casefold()}::{self.user_namespace}"


class LifeMemoryCandidate(MemoryModel):
    statement: str = Field(..., min_length=1, max_length=4000)
    kind: str = "event"
    importance: float = Field(0.5, ge=0.0, le=1.0)
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    sensitivity: Literal["normal", "private", "restricted"] = "normal"
    source_refs: tuple[str, ...] = ()
    source_type: str = "user_explicit"
    tags: tuple[str, ...] = ()
    idempotency_key: str = Field(..., min_length=1, max_length=256)
    context: str = Field("", max_length=12000)
    effective_at: str | None = Field(None, max_length=32)


class LifeMemoryRecord(LifeMemoryCandidate):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    status: Literal["active", "superseded", "disputed", "deleted"] = "active"
    supersedes: str | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    fact_key: str | None = None
    fact_value: str | None = None
    fact_state: FactState = "current"
    valid_from: str | None = None
    valid_to: str | None = None

    @property
    def fact_label(self) -> str:
        return {
            "current": "[现在事实]",
            "past": "[过去事实]",
            "uncertain": "[待确认事实]",
        }[self.fact_state]


class MemoryRevision(MemoryModel):
    statement: str = Field(..., min_length=1, max_length=4000)
    reason: str = Field("", max_length=1000)
    idempotency_key: str = Field(..., min_length=1, max_length=256)


class LifeMemoryQuery(MemoryModel):
    text: str = Field(..., min_length=1, max_length=4000)
    top_k: int = Field(8, ge=1, le=100)
    kinds: tuple[str, ...] = ()
    fact_states: tuple[FactState, ...] = ()
    min_score: float = Field(0.0, ge=0.0, le=1.0)


class LifeMemoryHit(MemoryModel):
    record: LifeMemoryRecord
    score: float = Field(..., ge=0.0, le=1.0)
    source: str = "provider"


class DeleteReceipt(MemoryModel):
    scope: LifeMemoryScope
    deleted_ids: tuple[str, ...] = ()
    deleted_count: int = 0
    completed: bool = True
    details: dict[str, bool] = Field(default_factory=dict)
    completed_at: str = Field(default_factory=utc_now)


class ProviderHealth(MemoryModel):
    available: bool
    provider: str
    version: str = ""
    detail: str = ""


class ProviderStatus(MemoryModel):
    scope: LifeMemoryScope
    record_count: int = 0
    index_ready: bool = True
    pending_writes: int = 0

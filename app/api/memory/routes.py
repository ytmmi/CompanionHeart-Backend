"""MEMORY_omni 协议转发 API。

路由不做记忆抽取、分类、去重、索引或本地持久化；这些操作全部交给插件进程。
"""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.memory.life import (
    LifeMemoryCandidate,
    LifeMemoryQuery,
    LifeMemoryService,
    MemoryRevision,
    create_life_memory_provider,
    create_life_memory_service,
)
from app.memory.roles import RoleConfigError, get_role_registry


router = APIRouter(prefix="/api/memory", tags=["Memory"])
_service = create_life_memory_service()


class MemoryTextRequest(BaseModel):
    role_name_en: Optional[str] = None
    text: str = Field(..., min_length=1, max_length=4000)
    idempotency_key: str = Field(..., min_length=1, max_length=256)
    source_type: str = "user_explicit"
    kind: str = "event"
    importance: float = Field(0.5, ge=0, le=1)
    confidence: float = Field(1.0, ge=0, le=1)
    sensitivity: Literal["normal", "private", "restricted"] = "normal"
    tags: tuple[str, ...] = ()
    context: str = Field("", max_length=12000)
    effective_at: str | None = Field(None, max_length=32)


class MemorySearchRequest(BaseModel):
    role_name_en: Optional[str] = None
    query: str = Field(..., min_length=1, max_length=4000)
    top_k: int = Field(8, ge=1, le=50)
    min_score: float = Field(0, ge=0, le=1)
    fact_states: tuple[Literal["current", "past", "uncertain"], ...] = ()


class MemoryRevisionRequest(BaseModel):
    role_name_en: Optional[str] = None
    statement: str = Field(..., min_length=1, max_length=4000)
    reason: str = Field("", max_length=1000)
    idempotency_key: str = Field(..., min_length=1, max_length=256)


def _scope(role_name_en: str | None):
    try:
        return _service.scope_for(role_name_en, "local-default")
    except RoleConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/health")
async def memory_health():
    if _service is None:
        return {"available": False, "provider": "disabled"}
    health = await _service.health()
    return health.model_dump()


@router.post("/text")
async def remember_text(request: MemoryTextRequest):
    if _service is None:
        raise HTTPException(status_code=503, detail="MEMORY_omni 未启用")
    scope = _scope(request.role_name_en)
    candidate = LifeMemoryCandidate(
        statement=request.text,
        source_type=request.source_type,
        kind=request.kind,
        importance=request.importance,
        confidence=request.confidence,
        sensitivity=request.sensitivity,
        tags=request.tags,
        idempotency_key=request.idempotency_key,
        context=request.context,
        effective_at=request.effective_at,
    )
    try:
        memory_id = await _service.remember(scope, candidate)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MEMORY_omni 不可用: {exc}") from exc
    record = await _service.provider.get(scope, memory_id)
    return {
        "id": memory_id,
        "role_name_en": scope.role_name_en,
        "memory": record.model_dump() if record else None,
        "fact_label": record.fact_label if record else None,
    }


@router.post("/search")
async def search_memory(request: MemorySearchRequest):
    if _service is None:
        raise HTTPException(status_code=503, detail="MEMORY_omni 未启用")
    scope = _scope(request.role_name_en)
    try:
        hits = await _service.search(
            scope,
            LifeMemoryQuery(
                text=request.query,
                top_k=request.top_k,
                min_score=request.min_score,
                fact_states=request.fact_states,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MEMORY_omni 不可用: {exc}") from exc
    return {
        "role_name_en": scope.role_name_en,
        "hits": [
            {**hit.model_dump(), "fact_label": hit.record.fact_label}
            for hit in hits
        ],
    }


@router.delete("/scope")
async def forget_scope(role_name_en: Optional[str] = None):
    if _service is None:
        raise HTTPException(status_code=503, detail="MEMORY_omni 未启用")
    scope = _scope(role_name_en)
    try:
        receipt = await _service.forget_scope(scope)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MEMORY_omni 不可用: {exc}") from exc
    return receipt.model_dump()


@router.get("/life/{memory_id}")
async def get_memory(memory_id: str, role_name_en: Optional[str] = None):
    if _service is None:
        raise HTTPException(status_code=503, detail="MEMORY_omni 未启用")
    scope = _scope(role_name_en)
    try:
        record = await _service.provider.get(scope, memory_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MEMORY_omni 不可用: {exc}") from exc
    if record is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {**record.model_dump(), "fact_label": record.fact_label}


@router.post("/life/{memory_id}/revise")
async def revise_memory(memory_id: str, request: MemoryRevisionRequest):
    if _service is None:
        raise HTTPException(status_code=503, detail="MEMORY_omni 未启用")
    scope = _scope(request.role_name_en)
    try:
        revised_id = await _service.provider.revise(
            scope,
            memory_id,
            MemoryRevision(
                statement=request.statement,
                reason=request.reason,
                idempotency_key=request.idempotency_key,
            ),
        )
        record = await _service.provider.get(scope, revised_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MEMORY_omni 不可用: {exc}") from exc
    return {
        "id": revised_id,
        "memory": record.model_dump() if record else None,
        "fact_label": record.fact_label if record else None,
    }


@router.delete("/life/{memory_id}")
async def delete_memory(memory_id: str, role_name_en: Optional[str] = None):
    if _service is None:
        raise HTTPException(status_code=503, detail="MEMORY_omni 未启用")
    scope = _scope(role_name_en)
    try:
        receipt = await _service.provider.delete(scope, memory_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MEMORY_omni 不可用: {exc}") from exc
    return receipt.model_dump()


@router.get("/status")
async def memory_status(role_name_en: Optional[str] = None):
    if _service is None:
        return {"available": False, "provider": "disabled"}
    scope = _scope(role_name_en)
    try:
        status = await _service.provider.status(scope)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MEMORY_omni 不可用: {exc}") from exc
    return status.model_dump()

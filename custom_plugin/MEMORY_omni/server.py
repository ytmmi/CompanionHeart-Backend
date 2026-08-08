"""MEMORY_omni HTTP sidecar。仅使用后端项目 Python 环境。"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:  # 直接以 server.py 启动时
    from omni_memory import InvalidMemoryScope, OmniMemoryOrchestrator
except ModuleNotFoundError:  # 作为包导入时的测试/工具场景
    from .omni_memory import InvalidMemoryScope, OmniMemoryOrchestrator


app = FastAPI(title="MEMORY_omni", version="0.1.0")
UPSTREAM_COMMIT = "db80b6a7c591e0ea730a058e9f5fc4eb06572299"
_data_root = Path(os.environ.get("MEMORY_DATA_ROOT", "../../app/memory/data_memory")).resolve()
_orchestrators: dict[tuple[str, str], OmniMemoryOrchestrator] = {}
_cache_lock = asyncio.Lock()


class TextMemoryRequest(BaseModel):
    role_name_en: str
    user_namespace: str
    text: str = Field(..., min_length=1)
    source: str = "conversation"
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    context: str = ""
    effective_at: str | None = None


class QueryRequest(BaseModel):
    role_name_en: str
    user_namespace: str
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    fact_states: tuple[Literal["current", "past", "uncertain"], ...] = ()


class DeleteRequest(BaseModel):
    role_name_en: str
    user_namespace: str


class RevisionRequest(DeleteRequest):
    text: str = Field(..., min_length=1)
    reason: str = ""
    idempotency_key: str | None = None


async def _get_orchestrator(role_name_en: str, user_namespace: str) -> OmniMemoryOrchestrator:
    key = (role_name_en, user_namespace)
    async with _cache_lock:
        if key not in _orchestrators:
            try:
                _orchestrators[key] = OmniMemoryOrchestrator(_data_root, *key)
            except InvalidMemoryScope as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _orchestrators[key]


def _unit_json(unit, score: float | None = None) -> dict[str, Any]:
    result = {
        "id": unit.id,
        "timestamp": unit.timestamp,
        "modality_type": unit.modality_type,
        "summary": unit.summary,
        "raw_pointer": unit.raw_pointer,
        "metadata": unit.metadata,
        "schema_version": unit.schema_version,
        "status": unit.status,
        "storage_tier": unit.storage_tier,
        "fact_key": unit.fact_key,
        "fact_state": unit.fact_state,
        "fact_label": unit.fact_label,
        "confidence": unit.confidence,
        "effective_at": unit.metadata.get("effective_at"),
    }
    if score is not None:
        result["score"] = score
    return result


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "MEMORY_omni",
        "version": "0.1.0",
        "upstream_commit": UPSTREAM_COMMIT,
        "data_root": str(_data_root),
    }


@app.get("/status")
async def status() -> dict[str, Any]:
    return {"status": "ok", "service": "MEMORY_omni", "namespaces": len(_orchestrators), "data_root": str(_data_root)}


@app.get("/v1/scopes/{role_name_en}/{user_namespace}/status")
async def scope_status(role_name_en: str, user_namespace: str) -> dict[str, Any]:
    orchestrator = await _get_orchestrator(role_name_en, user_namespace)
    return await asyncio.to_thread(orchestrator.status)


@app.post("/v1/memories/text")
async def add_text(request: TextMemoryRequest) -> dict[str, Any]:
    orchestrator = await _get_orchestrator(request.role_name_en, request.user_namespace)
    metadata = dict(request.metadata)
    if request.effective_at:
        metadata["effective_at"] = request.effective_at
    units = await asyncio.to_thread(
        orchestrator.add_text,
        request.text,
        source=request.source,
        idempotency_key=request.idempotency_key,
        metadata=metadata,
        context=request.context,
    )
    return {"accepted": len(units), "memories": [_unit_json(unit) for unit in units]}


@app.post("/v1/memories/query")
async def query(request: QueryRequest) -> dict[str, Any]:
    orchestrator = await _get_orchestrator(request.role_name_en, request.user_namespace)
    hits = await asyncio.to_thread(
        orchestrator.query,
        request.query,
        top_k=request.top_k,
        fact_states=request.fact_states,
    )
    return {"hits": [_unit_json(unit, score) for unit, score in hits]}


@app.delete("/v1/memories/{memory_id}")
async def delete(memory_id: str, request: DeleteRequest) -> dict[str, Any]:
    orchestrator = await _get_orchestrator(request.role_name_en, request.user_namespace)
    deleted = await asyncio.to_thread(orchestrator.delete, memory_id)
    return {"deleted": deleted, "memory_id": memory_id}


@app.get("/v1/memories/{memory_id}")
async def get(memory_id: str, role_name_en: str, user_namespace: str) -> dict[str, Any]:
    orchestrator = await _get_orchestrator(role_name_en, user_namespace)
    unit = await asyncio.to_thread(orchestrator.get, memory_id)
    if unit is None or unit.status == "DELETED":
        raise HTTPException(status_code=404, detail="memory not found")
    return {"memory": _unit_json(unit)}


@app.post("/v1/memories/{memory_id}/revise")
async def revise(memory_id: str, request: RevisionRequest) -> dict[str, Any]:
    orchestrator = await _get_orchestrator(request.role_name_en, request.user_namespace)
    unit = await asyncio.to_thread(
        orchestrator.revise,
        memory_id,
        request.text,
        reason=request.reason,
        idempotency_key=request.idempotency_key,
    )
    if unit is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"memory": _unit_json(unit)}


@app.delete("/v1/scopes/{role_name_en}/{user_namespace}")
async def delete_scope(role_name_en: str, user_namespace: str) -> dict[str, Any]:
    orchestrator = await _get_orchestrator(role_name_en, user_namespace)
    count = await asyncio.to_thread(orchestrator.delete_scope)
    return {"deleted": count, "role_name_en": role_name_en, "user_namespace": user_namespace}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8500)
    args = parser.parse_args()
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=args.port)

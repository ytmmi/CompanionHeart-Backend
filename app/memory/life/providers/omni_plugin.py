"""MEMORY_omni HTTP Provider。

本模块只做协议转换和异步 HTTP 调用，不在后端执行记忆抽取、分类、索引、去重或
持久化。所有这些行为由 custom_plugin/MEMORY_omni 完成。
"""

from __future__ import annotations

from typing import Any

import httpx

from app.plugins.client import PluginHTTPClient

from ..models import (
    DeleteReceipt,
    LifeMemoryHit,
    LifeMemoryQuery,
    LifeMemoryRecord,
    LifeMemoryScope,
    MemoryRevision,
    ProviderHealth,
    ProviderStatus,
)


class OmniPluginLifeMemoryProvider:
    provider_name = "MEMORY_omni"

    def __init__(self, base_url: str = "http://localhost:8500", timeout: int = 30) -> None:
        self.client = PluginHTTPClient(base_url, timeout=timeout)

    @staticmethod
    def _scope(scope: LifeMemoryScope) -> dict[str, str]:
        return {
            "role_name_en": scope.role_name_en,
            "user_namespace": scope.user_namespace,
        }

    @staticmethod
    def _record(scope: LifeMemoryScope, raw: dict[str, Any]) -> LifeMemoryRecord:
        metadata = raw.get("metadata") or {}
        return LifeMemoryRecord(
            id=raw["id"],
            statement=raw.get("summary", ""),
            kind=metadata.get("kind", "event"),
            importance=float(metadata.get("importance", 0.5)),
            confidence=float(metadata.get("confidence", 1.0)),
            sensitivity=metadata.get("sensitivity", "normal"),
            source_refs=tuple(metadata.get("source_refs", ())),
            source_type=metadata.get("source_type", metadata.get("source", "plugin")),
            tags=tuple(metadata.get("tags", ())),
            idempotency_key=metadata.get("idempotency_key", raw["id"]),
            context=metadata.get("context", ""),
            effective_at=metadata.get("effective_at"),
            status=str(raw.get("status", "ACTIVE")).lower(),
            supersedes=metadata.get("supersedes"),
            created_at=raw.get("timestamp"),
            updated_at=raw.get("timestamp"),
            fact_key=raw.get("fact_key"),
            fact_value=metadata.get("fact_value"),
            fact_state=raw.get("fact_state", "current"),
            valid_from=metadata.get("effective_at"),
            valid_to=metadata.get("valid_to"),
        )

    async def upsert(self, scope: LifeMemoryScope, record: LifeMemoryRecord) -> str:
        metadata = {
            "kind": record.kind,
            "importance": record.importance,
            "confidence": record.confidence,
            "sensitivity": record.sensitivity,
            "source_refs": list(record.source_refs),
            "source_type": record.source_type,
            "tags": list(record.tags),
            "fact_key": record.fact_key,
            "fact_value": record.fact_value,
            "fact_state": record.fact_state,
            "valid_from": record.valid_from,
            "valid_to": record.valid_to,
            "effective_at": record.effective_at,
            "context": record.context,
        }
        response = await self.client.post(
            "/v1/memories/text",
            json={
                **self._scope(scope),
                "text": record.statement,
                "source": record.source_type,
                "idempotency_key": record.idempotency_key,
                "metadata": metadata,
                "context": record.context,
                "effective_at": record.effective_at,
            },
        )
        response.raise_for_status()
        memories = response.json().get("memories", [])
        return memories[0]["id"] if memories else record.id

    async def search(self, scope: LifeMemoryScope, query: LifeMemoryQuery) -> list[LifeMemoryHit]:
        response = await self.client.post(
            "/v1/memories/query",
            json={
                **self._scope(scope),
                "query": query.text,
                "top_k": query.top_k,
                "fact_states": list(query.fact_states),
            },
        )
        response.raise_for_status()
        hits = []
        for raw in response.json().get("hits", []):
            score = float(raw.get("score", 0.0))
            if score < query.min_score:
                continue
            record = self._record(scope, raw)
            if query.kinds and record.kind not in query.kinds:
                continue
            if query.fact_states and record.fact_state not in query.fact_states:
                continue
            hits.append(LifeMemoryHit(record=record, score=score, source=self.provider_name))
        return hits

    async def get(self, scope: LifeMemoryScope, memory_id: str) -> LifeMemoryRecord | None:
        response = await self.client.get(
            f"/v1/memories/{memory_id}",
            params=self._scope(scope),
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        raw = response.json().get("memory")
        return self._record(scope, raw) if raw else None

    async def revise(self, scope: LifeMemoryScope, memory_id: str, revision: MemoryRevision) -> str:
        response = await self.client.post(
            f"/v1/memories/{memory_id}/revise",
            json={
                **self._scope(scope),
                "text": revision.statement,
                "reason": revision.reason,
                "idempotency_key": revision.idempotency_key,
            },
        )
        response.raise_for_status()
        return response.json()["memory"]["id"]

    async def delete(self, scope: LifeMemoryScope, memory_id: str) -> DeleteReceipt:
        response = await self.client.delete(
            f"/v1/memories/{memory_id}",
            json=self._scope(scope),
        )
        response.raise_for_status()
        deleted = bool(response.json().get("deleted", False))
        return DeleteReceipt(
            scope=scope,
            deleted_ids=(memory_id,) if deleted else (),
            deleted_count=1 if deleted else 0,
        )

    async def delete_scope(self, scope: LifeMemoryScope) -> DeleteReceipt:
        response = await self.client.delete(
            f"/v1/scopes/{scope.role_name_en}/{scope.user_namespace}"
        )
        response.raise_for_status()
        count = int(response.json().get("deleted", 0))
        return DeleteReceipt(scope=scope, deleted_count=count)

    async def status(self, scope: LifeMemoryScope) -> ProviderStatus:
        response = await self.client.get(
            f"/v1/scopes/{scope.role_name_en}/{scope.user_namespace}/status"
        )
        response.raise_for_status()
        return ProviderStatus(
            scope=scope,
            record_count=int(response.json().get("records", 0)),
            index_ready=True,
        )

    async def health(self) -> ProviderHealth:
        try:
            response = await self.client.get("/health")
            response.raise_for_status()
            return ProviderHealth(available=True, provider=self.provider_name, version="0.1.0")
        except (httpx.HTTPError, OSError) as exc:
            return ProviderHealth(available=False, provider=self.provider_name, detail=str(exc))

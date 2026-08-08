"""已认证开发会话的全记忆受控查询网关。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.work import WorkCoordinatorRegistry
from app.memory.developer import DEVELOPER_MEMORY_ROOT, DeveloperMemoryStore
from app.memory.life import LifeMemoryQuery, LifeMemoryService
from app.memory.roles import get_role_registry


MemoryDomain = Literal[
    "life", "work_long_term", "work_short_term", "developer", "work_archive"
]


class GatewayModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeveloperMemoryQuery(GatewayModel):
    text: str = Field(..., min_length=1, max_length=4000)
    domains: tuple[MemoryDomain, ...] = (
        "life",
        "work_long_term",
        "work_short_term",
        "developer",
    )
    role_name_en: str | None = None
    top_k: int = Field(20, ge=1, le=50)
    include_work_archive: bool = False


class DeveloperMemoryHit(GatewayModel):
    domain: MemoryDomain
    role_name_en: str
    source_id: str
    content: str = Field(..., max_length=12000)
    timestamp: str = ""
    score: float = Field(0, ge=0)


class DeveloperMemoryQueryResult(GatewayModel):
    audit_id: str
    hits: tuple[DeveloperMemoryHit, ...]


class DeveloperMemoryGateway:
    def __init__(
        self,
        *,
        work_registry: WorkCoordinatorRegistry | None = None,
        life_memory: LifeMemoryService | None = None,
        developer_root: Path | None = None,
    ) -> None:
        self.work_registry = work_registry or WorkCoordinatorRegistry()
        self.life_memory = life_memory
        self.developer_root = (developer_root or DEVELOPER_MEMORY_ROOT).resolve()

    @staticmethod
    def _score(text: str, query: str) -> float:
        terms = [term.casefold() for term in query.split() if term]
        haystack = text.casefold()
        return float(sum(term in haystack for term in terms)) if terms else 0.0

    async def query(
        self,
        *,
        developer_session_id: str,
        stable_user_id: str,
        request: DeveloperMemoryQuery,
    ) -> DeveloperMemoryQueryResult:
        domains = set(request.domains)
        if request.include_work_archive:
            domains.add("work_archive")
        else:
            domains.discard("work_archive")
        roles = (
            [get_role_registry().resolve(request.role_name_en)]
            if request.role_name_en
            else get_role_registry().list()
        )
        hits: list[DeveloperMemoryHit] = []

        for role in roles:
            if "life" in domains and self.life_memory is not None:
                try:
                    scope = self.life_memory.scope_for(role.name_en, stable_user_id)
                    life_hits = await self.life_memory.search(
                        scope,
                        LifeMemoryQuery(text=request.text, top_k=request.top_k),
                    )
                    hits.extend(
                        DeveloperMemoryHit(
                            domain="life",
                            role_name_en=role.name_en,
                            source_id=hit.record.id,
                            content=f"{hit.record.fact_label} {hit.record.statement}"[:12000],
                            timestamp=hit.record.updated_at,
                            score=hit.score,
                        )
                        for hit in life_hits
                    )
                except Exception:
                    # 单域不可用时继续返回其他域，避免 MEMORY 插件故障阻断调试。
                    pass

            coordinator = self.work_registry.get(role.name_en, stable_user_id)
            if "work_long_term" in domains:
                for record in coordinator.long_term.search(
                    request.text, top_k=request.top_k
                ):
                    content = f"{record.kind.value} {record.key}: {record.value}"
                    hits.append(
                        DeveloperMemoryHit(
                            domain="work_long_term",
                            role_name_en=role.name_en,
                            source_id=record.id,
                            content=content[:12000],
                            timestamp=record.last_observed_at,
                            score=self._score(content, request.text),
                        )
                    )
            if "work_short_term" in domains:
                for job_id in coordinator.jobs.list_job_ids():
                    for event in coordinator.jobs.read_events(job_id):
                        content = f"{event.event_type.value}: {event.summary}"
                        score = self._score(content, request.text)
                        if score:
                            hits.append(
                                DeveloperMemoryHit(
                                    domain="work_short_term",
                                    role_name_en=role.name_en,
                                    source_id=event.event_id,
                                    content=content[:12000],
                                    timestamp=event.timestamp,
                                    score=score,
                                )
                            )
            if "work_archive" in domains:
                today = datetime.now(timezone.utc).date()
                for offset in range(coordinator.archive.RETENTION_DAYS):
                    for record in coordinator.archive.read_day(today - timedelta(days=offset)):
                        content = f"{record.event_type}: {record.payload}"
                        score = self._score(content, request.text)
                        if score:
                            hits.append(
                                DeveloperMemoryHit(
                                    domain="work_archive",
                                    role_name_en=role.name_en,
                                    source_id=record.archive_id,
                                    content=content[:12000],
                                    timestamp=record.timestamp,
                                    score=score,
                                )
                            )

        if "developer" in domains:
            sessions_root = self.developer_root / "ytmmi" / "sessions"
            if sessions_root.exists():
                for path in sessions_root.iterdir():
                    if not path.is_dir():
                        continue
                    try:
                        store = DeveloperMemoryStore(path.name, data_root=self.developer_root)
                        records = store.records()
                    except (ValueError, RuntimeError):
                        continue
                    for record in records:
                        score = self._score(record.content, request.text)
                        if score:
                            hits.append(
                                DeveloperMemoryHit(
                                    domain="developer",
                                    role_name_en=record.role_name_en,
                                    source_id=record.record_id,
                                    content=record.content[:12000],
                                    timestamp=record.timestamp,
                                    score=score,
                                )
                            )

        hits.sort(key=lambda hit: (hit.score, hit.timestamp), reverse=True)
        selected = tuple(hits[: request.top_k])
        audit_id = uuid.uuid4().hex
        DeveloperMemoryStore(
            developer_session_id, data_root=self.developer_root
        ).append(
            request.role_name_en or roles[0].name_en,
            "system",
            f"受控全记忆查询 audit_id={audit_id} domains={','.join(sorted(domains))} hits={len(selected)}",
        )
        return DeveloperMemoryQueryResult(audit_id=audit_id, hits=selected)

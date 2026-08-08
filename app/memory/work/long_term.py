"""后端维护的版本化文本工作长期记忆 JSONL。"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path

from .models import (
    WorkMemoryKind,
    WorkMemoryRecord,
    WorkMemoryScope,
    WorkMemoryStatus,
    utc_now,
)
from .paths import resolve_work_memory_path


class WorkLongTermMemoryCorrupted(RuntimeError):
    pass


class LongTermWorkMemoryStore:
    def __init__(
        self,
        scope: WorkMemoryScope,
        *,
        work_root: Path | None = None,
    ) -> None:
        self.scope = scope
        self.work_root = work_root
        self._lock = threading.RLock()

    @property
    def file(self) -> Path:
        directory = resolve_work_memory_path(
            self.scope.role_name_en,
            self.scope.work_user_namespace,
            "long_term",
            work_root=self.work_root,
            create=True,
        )
        return directory / "memories.jsonl"

    def _events(self) -> list[WorkMemoryRecord]:
        if not self.file.exists():
            return []
        records: list[WorkMemoryRecord] = []
        with self.file.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    records.append(WorkMemoryRecord.model_validate_json(line))
                except (ValueError, json.JSONDecodeError) as exc:
                    raise WorkLongTermMemoryCorrupted(
                        f"工作长期记忆损坏: {self.file}:{line_number}"
                    ) from exc
        return records

    def records(self, *, include_history: bool = False) -> list[WorkMemoryRecord]:
        latest: dict[str, WorkMemoryRecord] = {}
        for record in self._events():
            latest[record.id] = record
        values = list(latest.values())
        if not include_history:
            values = [record for record in values if record.status == WorkMemoryStatus.CURRENT]
        return values

    def _append(self, record: WorkMemoryRecord) -> None:
        with self.file.open("a", encoding="utf-8") as stream:
            stream.write(record.model_dump_json() + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def upsert(
        self,
        kind: WorkMemoryKind,
        key: str,
        value: str,
        *,
        source: str,
        confidence: float,
        idempotency_key: str,
        statistics_delta: dict[str, float] | None = None,
    ) -> WorkMemoryRecord:
        with self._lock:
            events = self._events()
            for record in reversed(events):
                if record.idempotency_key == idempotency_key:
                    return record
            current = next(
                (
                    record
                    for record in self.records()
                    if record.kind == kind and record.key == key
                ),
                None,
            )
            statistics = dict(current.statistics if current else {})
            for name, amount in (statistics_delta or {}).items():
                statistics[name] = statistics.get(name, 0) + amount
            if current:
                superseded = current.model_copy(
                    update={"status": WorkMemoryStatus.SUPERSEDED, "last_observed_at": utc_now()}
                )
                self._append(superseded)
            record = WorkMemoryRecord(
                id=uuid.uuid4().hex,
                kind=kind,
                key=key,
                value=value,
                source=source,
                confidence=confidence,
                statistics=statistics,
                first_observed_at=current.first_observed_at if current else utc_now(),
                last_observed_at=utc_now(),
                supersedes=current.id if current else None,
                idempotency_key=idempotency_key,
            )
            self._append(record)
            return record

    def search(
        self,
        query: str,
        *,
        kinds: tuple[WorkMemoryKind, ...] = (),
        top_k: int = 8,
    ) -> list[WorkMemoryRecord]:
        terms = {part.casefold() for part in query.split() if part}
        scored: list[tuple[int, WorkMemoryRecord]] = []
        for record in self.records():
            if kinds and record.kind not in kinds:
                continue
            haystack = f"{record.kind.value} {record.key} {record.value}".casefold()
            score = sum(term in haystack for term in terms)
            if not terms or score:
                scored.append((score, record))
        scored.sort(key=lambda item: (item[0], item[1].last_observed_at), reverse=True)
        return [record for _, record in scored[: max(1, min(top_k, 50))]]

    def delete(self, memory_id: str) -> bool:
        with self._lock:
            current = next(
                (record for record in self.records(include_history=True) if record.id == memory_id),
                None,
            )
            if current is None or current.status == WorkMemoryStatus.DELETED:
                return False
            self._append(current.model_copy(update={"status": WorkMemoryStatus.DELETED}))
            return True

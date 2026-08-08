"""七天工作原始事件 JSONL 存档；默认不参与任何 Agent 上下文。"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pydantic import Field

from .models import WorkMemoryScope, WorkModel, utc_now
from .paths import resolve_work_memory_path
from .short_term import validate_job_id


REDACTED = "[REDACTED]"
_SECRET_KEY_RE = re.compile(
    r"(?:api[_-]?key|password|passwd|secret|token|authorization|cookie|developer[_-]?key)",
    re.I,
)
_DEVELOPER_CODE_RE = re.compile(r"dve_ytmmi_[A-Za-z0-9_-]{1,256}")
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]{8,}")
_INLINE_SECRET_RE = re.compile(
    r"(?i)(--?(?:password|token|secret|api[_-]?key)[=\s]+)([^\s]+)"
)


def redact_work_payload(value: Any, *, key: str = "") -> Any:
    if key and _SECRET_KEY_RE.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): redact_work_payload(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_work_payload(item) for item in value]
    if isinstance(value, str):
        text = _DEVELOPER_CODE_RE.sub("dve_ytmmi_[REDACTED]", value)
        text = _BEARER_RE.sub("Bearer [REDACTED]", text)
        text = _INLINE_SECRET_RE.sub(r"\1[REDACTED]", text)
        return text
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


class WorkArchiveRecord(WorkModel):
    schema_version: str = "companionheart.work-archive.v1"
    archive_id: str = Field(..., min_length=8, max_length=128)
    job_id: str = Field(..., min_length=8, max_length=128)
    event_type: str = Field(..., min_length=1, max_length=128)
    timestamp: str = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
    include_in_agent_context: bool = False


class WorkArchiveStore:
    RETENTION_DAYS = 7

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
    def directory(self) -> Path:
        return resolve_work_memory_path(
            self.scope.role_name_en,
            self.scope.work_user_namespace,
            "archive",
            "raw",
            work_root=self.work_root,
            create=True,
        )

    def file_for(self, day: date) -> Path:
        return self.directory / f"{day.isoformat()}.jsonl"

    def append(
        self,
        job_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> WorkArchiveRecord:
        job = validate_job_id(job_id)
        timestamp = now or datetime.now(timezone.utc)
        record = WorkArchiveRecord(
            archive_id=uuid.uuid4().hex,
            job_id=job,
            event_type=event_type,
            timestamp=timestamp.isoformat(),
            payload=redact_work_payload(payload),
        )
        with self._lock:
            with self.file_for(timestamp.date()).open("a", encoding="utf-8") as stream:
                stream.write(record.model_dump_json() + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        return record

    def read_day(self, day: date) -> list[WorkArchiveRecord]:
        path = self.file_for(day)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as stream:
            return [WorkArchiveRecord.model_validate_json(line) for line in stream if line.strip()]

    def cleanup(self, *, today: date | None = None) -> list[Path]:
        current = today or datetime.now(timezone.utc).date()
        oldest_allowed = current - timedelta(days=self.RETENTION_DAYS - 1)
        deleted: list[Path] = []
        with self._lock:
            for path in self.directory.glob("*.jsonl"):
                try:
                    day = date.fromisoformat(path.stem)
                except ValueError:
                    continue
                if day < oldest_allowed:
                    path.unlink()
                    deleted.append(path)
        return deleted

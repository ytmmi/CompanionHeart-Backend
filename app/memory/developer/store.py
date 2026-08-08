"""开发者独立 JSONL 会话存储；不复用生活或普通工作记忆。"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.memory.paths import validate_role_name
from app.memory.work.models import utc_now


DEVELOPER_MEMORY_ROOT = Path(__file__).resolve().parents[1] / "developer_memory"
_SESSION_RE = re.compile(r"^[0-9a-f]{32}$")


def validate_developer_session_id(value: str) -> str:
    if not isinstance(value, str) or not _SESSION_RE.fullmatch(value):
        raise ValueError("developer session id 不合法")
    return value


class DeveloperMemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "companionheart.developer-message.v1"
    record_id: str = Field(..., min_length=8, max_length=128)
    sequence: int = Field(..., ge=1)
    session_id: str
    developer_name: Literal["ytmmi"] = "ytmmi"
    developer_marker: Literal["dve:ytmmi"] = "dve:ytmmi"
    role_name_en: str
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1, max_length=24000)
    timestamp: str = Field(default_factory=utc_now)


class DeveloperMemoryStore:
    def __init__(
        self,
        session_id: str,
        *,
        developer_name: str = "ytmmi",
        data_root: Path | None = None,
    ) -> None:
        if developer_name != "ytmmi":
            raise ValueError("当前只注册开发者 ytmmi")
        self.session_id = validate_developer_session_id(session_id)
        self.developer_name = developer_name
        self.data_root = (data_root or DEVELOPER_MEMORY_ROOT).resolve()
        self._lock = threading.RLock()

    @property
    def session_directory(self) -> Path:
        root = (self.data_root / self.developer_name / "sessions").resolve()
        target = (root / self.session_id).resolve()
        if root != target.parent:
            raise ValueError("developer session path 越界")
        target.mkdir(parents=True, exist_ok=True)
        return target

    @property
    def file(self) -> Path:
        return self.session_directory / "conversation.jsonl"

    def records(self) -> list[DeveloperMemoryRecord]:
        if not self.file.exists():
            return []
        values: list[DeveloperMemoryRecord] = []
        with self.file.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    record = DeveloperMemoryRecord.model_validate_json(line)
                except (ValueError, json.JSONDecodeError) as exc:
                    raise RuntimeError(
                        f"开发会话记忆损坏: {self.file}:{line_number}"
                    ) from exc
                if record.session_id != self.session_id:
                    raise RuntimeError("开发会话文件包含其他 session")
                values.append(record)
        if [record.sequence for record in values] != list(range(1, len(values) + 1)):
            raise RuntimeError("开发会话 sequence 不连续")
        return values

    def append(
        self, role_name_en: str, role: Literal["user", "assistant", "system"], content: str
    ) -> DeveloperMemoryRecord:
        role_name = validate_role_name(role_name_en).casefold()
        text = content.strip()
        if not text:
            raise ValueError("开发记忆内容不能为空")
        with self._lock:
            existing = self.records()
            record = DeveloperMemoryRecord(
                record_id=uuid.uuid4().hex,
                sequence=len(existing) + 1,
                session_id=self.session_id,
                role_name_en=role_name,
                role=role,
                content=text,
            )
            with self.file.open("a", encoding="utf-8") as stream:
                stream.write(record.model_dump_json() + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return record

    def context_messages(self, *, max_messages: int = 100) -> list[dict[str, str]]:
        return [
            {"role": record.role, "content": record.content}
            for record in self.records()[-max(1, min(max_messages, 200)) :]
        ]

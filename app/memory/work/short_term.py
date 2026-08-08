"""每个工作 job 的 append-only JSONL 短期事件存储。"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path

from .models import WorkCommand, WorkEvent, WorkEventType, WorkMemoryScope, WorkStatus
from .paths import resolve_work_memory_path


_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,127}$")


class InvalidWorkJob(ValueError):
    pass


class InvalidWorkTransition(ValueError):
    pass


class WorkEventLogCorrupted(RuntimeError):
    pass


_STATE_EVENT: dict[WorkEventType, WorkStatus] = {
    WorkEventType.JOB_CREATED: WorkStatus.CREATED,
    WorkEventType.JOB_QUEUED: WorkStatus.QUEUED,
    WorkEventType.JOB_RUNNING: WorkStatus.RUNNING,
    WorkEventType.JOB_NEEDS_INPUT: WorkStatus.NEEDS_INPUT,
    WorkEventType.JOB_SUCCEEDED: WorkStatus.SUCCEEDED,
    WorkEventType.JOB_FAILED: WorkStatus.FAILED,
    WorkEventType.JOB_CANCELLED: WorkStatus.CANCELLED,
}
_ALLOWED_TRANSITIONS: dict[WorkStatus | None, set[WorkStatus]] = {
    None: {WorkStatus.CREATED},
    WorkStatus.CREATED: {WorkStatus.QUEUED, WorkStatus.CANCELLED},
    WorkStatus.QUEUED: {WorkStatus.RUNNING, WorkStatus.FAILED, WorkStatus.CANCELLED},
    WorkStatus.RUNNING: {
        WorkStatus.NEEDS_INPUT,
        WorkStatus.SUCCEEDED,
        WorkStatus.FAILED,
        WorkStatus.CANCELLED,
    },
    WorkStatus.NEEDS_INPUT: {WorkStatus.RUNNING, WorkStatus.FAILED, WorkStatus.CANCELLED},
    WorkStatus.SUCCEEDED: set(),
    WorkStatus.FAILED: set(),
    WorkStatus.CANCELLED: set(),
}


def validate_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or not _ID_RE.fullmatch(job_id):
        raise InvalidWorkJob("job_id 必须是 8..128 位安全标识")
    return job_id


class WorkJobStore:
    def __init__(
        self,
        scope: WorkMemoryScope,
        *,
        work_root: Path | None = None,
    ) -> None:
        self.scope = scope
        self.work_root = work_root
        self._locks: dict[str, threading.RLock] = {}
        self._locks_guard = threading.Lock()

    def _lock_for(self, job_id: str) -> threading.RLock:
        with self._locks_guard:
            return self._locks.setdefault(job_id, threading.RLock())

    def event_file(self, job_id: str, *, create: bool = False) -> Path:
        job = validate_job_id(job_id)
        directory = resolve_work_memory_path(
            self.scope.role_name_en,
            self.scope.work_user_namespace,
            "short_term",
            "jobs",
            job,
            work_root=self.work_root,
            create=create,
        )
        return directory / "events.jsonl"

    def command_file(self, job_id: str, *, create: bool = False) -> Path:
        job = validate_job_id(job_id)
        directory = resolve_work_memory_path(
            self.scope.role_name_en,
            self.scope.work_user_namespace,
            "short_term",
            "jobs",
            job,
            work_root=self.work_root,
            create=create,
        )
        return directory / "commands.jsonl"

    def list_job_ids(self) -> list[str]:
        directory = resolve_work_memory_path(
            self.scope.role_name_en,
            self.scope.work_user_namespace,
            "short_term",
            "jobs",
            work_root=self.work_root,
        )
        if not directory.exists():
            return []
        return sorted(
            path.name
            for path in directory.iterdir()
            if path.is_dir() and _ID_RE.fullmatch(path.name)
        )

    def read_commands(self, job_id: str) -> list[WorkCommand]:
        path = self.command_file(job_id)
        if not path.exists():
            return []
        commands: list[WorkCommand] = []
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    commands.append(WorkCommand.model_validate_json(line))
                except (ValueError, json.JSONDecodeError) as exc:
                    raise WorkEventLogCorrupted(
                        f"工作命令日志损坏: {path}:{line_number}"
                    ) from exc
        return commands

    def latest_command(self, job_id: str) -> WorkCommand | None:
        commands = self.read_commands(job_id)
        return commands[-1] if commands else None

    def save_command(self, command: WorkCommand) -> WorkCommand:
        if (
            command.origin_role_name_en.casefold() != self.scope.role_name_en.casefold()
            or command.work_user_namespace != self.scope.work_user_namespace
        ):
            raise InvalidWorkJob("WorkCommand 与 WorkJobStore scope 不一致")
        lock = self._lock_for(command.job_id)
        with lock:
            for existing in self.read_commands(command.job_id):
                if existing.command_id == command.command_id:
                    if existing != command:
                        raise InvalidWorkJob("相同 command_id 的命令正文不一致")
                    return existing
            path = self.command_file(command.job_id, create=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(command.model_dump_json() + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return command

    def read_events(self, job_id: str) -> list[WorkEvent]:
        path = self.event_file(job_id)
        if not path.exists():
            return []
        events: list[WorkEvent] = []
        with path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    events.append(WorkEvent.model_validate_json(line))
                except (ValueError, json.JSONDecodeError) as exc:
                    raise WorkEventLogCorrupted(
                        f"工作事件日志损坏: {path}:{line_number}"
                    ) from exc
        expected = list(range(1, len(events) + 1))
        if [event.sequence for event in events] != expected:
            raise WorkEventLogCorrupted(f"工作事件 sequence 不连续: {path}")
        return events

    def status(self, job_id: str) -> WorkStatus | None:
        state: WorkStatus | None = None
        for event in self.read_events(job_id):
            state = _STATE_EVENT.get(event.event_type, state)
        return state

    def create_job(self, command: WorkCommand) -> WorkEvent:
        if (
            command.origin_role_name_en.casefold() != self.scope.role_name_en.casefold()
            or command.work_user_namespace != self.scope.work_user_namespace
        ):
            raise InvalidWorkJob("WorkCommand 与 WorkJobStore scope 不一致")
        self.save_command(command)
        return self.append_event(
            command.job_id,
            command.command_id,
            WorkEventType.JOB_CREATED,
            summary=command.task,
            idempotency_key=f"create:{command.command_id}",
        )

    def append_event(
        self,
        job_id: str,
        command_id: str,
        event_type: WorkEventType,
        *,
        summary: str = "",
        tool_name: str | None = None,
        skill_name: str | None = None,
        error_code: str | None = None,
        questions: tuple[str, ...] = (),
        duration_ms: int | None = None,
        idempotency_key: str,
    ) -> WorkEvent:
        job = validate_job_id(job_id)
        if not _ID_RE.fullmatch(command_id):
            raise InvalidWorkJob("command_id 必须是 8..128 位安全标识")
        lock = self._lock_for(job)
        with lock:
            existing = self.read_events(job)
            for event in existing:
                if event.idempotency_key == idempotency_key:
                    return event
            current = None
            for event in existing:
                current = _STATE_EVENT.get(event.event_type, current)
            requested = _STATE_EVENT.get(event_type)
            if requested is not None and requested not in _ALLOWED_TRANSITIONS[current]:
                raise InvalidWorkTransition(f"非法工作状态转换: {current} -> {requested}")
            event = WorkEvent(
                event_id=uuid.uuid4().hex,
                job_id=job,
                command_id=command_id,
                sequence=len(existing) + 1,
                event_type=event_type,
                summary=summary,
                tool_name=tool_name,
                skill_name=skill_name,
                error_code=error_code,
                questions=questions,
                duration_ms=duration_ms,
                idempotency_key=idempotency_key,
            )
            path = self.event_file(job, create=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json() + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            return event

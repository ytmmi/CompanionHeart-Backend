"""异步工作协调器：唯一连接工作记忆和 AGENT_work 的后端组件。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.agent.work_sidecar import WorkAgentGateway
from app.memory.work import (
    LongTermWorkMemoryStore,
    WorkArchiveStore,
    WorkCommand,
    WorkEvent,
    WorkEventType,
    WorkJobStore,
    WorkMemoryKind,
    WorkMemoryScope,
    WorkResult,
    WorkStatus,
)


logger = logging.getLogger(__name__)
CompletionListener = Callable[[WorkMemoryScope, WorkResult], Awaitable[None]]
_TERMINAL = {WorkStatus.SUCCEEDED, WorkStatus.FAILED, WorkStatus.CANCELLED}


class WorkJobNotFound(LookupError):
    pass


class DuplicateWorkCommand(ValueError):
    pass


class WorkCoordinator:
    def __init__(
        self,
        scope: WorkMemoryScope,
        gateway: WorkAgentGateway,
        *,
        work_root: Path | None = None,
    ) -> None:
        self.scope = scope
        self.gateway = gateway
        self.jobs = WorkJobStore(scope, work_root=work_root)
        self.long_term = LongTermWorkMemoryStore(scope, work_root=work_root)
        self.archive = WorkArchiveStore(scope, work_root=work_root)
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._listeners: list[CompletionListener] = []

    def add_completion_listener(self, listener: CompletionListener) -> None:
        self._listeners.append(listener)

    def _lock(self, job_id: str) -> asyncio.Lock:
        return self._locks.setdefault(job_id, asyncio.Lock())

    def _find_by_command(self, command_id: str) -> WorkCommand | None:
        for job_id in self.jobs.list_job_ids():
            for command in self.jobs.read_commands(job_id):
                if command.command_id == command_id:
                    return command
        return None

    async def submit(self, command: WorkCommand) -> WorkEvent:
        existing = self._find_by_command(command.command_id)
        if existing is not None:
            if existing != command:
                raise DuplicateWorkCommand("相同 command_id 的命令正文不一致")
            events = self.jobs.read_events(existing.job_id)
            return events[-1]
        self.jobs.create_job(command)
        queued = self.jobs.append_event(
            command.job_id,
            command.command_id,
            WorkEventType.JOB_QUEUED,
            summary="工作任务已进入队列。",
            idempotency_key=f"queued:{command.command_id}",
        )
        self.archive.append(
            command.job_id,
            "command_submitted",
            command.model_dump(mode="json"),
        )
        self.archive.cleanup()
        self._schedule(command)
        return queued

    def _schedule(self, command: WorkCommand) -> None:
        active = self._tasks.get(command.job_id)
        if active is not None and not active.done():
            return
        task = asyncio.create_task(self._execute(command))
        self._tasks[command.job_id] = task
        task.add_done_callback(
            lambda done, job_id=command.job_id: (
                self._tasks.pop(job_id, None)
                if self._tasks.get(job_id) is done
                else None
            )
        )

    async def _execute(self, command: WorkCommand) -> None:
        async with self._lock(command.job_id):
            current = self.jobs.status(command.job_id)
            if current in _TERMINAL:
                return
            if current != WorkStatus.RUNNING:
                self.jobs.append_event(
                    command.job_id,
                    command.command_id,
                    WorkEventType.JOB_RUNNING,
                    summary="工作 Agent 正在执行。",
                    idempotency_key=f"running:{command.command_id}",
                )
            try:
                result = await self.gateway.run(command)
            except asyncio.CancelledError:
                if self.jobs.status(command.job_id) not in _TERMINAL:
                    self._append_result_event(
                        WorkResult(
                            command_id=command.command_id,
                            job_id=command.job_id,
                            status=WorkStatus.CANCELLED,
                            user_facing_summary="工作任务已取消。",
                        )
                    )
                return
            except Exception:
                logger.exception("AGENT_work 执行失败 job=%s", command.job_id)
                result = WorkResult(
                    command_id=command.command_id,
                    job_id=command.job_id,
                    status=WorkStatus.FAILED,
                    error_code="WORK_SIDECAR_UNAVAILABLE",
                    user_facing_summary="工作 Agent 暂时不可用。",
                )
            if result.command_id != command.command_id or result.job_id != command.job_id:
                result = WorkResult(
                    command_id=command.command_id,
                    job_id=command.job_id,
                    status=WorkStatus.FAILED,
                    error_code="WORK_RESULT_ID_MISMATCH",
                    user_facing_summary="工作 Agent 返回了不匹配的任务结果。",
                )
            if self.jobs.status(command.job_id) not in _TERMINAL:
                self._append_result_event(result)
            self.archive.append(
                command.job_id,
                "work_result",
                result.model_dump(mode="json"),
            )
            if result.status == WorkStatus.SUCCEEDED and not command.suppress_normal_memory_updates:
                self.long_term.upsert(
                    WorkMemoryKind.USAGE_FREQUENCY,
                    "work_jobs.successful",
                    "成功完成的工作任务频率",
                    source="system",
                    confidence=1.0,
                    statistics_delta={"executions": 1},
                    idempotency_key=f"job-success:{command.job_id}",
                )
            if result.status in _TERMINAL:
                await self._notify(result)

    def _append_result_event(self, result: WorkResult) -> WorkEvent:
        event_types = {
            WorkStatus.SUCCEEDED: WorkEventType.JOB_SUCCEEDED,
            WorkStatus.FAILED: WorkEventType.JOB_FAILED,
            WorkStatus.CANCELLED: WorkEventType.JOB_CANCELLED,
            WorkStatus.NEEDS_INPUT: WorkEventType.JOB_NEEDS_INPUT,
        }
        return self.jobs.append_event(
            result.job_id,
            result.command_id,
            event_types[result.status],
            summary=result.user_facing_summary,
            error_code=result.error_code,
            questions=result.questions,
            idempotency_key=f"result:{result.command_id}:{result.status.value}",
        )

    async def _notify(self, result: WorkResult) -> None:
        for listener in tuple(self._listeners):
            try:
                await listener(self.scope, result)
            except Exception:
                logger.exception("工作任务完成监听器失败 job=%s", result.job_id)

    async def wait(self, job_id: str) -> WorkStatus | None:
        task = self._tasks.get(job_id)
        if task is not None:
            await task
        return self.jobs.status(job_id)

    async def cancel(self, job_id: str) -> bool:
        command = self.jobs.latest_command(job_id)
        if command is None:
            raise WorkJobNotFound(job_id)
        if self.jobs.status(job_id) in _TERMINAL:
            return False
        await self.gateway.abort(job_id)
        self.jobs.append_event(
            job_id,
            command.command_id,
            WorkEventType.JOB_CANCELLED,
            summary="工作任务已取消。",
            idempotency_key=f"cancel:{command.command_id}",
        )
        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
        return True

    async def resume(self, job_id: str, additional_context: str) -> WorkEvent:
        if self.jobs.status(job_id) != WorkStatus.NEEDS_INPUT:
            raise ValueError("只有 needs_input 任务可以恢复")
        previous = self.jobs.latest_command(job_id)
        if previous is None:
            raise WorkJobNotFound(job_id)
        command = previous.model_copy(
            update={
                "command_id": uuid.uuid4().hex,
                "context_summary": (previous.context_summary + "\n" + additional_context).strip()[:12000],
            }
        )
        self.jobs.save_command(command)
        event = self.jobs.append_event(
            job_id,
            command.command_id,
            WorkEventType.JOB_RUNNING,
            summary="已补充信息，工作 Agent 继续执行。",
            idempotency_key=f"resume:{command.command_id}",
        )
        self._schedule(command)
        return event

    async def recover_interrupted(self) -> list[str]:
        """重启时将无法安全重放的 queued/running job 置为真实失败。"""
        recovered: list[str] = []
        for job_id in self.jobs.list_job_ids():
            state = self.jobs.status(job_id)
            if state not in {WorkStatus.QUEUED, WorkStatus.RUNNING}:
                continue
            command = self.jobs.latest_command(job_id)
            if command is None:
                continue
            self.jobs.append_event(
                job_id,
                command.command_id,
                WorkEventType.JOB_FAILED,
                summary="后端重启中断任务；为避免重复副作用，未自动重放。",
                error_code="COORDINATOR_RESTARTED",
                idempotency_key=f"restart-failed:{command.command_id}",
            )
            recovered.append(job_id)
        return recovered

"""AGENT_work 的最小执行内核与双重工具白名单。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

try:
    from .schemas import WorkCommand, WorkResult, WorkStatus, utc_now
except ImportError:  # 直接运行 server.py
    from schemas import WorkCommand, WorkResult, WorkStatus, utc_now


ToolHandler = Callable[[WorkCommand], Awaitable[str]]


async def _test_echo(command: WorkCommand) -> str:
    """只用于协议/协调器测试；不访问文件、网络、环境或记忆。"""
    await asyncio.sleep(0)
    return command.task


class WorkAgentEngine:
    """一次只允许每个 job 有一个执行任务的无状态 sidecar 内核。"""

    def __init__(self, *, enable_test_tools: bool | None = None) -> None:
        if enable_test_tools is None:
            enable_test_tools = os.getenv("WORK_AGENT_ENABLE_TEST_TOOLS") == "1"
        self._tools: dict[str, ToolHandler] = {}
        if enable_test_tools:
            self._tools["test.echo"] = _test_echo
        self._active: dict[str, asyncio.Task[WorkResult]] = {}

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def effective_capabilities(self, command: WorkCommand) -> tuple[str, ...]:
        """进程白名单与任务白名单取交集，客户端不能扩大权限。"""
        return tuple(name for name in command.allowed_capabilities if name in self._tools)

    async def _execute(self, command: WorkCommand) -> WorkResult:
        started_at = utc_now()
        capabilities = self.effective_capabilities(command)
        if not capabilities:
            return WorkResult(
                command_id=command.command_id,
                job_id=command.job_id,
                status=WorkStatus.FAILED,
                error_code="NO_ALLOWED_CAPABILITY",
                user_facing_summary="工作 Agent 没有本任务可用的工具权限。",
                started_at=started_at,
                finished_at=utc_now(),
            )

        # 阶段 7 只注册一个显式测试工具。正式工具必须逐项加入进程白名单，
        # 并继续由 command.allowed_capabilities 收窄。
        tool_name = capabilities[0]
        try:
            summary = await asyncio.wait_for(
                self._tools[tool_name](command), timeout=command.timeout_seconds
            )
        except asyncio.CancelledError:
            return WorkResult(
                command_id=command.command_id,
                job_id=command.job_id,
                status=WorkStatus.CANCELLED,
                user_facing_summary="工作任务已取消。",
                started_at=started_at,
                finished_at=utc_now(),
            )
        except TimeoutError:
            return WorkResult(
                command_id=command.command_id,
                job_id=command.job_id,
                status=WorkStatus.FAILED,
                error_code="WORK_AGENT_TIMEOUT",
                user_facing_summary="工作 Agent 执行超时。",
                started_at=started_at,
                finished_at=utc_now(),
            )
        except Exception:
            return WorkResult(
                command_id=command.command_id,
                job_id=command.job_id,
                status=WorkStatus.FAILED,
                error_code="WORK_AGENT_EXECUTION_FAILED",
                user_facing_summary="工作 Agent 执行失败。",
                started_at=started_at,
                finished_at=utc_now(),
            )
        return WorkResult(
            command_id=command.command_id,
            job_id=command.job_id,
            status=WorkStatus.SUCCEEDED,
            user_facing_summary=summary,
            started_at=started_at,
            finished_at=utc_now(),
        )

    async def run(self, command: WorkCommand) -> WorkResult:
        if command.job_id in self._active:
            raise ValueError("job 已在执行")
        task = asyncio.create_task(self._execute(command))
        self._active[command.job_id] = task
        try:
            return await task
        finally:
            self._active.pop(command.job_id, None)

    def abort(self, job_id: str) -> bool:
        task = self._active.get(job_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True

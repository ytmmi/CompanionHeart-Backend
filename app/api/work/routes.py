"""角色+用户隔离的异步工作任务 API。"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.agent.work import (
    WorkCompletionBroker,
    WorkCompletionReporter,
    WorkCoordinator,
    WorkCoordinatorRegistry,
    WorkJobNotFound,
    WorkNotification,
)
from app.memory.roles import RoleConfigError
from app.memory.work import WorkCommand, WorkEvent, WorkResult, WorkStatus


router = APIRouter(prefix="/api/work/jobs", tags=["Work"])
notifications_router = APIRouter(prefix="/api/work/notifications", tags=["Work"])
_completion_broker = WorkCompletionBroker()
_completion_reporter: WorkCompletionReporter | None = None


async def _engine_provider():
    # 延迟导入，避免 agent/work API 模块初始化环。
    from app.api.agent.routes import get_agent_engine

    return await get_agent_engine()


async def _report_completion(scope, result) -> None:
    global _completion_reporter
    if _completion_reporter is None:
        _completion_reporter = WorkCompletionReporter(_engine_provider, _completion_broker)
    await _completion_reporter.handle(scope, result)


_registry = WorkCoordinatorRegistry(completion_listeners=(_report_completion,))
_TERMINAL = {WorkStatus.SUCCEEDED, WorkStatus.FAILED, WorkStatus.CANCELLED}


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkJobCreateRequest(APIModel):
    role_name_en: str | None = None
    task: str = Field(..., min_length=1, max_length=8000)
    acceptance_criteria: tuple[str, ...] = Field(default=(), max_length=32)
    constraints: tuple[str, ...] = Field(default=(), max_length=32)
    allowed_capabilities: tuple[str, ...] = Field(default=(), max_length=64)
    context_summary: str = Field("", max_length=12000)
    timeout_seconds: int = Field(600, ge=1, le=3600)


class WorkResumeRequest(APIModel):
    role_name_en: str | None = None
    additional_context: str = Field(..., min_length=1, max_length=12000)


class WorkJobView(APIModel):
    job_id: str
    command_id: str
    role_name_en: str
    status: WorkStatus
    user_facing_summary: str = ""
    questions: tuple[str, ...] = ()
    error_code: str | None = None
    updated_at: str


StableUser = Annotated[
    str,
    Header(
        alias="X-Companion-User-Id",
        description="由可信本地壳层/认证层提供；桌面单用户缺省为 local-default",
    ),
]


def configure_work_registry(registry: WorkCoordinatorRegistry) -> None:
    """应用启动/测试注入；不会接受来自 HTTP 的数据根。"""
    global _registry
    _registry = registry


def configure_completion_broker(broker: WorkCompletionBroker) -> None:
    global _completion_broker, _completion_reporter
    _completion_broker = broker
    _completion_reporter = None


def _coordinator(role_name_en: str | None, stable_user_id: str) -> WorkCoordinator:
    try:
        return _registry.get(role_name_en, stable_user_id)
    except (RoleConfigError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _view(coordinator: WorkCoordinator, job_id: str) -> WorkJobView:
    command = coordinator.jobs.latest_command(job_id)
    events = coordinator.jobs.read_events(job_id)
    if command is None or not events:
        # 对错误 role/user scope 一律返回 404，不泄露 job 是否存在。
        raise HTTPException(status_code=404, detail="工作任务不存在")
    latest = events[-1]
    status = coordinator.jobs.status(job_id)
    assert status is not None
    return WorkJobView(
        job_id=job_id,
        command_id=latest.command_id,
        role_name_en=coordinator.scope.role_name_en,
        status=status,
        user_facing_summary=latest.summary,
        questions=latest.questions,
        error_code=latest.error_code,
        updated_at=latest.timestamp,
    )


@router.post("", response_model=WorkJobView, status_code=202)
async def create_job(
    body: WorkJobCreateRequest,
    stable_user_id: StableUser = "local-default",
) -> WorkJobView:
    coordinator = _coordinator(body.role_name_en, stable_user_id)
    command = WorkCommand(
        command_id=uuid.uuid4().hex,
        job_id=uuid.uuid4().hex,
        origin_role_name_en=coordinator.scope.role_name_en,
        work_user_namespace=coordinator.scope.work_user_namespace,
        task=body.task,
        acceptance_criteria=body.acceptance_criteria,
        constraints=body.constraints,
        allowed_capabilities=body.allowed_capabilities,
        context_summary=body.context_summary,
        timeout_seconds=body.timeout_seconds,
    )
    await coordinator.submit(command)
    return _view(coordinator, command.job_id)


@router.get("/{job_id}", response_model=WorkJobView)
async def get_job(
    job_id: str,
    role_name_en: str | None = None,
    stable_user_id: StableUser = "local-default",
) -> WorkJobView:
    return _view(_coordinator(role_name_en, stable_user_id), job_id)


@router.get("/{job_id}/events", response_model=list[WorkEvent])
async def get_job_events(
    job_id: str,
    role_name_en: str | None = None,
    after_sequence: int = Query(0, ge=0),
    stable_user_id: StableUser = "local-default",
) -> list[WorkEvent]:
    coordinator = _coordinator(role_name_en, stable_user_id)
    _view(coordinator, job_id)
    return [
        event
        for event in coordinator.jobs.read_events(job_id)
        if event.sequence > after_sequence
    ]


@router.get("/{job_id}/stream")
async def stream_job_events(
    job_id: str,
    request: Request,
    role_name_en: str | None = None,
    after_sequence: int = Query(0, ge=0),
    stable_user_id: StableUser = "local-default",
) -> StreamingResponse:
    coordinator = _coordinator(role_name_en, stable_user_id)
    _view(coordinator, job_id)

    async def event_stream():
        cursor = after_sequence
        while True:
            if await request.is_disconnected():
                return
            events = [
                event
                for event in coordinator.jobs.read_events(job_id)
                if event.sequence > cursor
            ]
            for event in events:
                cursor = event.sequence
                yield f"data: {json.dumps(event.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            status = coordinator.jobs.status(job_id)
            if status in _TERMINAL or status == WorkStatus.NEEDS_INPUT:
                yield "data: [DONE]\n\n"
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{job_id}/cancel", response_model=WorkJobView)
async def cancel_job(
    job_id: str,
    role_name_en: str | None = None,
    stable_user_id: StableUser = "local-default",
) -> WorkJobView:
    coordinator = _coordinator(role_name_en, stable_user_id)
    _view(coordinator, job_id)
    try:
        await coordinator.cancel(job_id)
    except WorkJobNotFound as exc:
        raise HTTPException(status_code=404, detail="工作任务不存在") from exc
    return _view(coordinator, job_id)


@router.post("/{job_id}/resume", response_model=WorkJobView, status_code=202)
async def resume_job(
    job_id: str,
    body: WorkResumeRequest,
    stable_user_id: StableUser = "local-default",
) -> WorkJobView:
    coordinator = _coordinator(body.role_name_en, stable_user_id)
    _view(coordinator, job_id)
    try:
        await coordinator.resume(job_id, body.additional_context)
    except WorkJobNotFound as exc:
        raise HTTPException(status_code=404, detail="工作任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _view(coordinator, job_id)


@notifications_router.get("", response_model=list[WorkNotification])
async def list_notifications(
    role_name_en: str | None = None,
    consume: bool = True,
    stable_user_id: StableUser = "local-default",
) -> list[WorkNotification]:
    try:
        scope = _registry.scope_for(role_name_en, stable_user_id)
    except (RoleConfigError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _completion_broker.read(scope, consume=consume)


@notifications_router.get("/stream")
async def stream_notifications(
    request: Request,
    role_name_en: str | None = None,
    stable_user_id: StableUser = "local-default",
) -> StreamingResponse:
    try:
        scope = _registry.scope_for(role_name_en, stable_user_id)
    except (RoleConfigError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_stream():
        while True:
            if await request.is_disconnected():
                return
            notifications = _completion_broker.read(scope, consume=True)
            for notification in notifications:
                yield f"data: {notification.model_dump_json()}\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")

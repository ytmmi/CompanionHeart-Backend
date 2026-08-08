"""AGENT_work 的严格 HTTP 客户端。"""

from __future__ import annotations

from typing import Protocol

from app.memory.work import WorkCommand, WorkResult
from app.plugins.client import PluginHTTPClient


class WorkAgentGateway(Protocol):
    async def run(self, command: WorkCommand) -> WorkResult: ...

    async def abort(self, job_id: str) -> bool: ...


class WorkAgentClient:
    def __init__(self, base_url: str = "http://localhost:8310", timeout: int = 620):
        self.client = PluginHTTPClient(base_url, timeout)

    async def health_check(self) -> bool:
        return await self.client.health_check()

    async def info(self) -> dict:
        response = await self.client.get("/info")
        response.raise_for_status()
        return response.json()

    async def run(self, command: WorkCommand) -> WorkResult:
        response = await self.client.post("/run", json=command.model_dump(mode="json"))
        if response.status_code != 200:
            raise RuntimeError(f"AGENT_work 调用失败({response.status_code})")
        return WorkResult.model_validate(response.json())

    async def abort(self, job_id: str) -> bool:
        response = await self.client.post("/abort", json={"job_id": job_id})
        if response.status_code != 200:
            return False
        return bool(response.json().get("ok"))

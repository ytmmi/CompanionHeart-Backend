"""AGENT_work 本机 HTTP sidecar。"""

from __future__ import annotations

import argparse

import uvicorn
from fastapi import FastAPI, HTTPException

try:
    from .engine import WorkAgentEngine
    from .schemas import AbortRequest, WorkCommand, WorkResult
except ImportError:  # PluginManager 从插件目录直接执行本文件
    from engine import WorkAgentEngine
    from schemas import AbortRequest, WorkCommand, WorkResult


app = FastAPI(title="CompanionHeart AGENT_work", version="0.1.0")
engine = WorkAgentEngine()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "AGENT_work"}


@app.get("/info")
async def info() -> dict:
    return {
        "name": "AGENT_work",
        "version": "0.1.0",
        "protocol": "companionheart.work-command.v1",
        "tools": list(engine.tool_names),
        "life_memory_access": False,
    }


@app.post("/run", response_model=WorkResult)
async def run(command: WorkCommand) -> WorkResult:
    try:
        return await engine.run(command)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/abort")
async def abort(request: AbortRequest) -> dict:
    return {"ok": engine.abort(request.job_id)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8310)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")

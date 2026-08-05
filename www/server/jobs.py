"""后台任务（安装 / 启动）的流式日志。

安装、启动都是慢操作，接口立刻返回 job_id，前端按 since 增量轮询日志行。
任务是纯内存态，只留最近 20 个。
"""
from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def job_new(kind: str, name: str) -> str:
    jid = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[jid] = {"id": jid, "kind": kind, "name": name, "status": "running",
                      "lines": [], "started": time.time()}
        # 只留最近 20 个任务
        if len(_jobs) > 20:
            for old in sorted(_jobs, key=lambda k: _jobs[k]["started"])[:-20]:
                _jobs.pop(old, None)
    return jid


def job_log(jid: str, line: str) -> None:
    with _jobs_lock:
        j = _jobs.get(jid)
        if j is not None:
            j["lines"].append(line.rstrip("\n"))


def job_done(jid: str, ok: bool, msg: str = "") -> None:
    with _jobs_lock:
        j = _jobs.get(jid)
        if j is not None:
            j["status"] = "ok" if ok else "error"
            j["message"] = msg
            j["ended"] = time.time()


def get_job(jid: str, since: int = 0) -> dict:
    with _jobs_lock:
        j = _jobs.get(jid)
        if j is None:
            return {"ok": False, "error": "任务不存在或已过期"}
        lines = j["lines"][since:]
        return {"ok": True, "id": jid, "kind": j["kind"], "name": j["name"],
                "status": j["status"], "message": j.get("message", ""),
                "lines": lines, "next": since + len(lines)}


def stream_subprocess(jid: str, cmd: list[str], cwd: Path | None = None,
                      env: dict | None = None) -> int:
    """跑子进程，stdout/stderr 合并逐行推进 job 日志；返回退出码"""
    job_log(jid, f"$ {' '.join(cmd)}")
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env={**os.environ, **env} if env else None,
        )
    except FileNotFoundError as e:
        job_log(jid, f"[启动失败] {e}")
        return 127
    for line in proc.stdout:
        job_log(jid, line)
    proc.wait()
    return proc.returncode

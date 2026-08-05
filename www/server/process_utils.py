"""按端口反查 PID / 结束进程 —— 跨进程停插件的基础。

设置服务（:17999）与后端 FastAPI（:18000）是两个进程，后端 PluginManager
在自己的 self.processes 里握着插件子进程句柄，本进程拿不到。所以生命周期
操作一律按「端口」而非「句柄」来做，谁拉起的都能停。
"""
from __future__ import annotations

import subprocess

from .paths import logger


def pids_on_port(port: int) -> list[int]:
    """netstat 找监听指定端口的 PID（Windows）"""
    pids: set[int] = set()
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, text=True, timeout=8).stdout
    except Exception:
        return []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5 or not parts[0].upper().startswith("TCP"):
            continue
        local = parts[1]
        # 本地地址以 :port 结尾，且是 LISTENING（或外部地址通配，兼容中文系统 state 本地化）
        if not local.endswith(f":{port}"):
            continue
        if "LISTENING" in line.upper() or parts[2] in ("0.0.0.0:0", "*:*", "[::]:0"):
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                pass
    return sorted(pids)


def kill_pid(pid: int) -> bool:
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                       capture_output=True, text=True, timeout=10)
        return True
    except Exception as e:
        logger.error("结束进程 %d 失败：%s", pid, e)
        return False

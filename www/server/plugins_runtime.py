"""插件的启动 / 停止 / 卸载。

启动用 detached 子进程（脱离本进程，设置服务重启也不会带走插件）；
停止按端口反查 PID 再杀，无论当初是谁拉起的都能停；
卸载移入 .trash 而非硬删，可逆。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .http_client import http_request
from .jobs import job_done, job_log, job_new
from .paths import CONFIG_PATHS, PLUGIN_ROOT, PLUGIN_TRASH, logger
from .plugins_registry import NON_PLUGIN_DIRS, autostart_map, plugin_manifest
from .ports import port_in_use
from .process_utils import kill_pid, pids_on_port
from .yaml_io import dig, read_yaml

# 启动等待健康检查的超时（秒），按类型区分：ASR 要加载模型，最慢
_START_HEALTH_TIMEOUT = {"asr": 45, "agent": 25, "tts": 20, "llm": 20}


def _build_agent_env() -> dict:
    """复刻 app/main.py:_build_agent_sidecar_env，从 llm/config.yaml 生成 sidecar env"""
    llm = read_yaml(CONFIG_PATHS["llm"])
    mode = llm.get("mode", "openai")
    conf = llm.get(mode, {}) or {}
    base_url = str(conf.get("base_url") or "").rstrip("/")
    env = {
        "LLM_MODEL": str(conf.get("model", "")),
        "LLM_API_KEY": str(conf.get("api_key", "")),
        "LLM_TIMEOUT": str(conf.get("timeout", 60)),
    }
    if mode == "anthropic":
        env["LLM_PROVIDER"] = "anthropic"
        # 仅在指向非官方端点（代理/中转）时下发 base_url
        if base_url and base_url != "https://api.anthropic.com":
            env["LLM_BASE_URL"] = base_url
    elif mode == "openai" and base_url in ("https://api.deepseek.com", "https://api.deepseek.com/v1"):
        env["LLM_PROVIDER"] = "deepseek"
    elif mode == "ollama":
        env["LLM_PROVIDER"] = "custom"
        env["LLM_BASE_URL"] = f"{base_url}/v1"
    else:
        env["LLM_PROVIDER"] = "custom"
        env["LLM_BASE_URL"] = base_url
    return env


def _start_cmd(meta: dict, plugin_dir: Path) -> list[str] | None:
    """复刻 manager.start_plugin 的命令拼装：service.command 优先，否则 python server.py"""
    port = dig(meta, "service.port")
    command = dig(meta, "service.command")
    if command:
        return [*command, "--port", str(port)]
    server = plugin_dir / "server.py"
    if not server.exists():
        return None
    return [sys.executable, str(server), "--port", str(port)]


def start_plugin(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    plugin_dir = PLUGIN_ROOT / name
    meta = plugin_manifest(name)
    if not meta:
        return {"ok": False, "error": f"插件不存在或缺少 plugin.yaml：{name}"}
    port = dig(meta, "service.port")
    if not port:
        return {"ok": False, "error": "plugin.yaml 未声明 service.port"}

    if port_in_use(int(port)):
        health = dig(meta, "service.health_check", "/health")
        proto = dig(meta, "service.protocol", "http")
        code, _, _ = http_request("GET", f"{proto}://localhost:{port}{health}", timeout=3)
        if code == 200:
            return {"ok": True, "already": True, "message": f"{name} 已在运行（:{port}）"}
        return {"ok": False, "error": f"端口 {port} 被占用但服务不健康，可能是别的程序占了 {port}"}

    cmd = _start_cmd(meta, plugin_dir)
    if cmd is None:
        return {"ok": False, "error": "既无 service.command 也无 server.py，无法启动"}

    jid = job_new("start", name)
    threading.Thread(target=_start_worker, args=(jid, name, meta, plugin_dir, cmd),
                     daemon=True).start()
    return {"ok": True, "job": jid}


def _start_worker(jid: str, name: str, meta: dict, plugin_dir: Path, cmd: list[str]) -> None:
    port = int(dig(meta, "service.port"))
    ptype = meta.get("type", "")
    env = _build_agent_env() if ptype == "agent" else None
    if ptype == "agent":
        job_log(jid, "[env] 已按 llm/config.yaml 注入 LLM_PROVIDER/MODEL/API_KEY（密钥不显示）")

    log_dir = PLUGIN_ROOT / ".logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"{name}.log"
    # 记下当前日志尾部，之后只 tail 新增部分推给前端
    start_offset = log_path.stat().st_size if log_path.exists() else 0

    job_log(jid, f"[启动] {' '.join(cmd)}")
    job_log(jid, f"[日志] {log_path}")
    try:
        logf = open(log_path, "a", encoding="utf-8", errors="replace")
        create_flags = 0
        if os.name == "nt":
            # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP：脱离本进程，
            # 本设置服务重启/退出也不会带走插件（插件是常驻服务）
            create_flags = 0x00000008 | 0x00000200
        subprocess.Popen(
            cmd, cwd=str(plugin_dir), stdout=logf, stderr=subprocess.STDOUT,
            env={**os.environ, **env} if env else None,
            creationflags=create_flags,
            close_fds=True,
        )
    except Exception as e:
        job_log(jid, f"[失败] 无法启动子进程：{e}")
        job_done(jid, False, str(e))
        return

    health = dig(meta, "service.health_check", "/health")
    proto = dig(meta, "service.protocol", "http")
    timeout = _START_HEALTH_TIMEOUT.get(ptype, 30)
    job_log(jid, f"[等待] 健康检查 {proto}://localhost:{port}{health}（超时 {timeout}s）")

    deadline = time.time() + timeout
    while time.time() < deadline:
        start_offset = _tail_log(jid, log_path, start_offset)
        code, _, _ = http_request("GET", f"{proto}://localhost:{port}{health}", timeout=2)
        if code == 200:
            job_log(jid, f"[成功] {name} 已就绪（:{port}）")
            job_done(jid, True, f"{name} 启动成功")
            return
        time.sleep(0.8)

    job_log(jid, f"[超时] {timeout}s 内未通过健康检查，请看上面的插件日志排查")
    job_done(jid, False, "启动超时")


def _tail_log(jid: str, log_path: Path, offset: int) -> int:
    """把插件自身日志的新增行推进 job，返回新的读取位置"""
    try:
        if not log_path.exists():
            return offset
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            chunk = f.read()
            offset = f.tell()
        for ln in chunk.splitlines():
            if ln.strip():
                job_log(jid, ln)
    except Exception:
        pass
    return offset


def stop_plugin(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    meta = plugin_manifest(name)
    if not meta:
        return {"ok": False, "error": f"插件不存在：{name}"}
    port = dig(meta, "service.port")
    if not port:
        return {"ok": False, "error": "plugin.yaml 未声明 service.port"}
    port = int(port)

    if not port_in_use(port):
        return {"ok": True, "message": f"{name} 未在运行（:{port} 空闲）"}

    pids = pids_on_port(port)
    if not pids:
        return {"ok": False, "error": f"端口 {port} 被占用但查不到 PID，可能需要管理员权限"}

    killed = [p for p in pids if kill_pid(p)]
    time.sleep(0.6)
    still = port_in_use(port)

    warn = ""
    autostart = autostart_map()
    if name in autostart or meta.get("name") in autostart:
        warn = ("（该插件在配置里是自启的，后端下次请求它时若已停止可能报错；"
                "重启后端会再次拉起）")
    if still:
        return {"ok": False, "error": f"已尝试结束 PID {killed}，但端口 {port} 仍被占用"}
    logger.info("已停止插件 %s（PID %s）", name, killed)
    return {"ok": True, "message": f"{name} 已停止（结束 PID {', '.join(map(str, killed))}）{warn}"}


def uninstall_plugin(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    plugin_dir = PLUGIN_ROOT / name
    if not plugin_dir.exists() or plugin_dir.name in NON_PLUGIN_DIRS:
        return {"ok": False, "error": f"插件目录不存在：{name}"}

    meta = plugin_manifest(name)
    port = dig(meta, "service.port")
    if port and port_in_use(int(port)):
        return {"ok": False, "error": f"{name} 正在运行（:{port}），请先停止再卸载"}

    PLUGIN_TRASH.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = PLUGIN_TRASH / f"{name}-{stamp}"
    try:
        # 移动到 .trash（可逆），不硬删；模型文件可能很大，同盘 move 很快
        shutil.move(str(plugin_dir), str(dest))
    except Exception as e:
        return {"ok": False, "error": f"移动到回收站失败：{e}"}
    logger.info("已卸载插件 %s → %s", name, dest)
    return {"ok": True, "message": f"{name} 已移入回收站 custom_plugin/.trash/{dest.name}，"
                                   f"确认无误后可手动删除该目录彻底清理"}

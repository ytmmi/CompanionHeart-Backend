"""插件扫描、状态汇总、自启判定、日志读取（只读侧）。

写侧（安装 / 启停 / 卸载）在 plugins_install 与 plugins_runtime。
"""
from __future__ import annotations

from .http_client import http_request
from .paths import CONFIG_PATHS, PLUGIN_ROOT, PLUGIN_TRASH
from .ports import port_in_use
from .process_utils import pids_on_port
from .yaml_io import dig, read_yaml

# 顶层里不是插件的目录，扫描时跳过
NON_PLUGIN_DIRS = {".logs", ".trash", ".git", "__pycache__"}


def plugin_manifest(name: str) -> dict:
    return read_yaml(PLUGIN_ROOT / name / "plugin.yaml")


def scan_installed_plugins() -> list[dict]:
    """扫描 custom_plugin/ 下所有带 plugin.yaml 的目录"""
    out = []
    if not PLUGIN_ROOT.exists():
        return out
    for d in sorted(PLUGIN_ROOT.iterdir()):
        if not d.is_dir() or d.name in NON_PLUGIN_DIRS:
            continue
        manifest = d / "plugin.yaml"
        if not manifest.exists():
            out.append({"name": d.name, "valid": False,
                        "error": "缺少 plugin.yaml（不是有效插件目录）"})
            continue
        try:
            out.append(_describe_plugin(d, read_yaml(manifest)))
        except Exception as e:
            out.append({"name": d.name, "dir": d.name, "valid": False,
                        "error": f"plugin.yaml 解析失败：{e}"})
    return out


def _describe_plugin(d, meta: dict) -> dict:
    svc = meta.get("service", {}) or {}
    api = meta.get("api", {}) or {}
    log_file = PLUGIN_ROOT / ".logs" / f"{d.name}.log"
    return {
        "name": meta.get("name", d.name),
        "dir": d.name,
        "valid": True,
        "type": meta.get("type", ""),
        "version": meta.get("version", ""),
        "description": meta.get("description", ""),
        "author": meta.get("author", "Unknown"),
        "repository": meta.get("repository", ""),
        "port": svc.get("port"),
        "protocol": svc.get("protocol", "http"),
        "health_check": svc.get("health_check", "/health"),
        "command": svc.get("command"),
        "endpoints": {k: v for k, v in api.items() if v},
        "dependencies": meta.get("dependencies", []) or [],
        "has_server_py": (d / "server.py").exists(),
        "log_size": log_file.stat().st_size if log_file.exists() else 0,
    }


def autostart_map() -> dict[str, str]:
    """复刻 app/main.py:_get_enabled_plugins —— 哪些插件会随后端自启，附原因"""
    reasons: dict[str, str] = {}
    tts = read_yaml(CONFIG_PATHS["tts"])
    if tts.get("mode") == "plugin":
        n = dig(tts, "plugin.name")
        if n:
            reasons[n] = "tts.mode=plugin"
    llm = read_yaml(CONFIG_PATHS["llm"])
    if llm.get("mode") == "plugin":
        n = dig(llm, "plugin.name")
        if n:
            reasons[n] = "llm.mode=plugin"
    asr = read_yaml(CONFIG_PATHS["asr"])
    if asr.get("enabled", False):
        n = dig(asr, f"{asr.get('mode', 'plugin')}.name")
        if n:
            reasons[n] = "asr.enabled=true"
    agent = read_yaml(CONFIG_PATHS["agent"])
    if agent.get("enabled", False):
        n = dig(agent, f"{agent.get('mode', 'pi_sidecar')}.plugin_name")
        if n:
            reasons[n] = "agent.enabled=true"
    return reasons


def get_plugins() -> dict:
    """插件总览：元数据 + 实时状态 + 是否随后端自启"""
    autostart = autostart_map()
    plugins = scan_installed_plugins()
    for p in plugins:
        if not p.get("valid"):
            p["running"] = False
            continue
        port = p.get("port")
        running = bool(port) and port_in_use(int(port))
        p["running"] = running
        p["healthy"] = False
        if running:
            base = f"{p['protocol']}://localhost:{port}"
            code, _, _ = http_request("GET", f"{base}{p['health_check']}", timeout=3)
            p["healthy"] = code == 200
            p["pid"] = pids_on_port(int(port))
        p["autostart"] = p["dir"] in autostart or p["name"] in autostart
        p["autostart_reason"] = autostart.get(p["dir"]) or autostart.get(p["name"], "")
    return {"plugins": plugins, "trash_dir": str(PLUGIN_TRASH)}


def get_plugin_logs(name: str, tail: int = 200) -> dict:
    log_path = PLUGIN_ROOT / ".logs" / f"{name}.log"
    if not log_path.exists():
        return {"ok": True, "name": name, "lines": [], "note": "暂无日志（插件还没被启动过）"}
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "name": name, "lines": lines[-tail:], "total": len(lines)}

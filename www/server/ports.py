"""端口探测、从配置值中解析端口、端口段约定校验。"""
from __future__ import annotations

import socket
from urllib.parse import urlparse

from .paths import BACKEND_PORT, CONFIG_PATHS, PORT_BANDS, SETTINGS_PORT
from .yaml_io import dig, read_yaml


def port_from(value) -> int | None:
    """value 可能是端口整数，也可能是 base_url 字符串"""
    if isinstance(value, int):
        return value
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    try:
        return urlparse(s).port
    except ValueError:
        return None


def port_in_use(port: int, host: str = "127.0.0.1", timeout: float = 0.35) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def check_port(port: int, module: str | None = None) -> dict:
    """端口占用 + 端口段约定 + 与其他模块冲突"""
    issues, level = [], "ok"

    if module and module in PORT_BANDS:
        lo, hi = PORT_BANDS[module]
        if not (lo <= port <= hi):
            issues.append(f"不在 {module.upper()} 约定端口段 {lo}-{hi} 内（仍可用，但不符合项目约定）")
            level = "warn"

    if port == SETTINGS_PORT:
        issues.append(f"{port} 是设置服务自身端口"); level = "error"
    if port == BACKEND_PORT:
        issues.append(f"{BACKEND_PORT} 是后端 FastAPI 端口"); level = "error"

    # 与其他模块当前配置的端口撞车
    others = current_module_ports()
    for other_mod, other_port in others.items():
        if other_mod != module and other_port == port:
            issues.append(f"与 {other_mod.upper()} 模块当前端口冲突"); level = "error"

    in_use = port_in_use(port)
    if in_use and level != "error":
        issues.append("端口已被占用（若正是该插件自己在跑则属正常，插件管理器会复用已有服务）")
        level = "warn" if level == "ok" else level

    return {"port": port, "in_use": in_use, "level": level, "issues": issues}


def current_module_ports() -> dict:
    tts = read_yaml(CONFIG_PATHS["tts"])
    agent = read_yaml(CONFIG_PATHS["agent"])
    asr = read_yaml(CONFIG_PATHS["asr"])
    out = {}
    p = port_from(dig(tts, "plugin.port", ""))
    if p: out["tts"] = p
    p = port_from(dig(agent, "pi_sidecar.base_url", ""))
    if p: out["agent"] = p
    p = port_from(dig(asr, "plugin.base_url", ""))
    if p: out["asr"] = p
    return out

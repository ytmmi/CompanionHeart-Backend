"""服务状态灯与连接测试。

状态灯只探端口；连接测试会真发一次请求，验证密钥、端点、模型名是否可用。
"""
from __future__ import annotations

import json

from .http_client import http_request
from .paths import BACKEND_PORT, BACKEND_URL, CONFIG_PATHS
from .ports import port_from, port_in_use
from .voices import edge_voice_catalog, scan_plugin_characters
from .yaml_io import dig, read_yaml


def get_status() -> dict:
    """顶部状态灯：各服务端口是否在线"""
    tts = read_yaml(CONFIG_PATHS["tts"])
    agent = read_yaml(CONFIG_PATHS["agent"])
    asr = read_yaml(CONFIG_PATHS["asr"])
    llm = read_yaml(CONFIG_PATHS["llm"])

    services = [
        {"id": "backend", "label": "后端 FastAPI", "port": BACKEND_PORT},
        {"id": "tts", "label": "TTS 插件",
         "port": port_from(dig(tts, "plugin.port", 8100)),
         "muted": tts.get("mode") != "plugin"},
        {"id": "agent", "label": "Agent sidecar",
         "port": port_from(dig(agent, "pi_sidecar.base_url", "")),
         "muted": not agent.get("enabled", True)},
        {"id": "asr", "label": "ASR 插件",
         "port": port_from(dig(asr, "plugin.base_url", "")),
         "muted": not asr.get("enabled", False)},
    ]
    if llm.get("mode") == "ollama":
        services.append({"id": "ollama", "label": "Ollama",
                         "port": port_from(dig(llm, "ollama.base_url", ""))})

    for s in services:
        s["online"] = bool(s["port"]) and port_in_use(s["port"])
    return {"services": services}


def test_connection(module: str) -> dict:
    """真实发一次请求验证配置是否可用"""
    if module == "llm":
        return _test_llm()
    if module == "tts":
        return _test_tts()
    if module == "agent":
        return _test_plugin_health(
            dig(read_yaml(CONFIG_PATHS["agent"]), "pi_sidecar.base_url", ""), "Agent sidecar")
    if module == "asr":
        return _test_plugin_health(
            dig(read_yaml(CONFIG_PATHS["asr"]), "plugin.base_url", ""), "ASR 插件")
    return {"ok": False, "message": f"未知模块: {module}"}


def _test_llm() -> dict:
    llm = read_yaml(CONFIG_PATHS["llm"])
    mode = llm.get("mode", "openai")

    if mode == "ollama":
        base = str(dig(llm, "ollama.base_url", "")).rstrip("/")
        code, text, err = http_request("GET", f"{base}/api/tags", timeout=6)
        if err:
            return {"ok": False, "message": f"连不上 Ollama（{base}）：{err}"}
        if code != 200:
            return {"ok": False, "message": f"Ollama 返回 HTTP {code}"}
        try:
            names = [m["name"] for m in json.loads(text).get("models", [])]
        except Exception:
            names = []
        want = dig(llm, "ollama.model", "")
        if want and want not in names:
            return {"ok": False, "level": "warn",
                    "message": f"Ollama 可达，但没有模型 “{want}”。已安装：{', '.join(names) or '（无）'}"}
        return {"ok": True, "message": f"Ollama 正常，模型 “{want}” 已就绪（共 {len(names)} 个模型）"}

    if mode == "claude":
        base = str(dig(llm, "claude.base_url", "")).rstrip("/")
        key = str(dig(llm, "claude.api_key", ""))
        model = str(dig(llm, "claude.model", ""))
        if not base: return {"ok": False, "message": "Claude API endpoint not set"}
        if not key: return {"ok": False, "message": "Claude API key not set (sk-ant-...)"}
        url = base if base.endswith("/v1/messages") else f"{base}/v1/messages"
        code, text, err = http_request(
            "POST", url, timeout=20,
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "Content-Type": "application/json"},
            json_body={"model": model, "max_tokens": 1,
                       "messages": [{"role": "user", "content": "hi"}]},
        )
        if err: return {"ok": False, "message": f"Claude request failed ({url}): {err}"}
        if code == 200: return {"ok": True, "message": f"Claude connected, model {model} OK"}
        if code == 401: return {"ok": False, "message": "Claude HTTP 401 - invalid API key"}
        if code == 404: return {"ok": False, "message": f"Claude HTTP 404 - bad endpoint/model ({url})"}
        snippet = (text or "")[:200].replace("\n", " ")
        return {"ok": False, "message": f"Claude HTTP {code}: {snippet}"}

    # openai 兼容：真发一次 1-token 的 chat，能同时验密钥、端点、模型名
    base = str(dig(llm, "openai.base_url", "")).rstrip("/")
    key = str(dig(llm, "openai.api_key", ""))
    model = str(dig(llm, "openai.model", ""))
    if not base:
        return {"ok": False, "message": "未填写 API 端点"}
    if not key:
        return {"ok": False, "message": "未填写 API 密钥"}

    url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    code, text, err = http_request(
        "POST", url, timeout=20,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json_body={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
    )
    if err:
        return {"ok": False, "message": f"请求失败（{url}）：{err}"}
    if code == 200:
        return {"ok": True, "message": f"连接成功，模型 “{model}” 可用"}
    if code == 401:
        return {"ok": False, "message": "HTTP 401 — API 密钥无效"}
    if code == 404:
        return {"ok": False, "message": f"HTTP 404 — 端点或模型名不对（{url}）"}
    snippet = (text or "")[:200].replace("\n", " ")
    return {"ok": False, "message": f"HTTP {code} — {snippet}"}


def _test_tts() -> dict:
    tts = read_yaml(CONFIG_PATHS["tts"])
    mode = tts.get("mode", "plugin")

    if mode == "plugin":
        port = port_from(dig(tts, "plugin.port", 8100))
        code, text, err = http_request("GET", f"http://localhost:{port}/health", timeout=6)
        if err:
            return {"ok": False,
                    "message": f"TTS 插件未响应（:{port}）—— 插件由后端启动时拉起，"
                               f"请先启动后端。原始错误：{err}"}
        if code != 200:
            return {"ok": False, "message": f"TTS 插件返回 HTTP {code}"}
        chars = [c["voice"] for c in scan_plugin_characters(tts)]
        want = dig(tts, "plugin.config.character_name", "")
        if want and want not in chars:
            return {"ok": False, "level": "warn",
                    "message": f"插件在线，但模型目录里没有角色 “{want}”。可用：{', '.join(chars) or '（无）'}"}
        return {"ok": True, "message": f"TTS 插件正常（:{port}），当前角色 “{want}”"}

    if mode == "edge":
        voice = dig(tts, "edge.voices.zh.voice", "")
        try:
            voices = edge_voice_catalog()
        except Exception as e:
            return {"ok": False, "message": f"拉取微软语音目录失败：{e}"}
        names = {v["voice"] for v in voices}
        if voice not in names:
            return {"ok": False, "message": f"语音 “{voice}” 不在微软目录中（共 {len(names)} 个）"}
        return {"ok": True, "message": f"Edge-TTS 可用，语音 “{voice}” 有效（目录共 {len(names)} 个）"}

    return {"ok": False, "level": "warn",
            "message": "local 模式为已废弃的进程内路径，无法远程探测；建议改用 plugin 模式"}


def _test_plugin_health(base_url: str, label: str) -> dict:
    base = str(base_url or "").rstrip("/")
    if not base:
        return {"ok": False, "message": f"{label} 地址为空"}
    code, text, err = http_request("GET", f"{base}/health", timeout=6)
    if err:
        return {"ok": False, "message": f"{label} 未响应（{base}）：{err}"}
    if code != 200:
        return {"ok": False, "message": f"{label} 返回 HTTP {code}"}
    return {"ok": True, "message": f"{label} 正常（{base}）"}


def restart_agent() -> dict:
    code, text, err = http_request("POST", f"{BACKEND_URL}/api/agent/restart", timeout=40)
    if err:
        return {"ok": False, "message": f"后端未响应（{BACKEND_URL}）：{err}"}
    if code != 200:
        return {"ok": False, "message": f"重启失败：HTTP {code} {(text or '')[:200]}"}
    return {"ok": True, "message": "Agent sidecar 已重启，新的 LLM 配置已生效"}

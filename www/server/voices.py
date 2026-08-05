"""角色扫描、微软语音目录、LLM 模型列表。

角色列表直接读磁盘而不是调插件的 /voices，这样插件没启动时设置界面也能用。
"""
from __future__ import annotations

import asyncio
import json

from .http_client import http_request
from .paths import CONFIG_PATHS, PLUGIN_ROOT
from .yaml_io import dig, read_yaml


def scan_plugin_characters(tts_config: dict) -> list[dict]:
    """扫描 TTS 插件的角色目录"""
    plugin_name = dig(tts_config, "plugin.name", "TTS_genie_tts")
    base = PLUGIN_ROOT / str(plugin_name) / "model" / "v2ProPlus"
    # 已知角色的语言/描述在插件 server.py 里硬编码，这里用 local 配置补齐展示信息
    known = dig(tts_config, "local.characters", {}) or {}
    out = []
    if not base.exists():
        return out
    for char_dir in sorted(base.iterdir()):
        if not char_dir.is_dir() or not (char_dir / "tts_models").exists():
            continue
        emotions = []
        pwj = char_dir / "prompt_wav.json"
        if pwj.exists():
            try:
                emotions = list(json.loads(pwj.read_text(encoding="utf-8")).keys())
            except Exception:
                pass
        meta = known.get(char_dir.name, {}) if isinstance(known, dict) else {}
        out.append({
            "id": f"plugin.{char_dir.name}",
            "voice": char_dir.name,
            "language": meta.get("language", ""),
            "description": meta.get("description", ""),
            "engine": "GenieTTS",
            "category": "plugin",
            "emotions": emotions,
        })
    return out


def get_tts_voices() -> list[dict]:
    tts_config = read_yaml(CONFIG_PATHS["tts"])
    voices = []

    for lang_key, info in (dig(tts_config, "edge.voices", {}) or {}).items():
        voices.append({
            "id": f"edge.{lang_key}",
            "voice": info.get("voice", ""),
            "language": info.get("language", lang_key),
            "description": info.get("description", ""),
            "engine": "EdgeTTS", "category": "edge",
        })

    for name, info in (dig(tts_config, "local.characters", {}) or {}).items():
        voices.append({
            "id": f"local.{name}",
            "voice": name,
            "language": info.get("language", ""),
            "description": info.get("description", ""),
            "engine": "GenieTTS", "category": "local",
        })

    voices += scan_plugin_characters(tts_config)
    return voices


_EDGE_CACHE: list[dict] = []


def edge_voice_catalog() -> list[dict]:
    """微软完整语音目录（300+），进程内缓存一次"""
    global _EDGE_CACHE
    if _EDGE_CACHE:
        return _EDGE_CACHE
    import edge_tts
    raw = asyncio.run(edge_tts.list_voices())
    out = []
    for v in raw:
        locale = v.get("Locale", "")
        out.append({
            "voice": v.get("ShortName", ""),
            "locale": locale,
            "lang": locale.split("-")[0] if locale else "",
            "gender": v.get("Gender", ""),
            "friendly": v.get("FriendlyName", ""),
            "personalities": (v.get("VoiceTag") or {}).get("VoicePersonalities", []),
            "categories": (v.get("VoiceTag") or {}).get("ContentCategories", []),
        })
    out.sort(key=lambda x: (x["locale"], x["voice"]))
    _EDGE_CACHE = out
    return out


def get_llm_models(mode: str) -> dict:
    """拉模型列表：ollama 走 /api/tags，openai 兼容走 /v1/models，Claude 走预置列表"""
    llm = read_yaml(CONFIG_PATHS["llm"])

    if mode == "ollama":
        base = str(dig(llm, "ollama.base_url", "")).rstrip("/")
        code, text, err = http_request("GET", f"{base}/api/tags", timeout=8)
        if err or code != 200:
            return {"ok": False, "models": [],
                    "error": err or f"HTTP {code}", "hint": "Ollama 未运行时无法列出模型，可手动填写"}
        try:
            models = [m["name"] for m in json.loads(text).get("models", [])]
        except Exception as e:
            return {"ok": False, "models": [], "error": str(e)}
        return {"ok": True, "models": sorted(models)}

    if mode == "claude":
        # Anthropic 没有公开模型列表 API，返回预设的当前模型列表
        return {"ok": True, "models": [
            "claude-opus-4-20250514",
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-haiku-20240307",
        ], "hint": "Anthropic 无模型列表 API，此为预设列表"}

    base = str(dig(llm, "openai.base_url", "")).rstrip("/")
    key = str(dig(llm, "openai.api_key", ""))
    if not base:
        return {"ok": False, "models": [], "error": "未填写 API 端点"}
    url = base if base.endswith("/models") else f"{base}/models"
    code, text, err = http_request("GET", url, timeout=10,
                                   headers={"Authorization": f"Bearer {key}"} if key else None)
    if err or code != 200:
        return {"ok": False, "models": [], "error": err or f"HTTP {code}",
                "hint": "部分端点不提供 /models，可手动填写模型名"}
    try:
        data = json.loads(text)
        models = sorted({m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m})
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)}
    return {"ok": True, "models": models}

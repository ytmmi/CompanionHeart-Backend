"""TTS 试听合成。

优先走后端 :18000（和桌宠实际发声路径一致）；后端没开就直连插件 :8100，
edge 模式还能退回到本进程内用 edge_tts 直接合成 —— 三级回退，尽量让试听可用。
"""
from __future__ import annotations

import asyncio

from .paths import BACKEND_URL, CONFIG_PATHS
from .ports import port_from
from .voices import scan_plugin_characters
from .yaml_io import dig, read_yaml

SAMPLE_TEXTS = {
    "zh": "你好呀，我是你的桌面伙伴，今天过得怎么样？",
    "jp": "こんにちは、今日はどんな一日でしたか？",
    "en": "Hello there, I'm your desktop companion. How was your day?",
}


def tts_preview(body: dict) -> tuple[bytes | None, str, str | None]:
    """合成一句试听音频，返回 (音频字节, content-type, 错误信息)"""
    tts = read_yaml(CONFIG_PATHS["tts"])
    mode = body.get("mode") or tts.get("mode", "plugin")
    text = (body.get("text") or "").strip()

    payload: dict = {}
    if mode == "plugin":
        char = body.get("character_name") or dig(tts, "plugin.config.character_name", "")
        payload["character_name"] = char
        if body.get("emotion"):
            payload["emotion"] = body["emotion"]
        if not text:
            lang = ""
            for c in scan_plugin_characters(tts):
                if c["voice"] == char:
                    lang = c.get("language", "")
                    break
            text = SAMPLE_TEXTS.get(lang, SAMPLE_TEXTS["zh"])
    elif mode == "edge":
        payload["voice"] = body.get("voice") or dig(tts, "edge.voices.zh.voice", "")
        for k in ("rate", "volume", "pitch"):
            v = body.get(k) if body.get(k) is not None else dig(tts, f"edge.default_params.{k}")
            if v:
                payload[k] = v
        if not text:
            lang = str(payload.get("voice", ""))[:2]
            text = SAMPLE_TEXTS.get({"ja": "jp"}.get(lang, lang), SAMPLE_TEXTS["zh"])
    else:
        return None, "", "local 模式不支持试听，请改用 plugin 或 edge"

    payload["text"] = text

    import requests

    # 1) 后端主链路
    try:
        r = requests.post(f"{BACKEND_URL}/api/voice/tts", json=payload, timeout=90)
        if r.status_code == 200 and r.content:
            return r.content, r.headers.get("Content-Type", "audio/wav"), None
        backend_err = f"后端返回 HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        backend_err = f"后端未响应（{BACKEND_URL}）: {type(e).__name__}"

    # 2) 后端不可用时直连插件
    if mode == "plugin":
        return _preview_via_plugin(tts, payload, backend_err)

    # 3) edge 模式后端不可用时本地合成
    if mode == "edge":
        return _preview_via_edge(text, payload, backend_err)

    return None, "", backend_err


def _preview_via_plugin(tts: dict, payload: dict, backend_err: str):
    import requests
    port = port_from(dig(tts, "plugin.port", 8100))
    try:
        r = requests.post(f"http://localhost:{port}/synthesize", json=payload, timeout=90)
        if r.status_code == 200 and r.content:
            return r.content, r.headers.get("Content-Type", "audio/wav"), None
        return None, "", f"{backend_err}；直连插件也失败：HTTP {r.status_code}"
    except Exception as e:
        return None, "", (f"{backend_err}；直连插件 :{port} 也失败：{type(e).__name__}。"
                          f"TTS 插件由后端启动时拉起，请先启动后端。")


def _preview_via_edge(text: str, payload: dict, backend_err: str):
    try:
        import edge_tts

        async def _synth() -> bytes:
            comm = edge_tts.Communicate(
                text, payload.get("voice") or "zh-CN-XiaoxiaoNeural",
                rate=payload.get("rate", "+0%"),
                volume=payload.get("volume", "+0%"),
                pitch=payload.get("pitch", "+0Hz"),
            )
            buf = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf += chunk["data"]
            return bytes(buf)

        audio = asyncio.run(_synth())
        if audio:
            return audio, "audio/mpeg", None
        return None, "", f"{backend_err}；本地 Edge-TTS 合成返回空音频"
    except Exception as e:
        return None, "", f"{backend_err}；本地 Edge-TTS 合成失败：{e}"

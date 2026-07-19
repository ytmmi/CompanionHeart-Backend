"""Edge-TTS 语音合成引擎

基于微软 Edge 浏览器的在线 TTS 服务，免费使用，无需 API Key。
支持多种语言和语音风格。

依赖:
    pip install edge-tts

文档:
    https://github.com/rany2/edge-tts
    https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts
"""

from pathlib import Path
from typing import AsyncIterator, Optional

from ..base import TTSBase


# ── 默认语音映射 ──
# 完整列表见: https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts
DEFAULT_VOICES: dict[str, dict] = {
    "jp": {
        "voice": "ja-JP-NanamiNeural",
        "language": "jp",
        "description": "日语女声 (Nanami)",
    },
    "zh": {
        "voice": "zh-CN-XiaoxiaoNeural",
        "language": "zh",
        "description": "中文女声 (晓晓)",
    },
    "en": {
        "voice": "en-US-AriaNeural",
        "language": "en",
        "description": "英文女声 (Aria)",
    },
}


class EdgeTTS(TTSBase):
    """Edge-TTS 语音合成引擎"""

    media_type = "audio/mpeg"

    def __init__(
        self,
        voice: str = "zh-CN-XiaoxiaoNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        output_dir: Optional[Path] = None,
    ):
        """
        初始化 Edge-TTS 引擎。

        Args:
            voice: 默认语音名称，如 "zh-CN-XiaoxiaoNeural"。
            rate:   语速，范围 "-50%" 到 "+50%"，默认 "+0%"。
            volume: 音量，范围 "-50%" 到 "+50%"，默认 "+0%"。
            pitch:  音调，范围 "-50Hz" 到 "+50Hz"，默认 "+0Hz"。
            output_dir: 音频输出目录，不提供则不保存文件。
        """
        self._voice = voice
        self._rate = rate
        self._volume = volume
        self._pitch = pitch
        self._output_dir = Path(output_dir) if output_dir else None

    # ── 属性 ──

    @property
    def voice(self) -> str:
        return self._voice

    @voice.setter
    def voice(self, value: str):
        self._voice = value

    @property
    def rate(self) -> str:
        return self._rate

    @rate.setter
    def rate(self, value: str):
        self._rate = value

    @property
    def volume(self) -> str:
        return self._volume

    @volume.setter
    def volume(self, value: str):
        self._volume = value

    @property
    def pitch(self) -> str:
        return self._pitch

    @pitch.setter
    def pitch(self, value: str):
        self._pitch = value

    # ── 核心方法 ──

    async def synthesize(
        self,
        text: str,
        output_path: Optional[Path] = None,
        *,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None,
        **kwargs,
    ) -> bytes:
        """
        将文本合成为 MP3 音频。

        Args:
            text: 要合成的文本。
            output_path: 保存路径，不提供则保存到 output_dir 下。
            voice:  临时覆盖默认语音。
            rate:   临时覆盖默认语速。
            volume: 临时覆盖默认音量。
            pitch:  临时覆盖默认音调。

        Returns:
            MP3 音频数据的字节流。
        """
        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            voice or self._voice,
            rate=rate or self._rate,
            volume=volume or self._volume,
            pitch=pitch or self._pitch,
        )

        # 确定输出路径
        save_path = output_path
        if save_path is None and self._output_dir is not None:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            safe_name = _sanitize_filename(text[:30])
            save_path = self._output_dir / f"{safe_name}.mp3"

        if save_path:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            await communicate.save(str(save_path))
            return save_path.read_bytes()
        else:
            chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

    async def stream(
        self,
        text: str,
        *,
        voice: Optional[str] = None,
        rate: Optional[str] = None,
        volume: Optional[str] = None,
        pitch: Optional[str] = None,
        **kwargs,
    ) -> AsyncIterator[bytes]:
        """
        流式合成语音，逐 chunk 产生 MP3 音频数据。

        Args:
            text: 要合成的文本。
            voice:  语音名称。
            rate:   语速。
            volume: 音量。
            pitch:  音调。

        Yields:
            MP3 音频数据块。
        """
        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            voice or self._voice,
            rate=rate or self._rate,
            volume=volume or self._volume,
            pitch=pitch or self._pitch,
        )

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    async def get_voices(self) -> list[dict]:
        """
        获取预配置的常用语音列表。

        注意: edge-tts 库支持通过 `edge_tts.list_voices()` 获取完整列表。
        此处返回项目配置中预设的常用语音。
        """
        return list(DEFAULT_VOICES.values())

    async def list_all_voices(self) -> list[dict]:
        """
        从 Edge-TTS 获取所有可用语音的完整列表。

        返回完整语音列表，每项包含 VoiceFriendlyName、Gender、Locale 等字段。
        """
        import edge_tts

        raw = await edge_tts.list_voices()
        return [
            {
                "name": v.get("ShortName"),
                "friendly_name": v.get("FriendlyName"),
                "locale": v.get("Locale"),
                "gender": v.get("Gender"),
                "language": v.get("Locale", "").split("-")[0] if v.get("Locale") else "",
                "description": f"{v.get('Locale', '')} - {v.get('FriendlyName', '')} ({v.get('Gender', '')})",
            }
            for v in raw
        ]

    async def validate_config(self) -> bool:
        """验证 Edge-TTS 配置：尝试列出语音以确认网络可达"""
        try:
            import edge_tts
            await edge_tts.list_voices()
            return True
        except Exception:
            return False


# ── 辅助函数 ──

def _sanitize_filename(text: str, max_len: int = 50) -> str:
    """将文本转为安全的文件名片段"""
    import re

    safe = re.sub(r"[^\w\-_ ]", "", text, flags=re.UNICODE)
    safe = safe.strip().replace(" ", "_")
    if len(safe) > max_len:
        safe = safe[:max_len]
    if not safe:
        safe = "tts_output"
    return safe

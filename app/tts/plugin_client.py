"""TTS插件HTTP客户端

通过HTTP协议与TTS插件通信。
"""

import logging
from pathlib import Path
from typing import AsyncIterator, Optional

from ..plugins.client import PluginHTTPClient
from .base import TTSBase

logger = logging.getLogger(__name__)


class TTSPluginClient(TTSBase):
    """TTS插件HTTP客户端"""

    supports_sentence_stream = True

    def __init__(
        self,
        base_url: str,
        timeout: int = 120,
        plugin_config: Optional[dict] = None,
    ):
        """
        初始化TTS插件客户端。

        Args:
            base_url: 插件服务地址（如 http://localhost:8100）
            timeout: 请求超时时间（秒）
            plugin_config: 插件配置参数（传递给插件的默认参数）
        """
        self.client = PluginHTTPClient(base_url, timeout)
        self.plugin_config = plugin_config or {}

    async def synthesize(
        self,
        text: str,
        output_path: Optional[Path] = None,
        **kwargs,
    ) -> bytes:
        """
        将文本合成为音频（非流式）。

        Args:
            text: 要合成的文本。
            output_path: 保存路径（可选，不影响HTTP请求）。
            **kwargs: 插件特定参数（如 character_name, split_sentence）。

        Returns:
            音频数据的字节流。
        """
        # 合并默认配置和调用参数
        request_data = {"text": text, **self.plugin_config, **kwargs}

        try:
            resp = await self.client.post("/synthesize", json=request_data)
            resp.raise_for_status()
            audio_data = resp.content

            # 如果提供了输出路径，保存到本地
            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(audio_data)

            return audio_data

        except Exception as e:
            logger.error("TTS插件合成失败: %s", e)
            raise RuntimeError(f"TTS插件合成失败: {e}")

    async def stream(
        self,
        text: str,
        **kwargs,
    ) -> AsyncIterator[bytes]:
        """
        流式合成语音，逐 chunk 产生音频数据。

        Args:
            text: 要合成的文本。
            **kwargs: 插件特定参数。

        Yields:
            音频数据块。
        """
        # 合并默认配置和调用参数
        request_data = {"text": text, **self.plugin_config, **kwargs}

        try:
            async for chunk in self.client.stream_post("/stream", json=request_data):
                yield chunk
        except Exception as e:
            logger.error("TTS插件流式合成失败: %s", e)
            raise RuntimeError(f"TTS插件流式合成失败: {e}")

    async def stream_sentences(
        self,
        text: str,
        **kwargs,
    ) -> AsyncIterator[bytes]:
        """
        句子级同步流式合成：透传插件 /stream_sentences 的 NDJSON 字节流。

        每行: {"text": 句子, "audio": base64(PCM), "duration_ms": 时长}

        Yields:
            NDJSON 数据块。
        """
        request_data = {"text": text, **self.plugin_config, **kwargs}

        try:
            async for chunk in self.client.stream_post("/stream_sentences", json=request_data):
                yield chunk
        except Exception as e:
            logger.error("TTS插件句子级流式合成失败: %s", e)
            raise RuntimeError(f"TTS插件句子级流式合成失败: {e}")

    async def get_voices(self) -> list[dict]:
        """
        获取插件支持的语音/角色列表。

        Returns:
            字典列表，每项包含 voice / language / description 等字段。
        """
        try:
            resp = await self.client.get("/voices")
            resp.raise_for_status()
            data = resp.json()
            return data.get("voices", [])
        except Exception as e:
            logger.error("获取TTS插件语音列表失败: %s", e)
            return []

    async def validate_config(self) -> bool:
        """
        验证插件配置：检查插件服务是否可达。

        Returns:
            True 表示配置有效，False 表示无效。
        """
        return await self.client.health_check()

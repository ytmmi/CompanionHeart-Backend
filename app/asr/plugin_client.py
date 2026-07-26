"""ASR插件HTTP客户端

通过HTTP协议与ASR插件（独立子进程，本地重型模型）通信。
"""

import logging

from ..plugins.client import PluginHTTPClient
from .base import ASRBase, TranscriptionResult

logger = logging.getLogger(__name__)


class ASRPluginClient(ASRBase):
    """ASR插件HTTP客户端（SenseVoice 提供情感/事件信号）"""

    supports_emotion = True

    def __init__(
        self,
        base_url: str,
        timeout: int = 60,
        plugin_config: dict | None = None,
    ):
        """
        初始化ASR插件客户端。

        Args:
            base_url: 插件服务地址（如 http://localhost:8400）
            timeout: 请求超时时间（秒）
            plugin_config: 插件默认参数（随请求一并发送）
        """
        self.client = PluginHTTPClient(base_url, timeout)
        self.plugin_config = plugin_config or {}

    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "auto",
        **kwargs,
    ) -> str:
        """
        将音频转写为文本（纯文本，丢弃情感信号）。

        需要情感信号时用 transcribe_detailed()。
        """
        result = await self.transcribe_detailed(audio_data, language=language, **kwargs)
        return result.text

    async def transcribe_detailed(
        self,
        audio_data: bytes,
        language: str = "auto",
        **kwargs,
    ) -> TranscriptionResult:
        """
        转写并返回情感信号（POST /transcribe，multipart 上传）。

        Args:
            audio_data: 音频字节数据。
            language: 语言代码（auto/zh/en/yue/ja/ko）。
            **kwargs: 插件特定参数（如 use_itn、audio_filename）。

        Returns:
            TranscriptionResult（text + emotion + events + detected_language）
        """
        params = {"language": language, **self.plugin_config, **kwargs}
        # 文件名只用于让插件按扩展名选择解码方式，不作为表单字段下发
        filename = params.pop("audio_filename", None) or "audio.wav"
        # bool 需转成字符串形式随 form 提交
        data = {k: str(v) for k, v in params.items() if v is not None}
        files = {"audio": (filename, audio_data, "application/octet-stream")}

        try:
            resp = await self.client.post("/transcribe", files=files, data=data)
            resp.raise_for_status()
            body = resp.json()
            return TranscriptionResult(
                text=body.get("text", ""),
                emotion=body.get("emotion"),
                events=body.get("events") or [],
                detected_language=body.get("detected_language"),
            )
        except Exception as e:
            logger.error("ASR插件转写失败: %s", e)
            raise RuntimeError(f"ASR插件转写失败: {e}")

    async def get_languages(self) -> list[str]:
        """获取插件支持的语言列表"""
        try:
            resp = await self.client.get("/languages")
            resp.raise_for_status()
            return resp.json().get("languages", [])
        except Exception as e:
            logger.warning("获取ASR插件语言列表失败: %s", e)
            return []

    async def validate_config(self) -> bool:
        """验证插件配置：检查插件服务是否可达"""
        return await self.client.health_check()

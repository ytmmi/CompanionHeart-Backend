"""TTS 语音合成基类"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator, Optional


class TTSBase(ABC):
    """所有 TTS 引擎的抽象基类"""

    # 是否支持真流式合成（逐 chunk 增量产出）。
    # 若引擎的 stream() 只是先合成完整音频再一次性 yield，应覆盖为 False，
    # 调用方（API 层 / 前端）据此回退到非流式路径。
    supports_streaming: bool = True

    # 是否支持句子级同步流式（stream_sentences，文本与音频成对产出）。
    # 支持的引擎覆盖为 True 并实现 stream_sentences()。
    supports_sentence_stream: bool = False

    # 输出音频的 MIME 类型（EdgeTTS 覆盖为 audio/mpeg）
    media_type: str = "audio/wav"

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        output_path: Optional[Path] = None,
        **kwargs,
    ) -> bytes:
        """
        将文本合成为音频。

        Args:
            text: 要合成的文本。
            output_path: 如果提供，音频将保存到此路径。
            **kwargs: 引擎特定的参数。

        Returns:
            音频数据的字节流（WAV/MP3 格式）。
        """
        ...

    @abstractmethod
    async def stream(
        self,
        text: str,
        **kwargs,
    ) -> AsyncIterator[bytes]:
        """
        流式合成语音，逐 chunk 产生音频数据。

        Args:
            text: 要合成的文本。
            **kwargs: 引擎特定的参数。

        Yields:
            音频数据块。
        """
        ...
        # 若引擎不支持流式，yield self.synthesize(text, **kwargs) 即可
        yield b""

    async def stream_sentences(
        self,
        text: str,
        **kwargs,
    ) -> AsyncIterator[bytes]:
        """
        句子级同步流式合成（NDJSON 字节流）。

        每行一个 JSON 对象: {"text": 句子, "audio": base64(PCM), "duration_ms": 时长}。
        仅 supports_sentence_stream=True 的引擎实现；默认抛 NotImplementedError。

        Yields:
            NDJSON 行的字节数据。
        """
        raise NotImplementedError("该引擎不支持句子级同步流式合成")
        yield b""  # pragma: no cover

    @abstractmethod
    async def get_voices(self) -> list[dict]:
        """
        获取当前引擎支持的语音/角色列表。

        Returns:
            字典列表，每项包含 voice / language / description 等字段。
        """
        ...

    @abstractmethod
    async def validate_config(self) -> bool:
        """
        验证当前配置是否有效（如 API Key、文件路径等）。

        Returns:
            True 表示配置有效，False 表示无效。
        """
        ...

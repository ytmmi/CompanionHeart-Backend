"""TTS 语音合成基类"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncIterator, Optional


class TTSBase(ABC):
    """所有 TTS 引擎的抽象基类"""

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

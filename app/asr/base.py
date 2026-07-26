"""ASR 语音识别基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

# 归一化情感值（SenseVoice 情感标签映射结果）
EMOTIONS = ("happy", "sad", "angry", "neutral", "fearful", "disgusted", "surprised")


@dataclass
class TranscriptionResult:
    """转写结果 — 文本与情感信号分离

    情感/事件作为独立字段而非混入文本，供 Live2D 表情、TTS 情绪参数使用；
    text 保持纯净，可直接作为 agent 的用户输入。
    """
    text: str
    # 情感（EMOTIONS 之一）；引擎不支持或未检出时为 None
    emotion: Optional[str] = None
    # 声学事件（speech/laughter/cry/applause/bgm/sneeze/breath/cough）
    events: list[str] = field(default_factory=list)
    # 引擎检测到的语言（请求为 auto 时尤其有用）
    detected_language: Optional[str] = None


class ASRBase(ABC):
    """所有 ASR 引擎的抽象基类"""

    # 支持的音频格式（供 API 层校验/文档展示）
    supported_formats: tuple[str, ...] = ("wav", "mp3", "pcm")

    # 是否提供情感/事件信号（供上层决定是否驱动表情）
    supports_emotion: bool = False

    # ── 核心接口 ──

    @abstractmethod
    async def transcribe(
        self,
        audio_data: bytes,
        language: str = "auto",
        **kwargs,
    ) -> str:
        """
        将音频转写为文本。

        Args:
            audio_data: 音频字节数据（WAV / MP3 等，由引擎自行解码）。
            language: 语言代码，"auto" 表示自动检测；
                      SenseVoice 支持 auto/zh/en/yue/ja/ko/nospeech。
            **kwargs: 引擎特定参数（如 use_itn 逆文本标准化）。

        Returns:
            转写文本（纯文本，不含情感标签/emoji）。
        """
        ...

    async def transcribe_detailed(
        self,
        audio_data: bytes,
        language: str = "auto",
        **kwargs,
    ) -> TranscriptionResult:
        """
        转写并返回情感信号（文本 + emotion/events/detected_language）。

        默认退化为只有文本的结果；supports_emotion=True 的引擎覆写此方法。
        """
        text = await self.transcribe(audio_data, language=language, **kwargs)
        return TranscriptionResult(text=text)

    # ── 配置与状态 ──

    @abstractmethod
    async def validate_config(self) -> bool:
        """
        验证当前配置是否有效（如模型文件、服务可达性）。

        Returns:
            True 表示配置有效，False 表示无效。
        """
        ...

    async def get_languages(self) -> list[str]:
        """
        获取引擎支持的语言列表。

        默认返回空列表，子类可覆写。
        """
        return []

    # ── 生命周期 ──

    async def close(self):
        """释放引擎占用的资源，子类可覆写"""
        pass

"""TTS 语音合成模块

支持的引擎:
    - edge:     微软 Edge-TTS（在线，免费，无需 API Key）
    - local:    Genie-TTS（本地 ONNX 推理，需下载模型）
"""

from .base import TTSBase
from .edge_tts import EdgeTTS
from .genie_tts import GenieTTS
from .factories import TTSFactory

__all__ = [
    "TTSBase",
    "EdgeTTS",
    "GenieTTS",
    "TTSFactory",
]

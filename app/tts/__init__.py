"""TTS 语音合成模块

支持的引擎:
    - edge:     微软 Edge-TTS（在线，免费，无需 API Key）
    - local:    Genie-TTS（本地 ONNX 推理，需下载模型）
    - plugin:   插件模式（本地部署模型通过HTTP通信）
"""

from .base import TTSBase
from .edge_tts import EdgeTTS
from .genie_tts import GenieTTS
from .plugin_client import TTSPluginClient
from .factories import TTSFactory

__all__ = [
    "TTSBase",
    "EdgeTTS",
    "GenieTTS",
    "TTSPluginClient",
    "TTSFactory",
]

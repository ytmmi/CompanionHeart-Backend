"""ASR 语音识别模块

本地重型模型（FunASR + SenseVoiceSmall）走独立子进程插件
（custom_plugin/ASR_funasr，端口 8400），与 TTS 的插件模式一致。
"""

from .base import EMOTIONS, ASRBase, TranscriptionResult
from .factories import ASRFactory
from .plugin_client import ASRPluginClient

__all__ = ["ASRBase", "ASRFactory", "ASRPluginClient", "TranscriptionResult", "EMOTIONS"]

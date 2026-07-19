"""TTS 引擎工厂"""

from pathlib import Path
from typing import Optional

from .base import TTSBase
from .edge_tts import EdgeTTS
from .genie_tts import GenieTTS
from .plugin_client import TTSPluginClient


class TTSFactory:
    """TTS 引擎工厂，根据配置创建对应的 TTS 实例"""

    @staticmethod
    def create(
        provider: str,
        *,
        voice: Optional[str] = None,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        output_dir: Optional[Path] = None,
        **kwargs,
    ) -> TTSBase:
        """
        创建 TTS 引擎实例。

        Args:
            provider: 引擎类型，支持 "edge" / "local"。
            voice: 语音名称（EdgeTTS）或角色名（GenieTTS）。
            rate: 语速（仅 EdgeTTS）。
            volume: 音量（仅 EdgeTTS）。
            pitch: 音调（仅 EdgeTTS）。
            output_dir: 音频输出目录。
            **kwargs: 引擎特定的额外参数。

        Returns:
            TTSBase 子类实例。

        Raises:
            ValueError: 不支持的 provider。
        """
        provider = provider.lower().strip()

        if provider == "edge":
            return EdgeTTS(
                voice=voice or "zh-CN-XiaoxiaoNeural",
                rate=rate,
                volume=volume,
                pitch=pitch,
                output_dir=output_dir,
                **kwargs,
            )

        if provider == "local":
            return GenieTTS(
                output_dir=output_dir,
                **kwargs,
            )

        raise ValueError(f"不支持的 TTS 引擎类型: {provider}。当前支持: edge, local")

    @staticmethod
    def create_from_config(config: dict) -> TTSBase:
        """
        从配置字典创建 TTS 引擎实例。

        配置格式（对应 configs/tts/config.yaml）:
            {
                "mode": "edge" / "local" / "plugin",
                "edge": { ... },       # Edge-TTS 配置
                "local": { ... },      # Genie-TTS 配置
                "plugin": { ... },     # 插件配置
            }

        Args:
            config: TTS 配置字典。

        Returns:
            TTSBase 子类实例。
        """
        mode = config.get("mode", "edge")
        provider_config = config.get(mode, {})

        if mode == "edge":
            return TTSFactory._create_edge_from_config(provider_config)
        if mode == "local":
            return TTSFactory._create_local_from_config(provider_config)
        if mode == "plugin":
            return TTSFactory._create_plugin_from_config(provider_config)

        raise ValueError(f"不支持的 TTS 模式: {mode}。当前支持: edge, local, plugin")

    @staticmethod
    def _create_edge_from_config(config: dict) -> EdgeTTS:
        """从配置创建 EdgeTTS 实例"""
        voices = config.get("voices", {})
        voice = None
        if "zh" in voices:
            voice = voices["zh"].get("voice")
        elif voices:
            first_key = next(iter(voices))
            voice = voices[first_key].get("voice")

        default_params = config.get("default_params", {})
        output_dir = config.get("output_dir")

        return EdgeTTS(
            voice=voice or "zh-CN-XiaoxiaoNeural",
            rate=default_params.get("rate", "+0%"),
            volume=default_params.get("volume", "+0%"),
            pitch=default_params.get("pitch", "+0Hz"),
            output_dir=Path(output_dir) if output_dir else None,
        )

    @staticmethod
    def _create_local_from_config(config: dict) -> GenieTTS:
        """从配置创建 GenieTTS 实例"""
        data_dir = config.get("data_dir", "")
        model_base_dir = config.get("model_base_dir", "")
        output_dir = config.get("output_dir")
        characters = config.get("characters", {})
        default_params = config.get("default_params", {})

        return GenieTTS(
            data_dir=data_dir,
            model_base_dir=model_base_dir,
            output_dir=Path(output_dir) if output_dir else None,
            characters=characters,
            default_params=default_params,
        )

    @staticmethod
    def _create_plugin_from_config(config: dict) -> TTSPluginClient:
        """从配置创建插件客户端实例"""
        port = config.get("port", 8100)
        base_url = f"http://localhost:{port}"
        timeout = config.get("timeout", 120)
        plugin_config = config.get("config", {})

        return TTSPluginClient(
            base_url=base_url,
            timeout=timeout,
            plugin_config=plugin_config,
        )

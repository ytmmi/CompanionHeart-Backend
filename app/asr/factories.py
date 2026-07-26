"""ASR 引擎工厂"""

from typing import Optional

from .base import ASRBase
from .plugin_client import ASRPluginClient


class ASRFactory:
    """ASR 引擎工厂，根据配置创建对应的 ASR 实例"""

    @staticmethod
    def create(
        provider: str,
        *,
        base_url: Optional[str] = None,
        timeout: int = 60,
        plugin_config: Optional[dict] = None,
        **kwargs,
    ) -> ASRBase:
        """
        创建 ASR 引擎实例。

        Args:
            provider: 引擎类型，支持 "plugin"（本地模型走独立子进程）。
            base_url: 插件服务地址。
            timeout: 请求超时（秒）。
            plugin_config: 插件默认参数。

        Returns:
            ASRBase 子类实例。

        Raises:
            ValueError: provider 不支持时。
        """
        if provider == "plugin":
            return ASRPluginClient(
                base_url=base_url or "http://localhost:8400",
                timeout=timeout,
                plugin_config=plugin_config,
            )
        raise ValueError(f"不支持的 ASR 引擎: {provider}")

    @staticmethod
    def create_from_config(config: dict) -> ASRBase:
        """
        从配置字典创建 ASR 引擎（app/configs/asr/config.yaml 的结构）。

        Args:
            config: {"mode": "plugin", "plugin": {"base_url": ..., "timeout": ...}}
        """
        mode = config.get("mode", "plugin")
        engine_config = dict(config.get(mode, {}))
        base_url = engine_config.pop("base_url", None)
        timeout = engine_config.pop("timeout", 60)
        # 其余字段作为插件默认参数（name 是插件标识，不下发）
        engine_config.pop("name", None)
        return ASRFactory.create(
            mode,
            base_url=base_url,
            timeout=timeout,
            plugin_config=engine_config or None,
        )

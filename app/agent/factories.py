"""Agent 引擎工厂"""

from typing import Optional

from .base import AgentBase
from .pi_sidecar import PiSidecarAgentEngine


class AgentFactory:
    """Agent 引擎工厂，根据配置创建对应的 Agent 实例"""

    @staticmethod
    def create(
        mode: str,
        *,
        base_url: Optional[str] = None,
        timeout: int = 120,
        system_prompt: str = "",
        default_params: Optional[dict] = None,
        **kwargs,
    ) -> AgentBase:
        """
        创建 Agent 引擎实例。

        Args:
            mode: 引擎类型，支持 "pi_sidecar"（"basic" 预留）。
            base_url: sidecar 服务地址。
            timeout: 请求超时（秒）。
            system_prompt: 默认系统提示词（人格设定）。
            default_params: 默认采样参数 {temperature, max_tokens}。

        Returns:
            AgentBase 子类实例。

        Raises:
            ValueError: mode 不支持时。
            NotImplementedError: mode 已预留但未实现时。
        """
        if mode == "pi_sidecar":
            return PiSidecarAgentEngine(
                base_url=base_url or "http://localhost:8300",
                timeout=timeout,
                system_prompt=system_prompt,
                default_params=default_params,
            )
        if mode == "basic":
            raise NotImplementedError(
                "basic 引擎（llm+memory+tts 直连降级实现）预留待实现")
        raise ValueError(f"不支持的 Agent 引擎: {mode}")

    @staticmethod
    def create_from_config(config: dict) -> AgentBase:
        """
        从配置字典创建 Agent 引擎（app/configs/agent/config.yaml 的结构）。

        Args:
            config: {"mode": ..., "pi_sidecar": {...}, "system_prompt": ..., ...}
        """
        mode = config.get("mode", "pi_sidecar")
        engine_config = config.get(mode, {})
        return AgentFactory.create(
            mode,
            base_url=engine_config.get("base_url"),
            timeout=engine_config.get("timeout", 120),
            system_prompt=config.get("system_prompt", ""),
            default_params=engine_config.get("default_params"),
        )

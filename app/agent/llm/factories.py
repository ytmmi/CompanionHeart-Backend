"""LLM 引擎工厂"""

from typing import Optional

from .anthropic import AnthropicLLM
from .base import LLMBase
from .ollama import OllamaLLM
from .openai_llm import OpenAILLM

# 支持的引擎格式（仅这三种）
SUPPORTED_PROVIDERS = ("openai", "ollama", "anthropic")


class LLMFactory:
    """LLM 引擎工厂，根据配置创建对应的 LLM 实例"""

    @staticmethod
    def create(
        provider: str,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 60,
        **kwargs,
    ) -> LLMBase:
        """
        创建 LLM 引擎实例。

        Args:
            provider:   引擎格式，支持 "openai" / "ollama" / "anthropic"。
            base_url:   API 基础 URL。
            api_key:    API 密钥（ollama 不需要）。
            model:      模型名称。
            timeout:    请求超时时间（秒）。
            **kwargs:   引擎特定的额外参数。

        Returns:
            LLMBase 子类实例。

        Raises:
            ValueError: 不支持的 provider。
        """
        provider = provider.lower().strip()

        if provider == "openai":
            return OpenAILLM(
                base_url=base_url or "https://api.openai.com/v1",
                api_key=api_key or "",
                model=model or "gpt-4o",
                timeout=timeout,
                **kwargs,
            )

        if provider == "ollama":
            return OllamaLLM(
                base_url=base_url or "http://localhost:11434",
                model=model or "llama3",
                timeout=timeout,
                **kwargs,
            )

        if provider == "anthropic":
            return AnthropicLLM(
                api_key=api_key or "",
                model=model or "claude-sonnet-4-6",
                base_url=base_url or "https://api.anthropic.com",
                timeout=timeout,
                **kwargs,
            )

        raise ValueError(
            f"不支持的 LLM 引擎格式: {provider}。"
            f"当前支持: {', '.join(SUPPORTED_PROVIDERS)}"
        )

    @staticmethod
    def create_from_config(config: dict) -> LLMBase:
        """
        从配置字典创建 LLM 引擎实例。

        配置格式（对应 configs/llm/config.yaml）:
            {
                "mode": "openai" / "ollama" / "anthropic",
                "openai": { ... },      # OpenAI 兼容格式配置
                "ollama": { ... },      # Ollama 配置
                "anthropic": { ... },   # Anthropic Messages API 配置
            }

        Args:
            config: LLM 配置字典。

        Returns:
            LLMBase 子类实例。
        """
        mode = config.get("mode", "openai")
        provider_config = config.get(mode, {}) or {}

        if mode == "openai":
            return LLMFactory._create_openai_from_config(provider_config)
        if mode == "ollama":
            return LLMFactory._create_ollama_from_config(provider_config)
        if mode == "anthropic":
            return LLMFactory._create_anthropic_from_config(provider_config)

        raise ValueError(
            f"不支持的 LLM 模式: {mode}。"
            f"当前支持: {', '.join(SUPPORTED_PROVIDERS)}"
        )

    # ── 内部方法：从配置字典创建各引擎实例 ──

    @staticmethod
    def _create_openai_from_config(config: dict) -> OpenAILLM:
        """从配置创建 OpenAILLM 实例"""
        return OpenAILLM(
            base_url=config.get("base_url", "https://api.openai.com/v1"),
            api_key=config.get("api_key", ""),
            model=config.get("model", "gpt-4o"),
            timeout=config.get("timeout", 60),
            system_prompt=config.get("system_prompt", ""),
            default_params=config.get("default_params", {}),
        )

    @staticmethod
    def _create_ollama_from_config(config: dict) -> OllamaLLM:
        """从配置创建 OllamaLLM 实例"""
        return OllamaLLM(
            base_url=config.get("base_url", "http://localhost:11434"),
            model=config.get("model", "llama3"),
            timeout=config.get("timeout", 60),
            system_prompt=config.get("system_prompt", ""),
            default_params=config.get("default_params", {}),
        )

    @staticmethod
    def _create_anthropic_from_config(config: dict) -> AnthropicLLM:
        """从配置创建 AnthropicLLM 实例"""
        return AnthropicLLM(
            api_key=config.get("api_key", ""),
            model=config.get("model", "claude-sonnet-4-6"),
            base_url=config.get("base_url", "https://api.anthropic.com"),
            timeout=config.get("timeout", 120),
            system_prompt=config.get("system_prompt", ""),
            default_params=config.get("default_params", {}),
        )

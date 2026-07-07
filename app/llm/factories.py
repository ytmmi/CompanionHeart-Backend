"""LLM 引擎工厂"""

from typing import Optional

from .base import LLMBase
from .openai_llm import OpenAILLM
from .ollama import OllamaLLM


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
            provider:   引擎类型，支持 "openai" / "ollama"。
            base_url:   API 基础 URL。
            api_key:    API 密钥（仅部分引擎需要）。
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

        if provider == "claude":
            # Claude 预留 — 待实现
            raise NotImplementedError("Claude 引擎尚未实现，敬请期待")

        if provider == "gemini":
            # Gemini 预留 — 待实现
            raise NotImplementedError("Gemini 引擎尚未实现，敬请期待")

        if provider == "deepseek":
            # DeepSeek 预留 — 待实现（当前可使用 OpenAI 兼容格式）
            raise NotImplementedError(
                "DeepSeek 专用引擎尚未实现。"
                "DeepSeek 兼容 OpenAI API 格式，当前请使用 provider='openai'。"
            )

        raise ValueError(f"不支持的 LLM 引擎类型: {provider}。当前支持: openai, ollama")

    @staticmethod
    def create_from_config(config: dict) -> LLMBase:
        """
        从配置字典创建 LLM 引擎实例。

        配置格式（对应 configs/llm/config.yaml）:
            {
                "mode": "openai" / "ollama",
                "openai": { ... },    # OpenAI 兼容格式配置
                "ollama": { ... },    # Ollama 配置
                ...
            }

        Args:
            config: LLM 配置字典。

        Returns:
            LLMBase 子类实例。
        """
        mode = config.get("mode", "openai")
        provider_config = config.get(mode, {})

        if mode == "openai":
            return LLMFactory._create_openai_from_config(provider_config)
        if mode == "ollama":
            return LLMFactory._create_ollama_from_config(provider_config)

        raise ValueError(f"不支持的 LLM 模式: {mode}。当前支持: openai, ollama")

    # ── 内部方法：从配置字典创建各引擎实例 ──

    @staticmethod
    def _create_openai_from_config(config: dict) -> OpenAILLM:
        """从配置创建 OpenAILLM 实例"""
        default_params = config.get("default_params", {})
        system_prompt = config.get("system_prompt", "")

        return OpenAILLM(
            base_url=config.get("base_url", "https://api.openai.com/v1"),
            api_key=config.get("api_key", ""),
            model=config.get("model", "gpt-4o"),
            timeout=config.get("timeout", 60),
            system_prompt=system_prompt,
            default_params=default_params,
        )

    @staticmethod
    def _create_ollama_from_config(config: dict) -> OllamaLLM:
        """从配置创建 OllamaLLM 实例"""
        default_params = config.get("default_params", {})
        system_prompt = config.get("system_prompt", "")

        return OllamaLLM(
            base_url=config.get("base_url", "http://localhost:11434"),
            model=config.get("model", "llama3"),
            timeout=config.get("timeout", 60),
            system_prompt=system_prompt,
            default_params=default_params,
        )

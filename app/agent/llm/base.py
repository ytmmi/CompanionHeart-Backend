"""LLM 大语言模型基类"""

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional


class LLMBase(ABC):
    """所有 LLM 引擎的抽象基类"""

    # ── 核心接口 ──

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        **kwargs,
    ) -> str:
        """
        非流式对话：发送消息列表，返回完整回复文本。

        Args:
            messages: 消息列表，每项格式为 {"role": "system"|"user"|"assistant", "content": str}。
            **kwargs: 引擎特定的参数（如 temperature, max_tokens, top_p 等）。

        Returns:
            模型回复文本。
        """
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        流式对话：逐 chunk 产生回复文本。

        Args:
            messages: 消息列表，格式同 chat()。
            **kwargs: 引擎特定的参数。

        Yields:
            回复文本块。
        """
        ...
        # 若引擎不支持流式，可 yield chat(messages, **kwargs)
        yield ""

    # ── 配置与状态 ──

    @abstractmethod
    async def validate_config(self) -> bool:
        """
        验证当前配置是否有效（如 API Key、Base URL 等）。

        Returns:
            True 表示配置有效，False 表示无效。
        """
        ...

    async def get_models(self) -> list[str]:
        """
        获取当前引擎可用的模型列表。

        默认返回空列表，子类可覆写以提供实际模型列表。
        """
        return []

    # ── 生命周期 ──

    async def close(self):
        """
        释放引擎占用的资源（如 HTTP 客户端连接）。

        子类可覆写以执行清理操作。
        """
        pass

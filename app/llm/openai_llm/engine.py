"""OpenAI 兼容格式 LLM 引擎

支持所有兼容 OpenAI Chat Completions API 的服务:
    - OpenAI (GPT-4, GPT-4o, GPT-3.5 等)
    - DeepSeek
    - 任何实现 /v1/chat/completions 标准的 API

依赖:
    pip install openai

文档:
    https://platform.openai.com/docs/api-reference/chat
"""

from typing import AsyncIterator, Optional

from ..base import LLMBase


class OpenAILLM(LLMBase):
    """OpenAI 兼容格式 LLM 引擎"""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "gpt-4o",
        timeout: int = 60,
        system_prompt: str = "",
        default_params: Optional[dict] = None,
    ):
        """
        初始化 OpenAI 兼容引擎。

        Args:
            base_url:       API 基础 URL，如 "https://api.openai.com/v1"。
            api_key:        API 密钥。
            model:          模型名称，如 "gpt-4o" / "deepseek-v4-flash"。
            timeout:        请求超时时间（秒）。
            system_prompt:  系统提示词，发送对话时自动注入。
            default_params: 默认请求参数（temperature, max_tokens, top_p 等）。
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._system_prompt = system_prompt
        self._default_params = default_params or {}
        self._client = None

    # ── 属性 ──

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str):
        self._model = value

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @system_prompt.setter
    def system_prompt(self, value: str):
        self._system_prompt = value

    # ── 内部方法 ──

    def _ensure_client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
                timeout=self._timeout,
                http_client=None,
            )

    def _merge_params(self, kwargs: dict) -> dict:
        """合并默认参数和调用时覆盖的参数"""
        params = {**self._default_params}
        params.update(kwargs)
        # 移除 stream 参数（由 chat_stream 管理）
        params.pop("stream", None)
        return params

    def _build_messages(self, messages: list[dict]) -> list[dict]:
        """构建消息列表，自动注入 system prompt"""
        if not self._system_prompt:
            return messages

        # 检查是否已有 system 消息
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            return [{"role": "system", "content": self._system_prompt}, *messages]
        return messages

    # ── 核心方法 ──

    async def chat(
        self,
        messages: list[dict],
        **kwargs,
    ) -> str:
        """
        非流式对话。

        Args:
            messages: 消息列表，每项 {"role": "system"|"user"|"assistant", "content": str}。
            **kwargs: 可覆盖默认参数（temperature, max_tokens, top_p 等）。

        Returns:
            模型回复文本。
        """
        self._ensure_client()

        full_messages = self._build_messages(messages)
        params = self._merge_params(kwargs)

        response = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            **params,
        )

        return response.choices[0].message.content or ""

    async def chat_stream(
        self,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        流式对话，逐 chunk 产生回复文本。

        Args:
            messages: 消息列表。
            **kwargs: 可覆盖默认参数。

        Yields:
            回复文本块。
        """
        self._ensure_client()

        full_messages = self._build_messages(messages)
        params = self._merge_params(kwargs)

        stream = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            stream=True,
            **params,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    async def validate_config(self) -> bool:
        """
        验证配置：尝试列出可用模型。

        Returns:
            True 表示 API Key 和 Base URL 有效。
        """
        self._ensure_client()
        try:
            # 尝试列出模型（需要 API Key 有 models:list 权限）
            self._client.models.list()
            return True
        except Exception:
            # 部分 API 可能不支持 models.list，尝试简单对话
            try:
                _ = self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                )
                return True
            except Exception:
                return False

    async def get_models(self) -> list[str]:
        """
        获取当前 API 可用的模型列表。

        Returns:
            模型名称列表。
        """
        self._ensure_client()
        try:
            models = self._client.models.list()
            return [m.id for m in models]
        except Exception:
            return []

    async def close(self):
        """释放 HTTP 客户端资源"""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

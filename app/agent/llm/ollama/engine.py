"""Ollama LLM 引擎

基于 Ollama 本地推理服务，支持流式/非流式对话。

依赖:
    pip install httpx

Ollama 安装:
    https://ollama.com/download

文档:
    https://github.com/ollama/ollama/blob/main/docs/api.md
"""

import json
from typing import AsyncIterator, Optional

import httpx

from ..base import LLMBase


class OllamaLLM(LLMBase):
    """Ollama 本地 LLM 引擎"""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        timeout: int = 120,
        system_prompt: str = "",
        default_params: Optional[dict] = None,
    ):
        """
        初始化 Ollama 引擎。

        Args:
            base_url:       Ollama 服务地址，默认 "http://localhost:11434"。
            model:          模型名称，如 "llama3" / "qwen2" / "mistral"。
            timeout:        请求超时时间（秒），Ollama 本地推理可能较慢。
            system_prompt:  系统提示词。
            default_params: 默认请求参数（temperature, top_p, max_tokens 等）。
        """
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._system_prompt = system_prompt
        self._default_params = default_params or {}
        self._client: Optional[httpx.AsyncClient] = None

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
        """延迟初始化 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)

    def _build_messages(self, messages: list[dict]) -> list[dict]:
        """构建消息列表，自动注入 system prompt"""
        if not self._system_prompt:
            return messages

        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            return [{"role": "system", "content": self._system_prompt}, *messages]
        return messages

    def _merge_params(self, kwargs: dict) -> dict:
        """合并默认参数和调用时覆盖的参数"""
        params = {**self._default_params}
        # Ollama 使用 options 嵌套参数
        ollama_options = params.pop("options", {})
        ollama_options.update(kwargs)
        if ollama_options:
            params["options"] = ollama_options
        return params

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
            **kwargs: 可覆盖默认参数。

        Returns:
            模型回复文本。
        """
        self._ensure_client()

        full_messages = self._build_messages(messages)
        params = self._merge_params(kwargs)

        body = {
            "model": self._model,
            "messages": full_messages,
            "stream": False,
            **params,
        }

        response = await self._client.post(
            f"{self._base_url}/api/chat",
            json=body,
        )
        response.raise_for_status()

        data = response.json()
        return data.get("message", {}).get("content", "")

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

        body = {
            "model": self._model,
            "messages": full_messages,
            "stream": True,
            **params,
        }

        async with self._client.stream(
            "POST",
            f"{self._base_url}/api/chat",
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("done"):
                        break
                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue

    async def validate_config(self) -> bool:
        """
        验证配置：检查 Ollama 服务是否可访问。

        Returns:
            True 表示服务可用。
        """
        self._ensure_client()
        try:
            response = await self._client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            return True
        except Exception:
            return False

    async def get_models(self) -> list[str]:
        """
        获取本地已安装的模型列表。

        Returns:
            模型名称列表。
        """
        self._ensure_client()
        try:
            response = await self._client.get(f"{self._base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    async def close(self):
        """释放 HTTP 客户端连接"""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

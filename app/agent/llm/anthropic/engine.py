"""Anthropic 格式 LLM 引擎 — 通过 Messages API 调用

支持所有实现 Anthropic Messages API 格式的服务:
    - Anthropic 官方 API（Claude 系列）
    - 任何兼容 /v1/messages 格式的代理/中转服务

API 文档:
    https://platform.claude.com/docs/en/api/messages

与 OpenAI Chat Completions 的关键差异:
    - system 消息通过请求体的 `system` 字段传入（不在 messages 中）
    - `max_tokens` 是必填参数
    - messages 数组必须交替 user/assistant（无 developer/system role）
"""

import json
from typing import AsyncIterator, Optional

import httpx

from ..base import LLMBase


class AnthropicLLM(LLMBase):
    """Anthropic 格式 LLM 引擎 — Messages API"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        base_url: str = "https://api.anthropic.com",
        timeout: int = 120,
        system_prompt: str = "",
        default_params: Optional[dict] = None,
    ):
        """
        Args:
            api_key:        Anthropic API Key（sk-ant-...）。
            model:          模型 ID，默认 claude-sonnet-4-6。
            base_url:       API 基础地址（可覆盖为代理/中转服务）。
            timeout:        请求超时（秒）。
            system_prompt:  系统提示词。
            default_params: 默认采样参数（temperature, max_tokens 等）。
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
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

    # ── 内部 ──

    def _ensure_client(self):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)

    def _headers(self) -> dict:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _build_messages(self, messages: list[dict]) -> list[dict]:
        """过滤 system 消息（Anthropic 不允许 messages 中带 role:system）"""
        return [m for m in messages if m.get("role") != "system"]

    def _build_body(
        self,
        messages: list[dict],
        stream: bool,
        **kwargs,
    ) -> dict:
        """构建 Anthropic Messages API 请求体"""
        # 合并参数：默认值 → 实例级 system_prompt → 调用覆盖
        system = self._system_prompt
        for m in messages:
            if m.get("role") == "system" and not system:
                system = m.get("content", "")

        params = {**self._default_params, **kwargs}
        max_tokens = params.pop("max_tokens", 2048)

        body: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": self._build_messages(messages),
            "stream": stream,
        }
        if system:
            body["system"] = system
        # 透传 Anthropic 支持的采样参数
        for key in ("temperature", "top_p", "top_k", "stop_sequences"):
            if key in params:
                body[key] = params[key]
        # metadata: user_id 可帮助监控，非必填
        if "metadata" in params:
            body["metadata"] = params["metadata"]

        return body

    # ── 核心 ──

    async def chat(
        self,
        messages: list[dict],
        **kwargs,
    ) -> str:
        """
        非流式对话，返回完整回复文本。

        Args:
            messages: 消息列表，每项 {"role": "user"|"assistant", "content": str}。
            **kwargs: 可覆盖的采样参数。
        """
        self._ensure_client()

        body = self._build_body(messages, stream=False, **kwargs)

        response = await self._client.post(
            f"{self._base_url}/v1/messages",
            headers=self._headers(),
            json=body,
        )
        response.raise_for_status()

        data = response.json()
        # Anthropic 返回 content: [{ type: "text", text: "..." }]
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block.get("text", "")
        return ""

    async def chat_stream(
        self,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        流式对话，逐 token 产生回复文本。

        Args:
            messages: 消息列表。
            **kwargs: 可覆盖的采样参数。
        """
        self._ensure_client()

        body = self._build_body(messages, stream=True, **kwargs)

        async with self._client.stream(
            "POST",
            f"{self._base_url}/v1/messages",
            headers=self._headers(),
            json=body,
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    return

                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                typ = event.get("type", "")
                if typ == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield text
                elif typ == "message_stop":
                    return
                elif typ == "error":
                    msg = event.get("error", {}).get("message", "未知 Anthropic 错误")
                    raise RuntimeError(f"Anthropic API 错误: {msg}")

    async def validate_config(self) -> bool:
        """验证 API Key 和模型可用性（发送最小消息测试）"""
        try:
            await self.chat([{"role": "user", "content": "hi"}], max_tokens=5)
            return True
        except Exception:
            return False

    async def get_models(self) -> list[str]:
        """返回已配置的模型（Anthropic 无公共模型列表 API）"""
        return [self._model]

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

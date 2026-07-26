"""PiSidecarAgentEngine — pi-agent-core sidecar 引擎（对外唯一门面）

sidecar 完全无状态：每轮把 role 化历史（来自短期记忆）+ 本轮输入
整体传给 sidecar，记忆的唯一真源始终在 Python 侧（ConversationStore）。
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from typing import Any, AsyncIterator, Optional

from ..base import AgentBase
from .plugin_client import AgentPluginClient

logger = logging.getLogger(__name__)


class PiSidecarAgentEngine(AgentBase):
    """基于 pi-agent-core sidecar 的 Agent 引擎"""

    def __init__(
        self,
        base_url: str = "http://localhost:8300",
        timeout: int = 120,
        system_prompt: str = "",
        default_params: Optional[dict] = None,
    ):
        """
        Args:
            base_url: sidecar 服务地址
            timeout: 请求超时（秒）
            system_prompt: 默认系统提示词（人格设定）
            default_params: 默认采样参数 {temperature, max_tokens}
        """
        self.client = AgentPluginClient(base_url, timeout)
        self.system_prompt = system_prompt
        self.default_params = default_params or {}
        # 进行中请求：conversation_id/自生成 id → sidecar request_id
        self._active_requests: dict[str, str] = {}
        # 同会话串行锁：防止同一 conversation_id 并发请求乱序写会话存储
        self._conversation_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def conversation_lock(self, track_key: Optional[str]) -> asyncio.Lock:
        """按会话取串行锁（无 track_key 时每次新锁 = 不串行）"""
        if track_key is None:
            return asyncio.Lock()
        return self._conversation_locks[track_key]

    # ── 内部 ──

    def _split_messages(self, messages: list[dict], **kwargs) -> tuple[str, list[dict]]:
        """
        分离 system 消息与对话消息：
        sidecar 的 system_prompt 是独立字段，messages 只收 user/assistant。
        """
        system_prompt = kwargs.get("system_prompt") or self.system_prompt
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                # 请求内嵌 system 消息优先于配置默认
                system_prompt = m["content"]
            else:
                chat_messages.append({"role": m["role"], "content": m["content"]})
        return system_prompt, chat_messages

    def _build_options(self, **kwargs) -> dict:
        """合并默认采样参数与本次覆盖（top_p 不被 sidecar 支持，丢弃并警告）"""
        options = {}
        for key in ("temperature", "max_tokens"):
            value = kwargs.get(key, self.default_params.get(key))
            if value is not None:
                options[key] = value
        if kwargs.get("top_p") is not None:
            logger.warning("pi sidecar 不支持 top_p 参数，已忽略")
        return options

    # ── 核心接口 ──

    async def process_text(self, messages: list[dict], **kwargs) -> dict:
        """非流式处理：agent 循环跑完后返回完整结果（同会话串行）"""
        system_prompt, chat_messages = self._split_messages(messages, **kwargs)
        request_id = kwargs.get("request_id") or uuid.uuid4().hex
        track_key = kwargs.get("track_key", request_id)

        async with self.conversation_lock(kwargs.get("track_key")):
            self._active_requests[track_key] = request_id
            try:
                result = await self.client.chat(
                    messages=chat_messages,
                    system_prompt=system_prompt,
                    request_id=request_id,
                    options=self._build_options(**kwargs),
                )
                return {
                    "reply": result.get("content", ""),
                    "tool_calls": result.get("tool_calls", []),
                    "usage": result.get("usage", {}),
                    "stop_reason": result.get("stop_reason", ""),
                }
            finally:
                self._active_requests.pop(track_key, None)

    async def process_text_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[dict]:
        """流式处理：逐事件产出归一化 agent 事件（同会话串行）"""
        system_prompt, chat_messages = self._split_messages(messages, **kwargs)
        request_id = kwargs.get("request_id") or uuid.uuid4().hex
        track_key = kwargs.get("track_key", request_id)

        async with self.conversation_lock(kwargs.get("track_key")):
            self._active_requests[track_key] = request_id
            try:
                async for event in self.client.chat_stream(
                    messages=chat_messages,
                    system_prompt=system_prompt,
                    request_id=request_id,
                    options=self._build_options(**kwargs),
                ):
                    yield event
            finally:
                self._active_requests.pop(track_key, None)

    # ── 控制 ──

    async def abort(self, request_id: Optional[str] = None) -> bool:
        """
        中断进行中的请求。

        Args:
            request_id: track_key（如 conversation_id）或 sidecar request_id；
                        None 表示中断全部进行中请求。
        """
        if request_id is None:
            results = [
                await self.client.abort(rid)
                for rid in list(self._active_requests.values())
            ]
            return any(results)
        sidecar_id = self._active_requests.get(request_id, request_id)
        return await self.client.abort(sidecar_id)

    # ── 配置与状态 ──

    async def validate_config(self) -> bool:
        """验证 sidecar 是否可达"""
        return await self.client.health_check()

    async def get_info(self) -> dict[str, Any]:
        """获取 sidecar 信息"""
        return await self.client.get_info()

"""Agent sidecar HTTP 客户端

通过 HTTP 与 AGENT_pi sidecar（pi-agent-core 无状态服务）通信。
照 app/tts/plugin_client.py 的样板，基于 PluginHTTPClient。
"""

import json
import logging
from typing import AsyncIterator, Optional

from ...plugins.client import PluginHTTPClient
from .events import normalize_event

logger = logging.getLogger(__name__)


class AgentPluginClient:
    """Agent sidecar HTTP 客户端"""

    def __init__(self, base_url: str, timeout: int = 120):
        """
        Args:
            base_url: sidecar 服务地址（如 http://localhost:8300）
            timeout: 请求超时时间（秒）
        """
        self.client = PluginHTTPClient(base_url, timeout)

    async def health_check(self) -> bool:
        """sidecar 是否可达"""
        return await self.client.health_check()

    async def get_info(self) -> dict:
        """获取 sidecar 信息（模型/provider/工具/能力标志）"""
        resp = await self.client.get("/info")
        resp.raise_for_status()
        return resp.json()

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str = "",
        request_id: Optional[str] = None,
        options: Optional[dict] = None,
        tool_context: Optional[dict] = None,
    ) -> dict:
        """
        非流式对话。

        Args:
            messages: role 化历史 + 本轮输入（最后一条必须是 user）
            system_prompt: 系统提示词
            request_id: 请求标识（用于 abort）
            options: 采样参数 {temperature, max_tokens}

        Returns:
            {"content": str, "tool_calls": list, "usage": dict, "stop_reason": str}
        """
        payload: dict = {"messages": messages, "system_prompt": system_prompt}
        if request_id:
            payload["request_id"] = request_id
        if options:
            payload["options"] = options
        if tool_context:
            payload["tool_context"] = tool_context

        resp = await self.client.post("/chat", json=payload)
        if resp.status_code != 200:
            detail = resp.json().get("detail", resp.text) if resp.content else resp.text
            raise RuntimeError(f"sidecar 对话失败({resp.status_code}): {detail}")
        return resp.json()

    async def chat_stream(
        self,
        messages: list[dict],
        system_prompt: str = "",
        request_id: Optional[str] = None,
        options: Optional[dict] = None,
        tool_context: Optional[dict] = None,
    ) -> AsyncIterator[dict]:
        """
        流式对话：解析 sidecar 的 NDJSON 字节流，逐行产出归一化事件字典。

        Yields:
            事件字典（见 events.py：delta / thinking / tool / done / error）
        """
        payload: dict = {"messages": messages, "system_prompt": system_prompt}
        if request_id:
            payload["request_id"] = request_id
        if options:
            payload["options"] = options
        if tool_context:
            payload["tool_context"] = tool_context

        buffer = b""
        async for chunk in self.client.stream_post("/chat/stream", json=payload):
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    yield normalize_event(json.loads(line.decode("utf-8")))
                except json.JSONDecodeError as e:
                    logger.warning("sidecar NDJSON 行解析失败: %s", e)

    async def abort(self, request_id: str) -> bool:
        """中断进行中的请求"""
        try:
            resp = await self.client.post("/abort", json={"request_id": request_id})
            resp.raise_for_status()
            return bool(resp.json().get("ok"))
        except Exception as e:
            logger.warning("sidecar abort 失败: %s", e)
            return False

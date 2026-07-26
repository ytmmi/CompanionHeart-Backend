"""Agent 智能代理基类

对齐 tests/参考文档/AI-Agent开发指南.md 的 AgentBase 契约，
并按现有模块（LLM/TTS）的流式风格补齐。
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional


class AgentBase(ABC):
    """所有 Agent 引擎的抽象基类"""

    # ── 核心接口 ──

    @abstractmethod
    async def process_text(
        self,
        messages: list[dict],
        **kwargs,
    ) -> dict:
        """
        非流式处理：发送消息列表，agent 循环（LLM + 工具调用）跑完后返回完整结果。

        Args:
            messages: 消息列表，每项 {"role": "system"|"user"|"assistant", "content": str}，
                      最后一条必须是 user（本轮输入）。
            **kwargs: 引擎特定参数（如 temperature, max_tokens, system_prompt）。

        Returns:
            {"reply": str, "tool_calls": list[dict], "usage": dict, "stop_reason": str}
        """
        ...

    @abstractmethod
    async def process_text_stream(
        self,
        messages: list[dict],
        **kwargs,
    ) -> AsyncIterator[dict]:
        """
        流式处理：逐事件产生归一化的 agent 事件。

        Yields:
            事件字典，type 字段区分:
            - {"type": "delta", "content": str}       文本增量
            - {"type": "thinking", "content": str}    思考增量（默认由上层过滤）
            - {"type": "tool", "phase": "start"|"end", "name": str, ...}  工具执行
            - {"type": "done", "content_full": str, "usage": dict, "stop_reason": str}
            - {"type": "error", "message": str}
        """
        ...
        yield {}

    async def process_audio(
        self,
        audio_data: bytes,
        **kwargs,
    ) -> AsyncIterator[bytes]:
        """
        语音处理：ASR → agent → TTS 完整链路（待 ASR 模块实现后补齐）。

        默认未实现，子类可覆写。
        """
        raise NotImplementedError("语音链路待 ASR 模块实现后支持")
        yield b""

    # ── 控制 ──

    async def abort(self, request_id: Optional[str] = None) -> bool:
        """
        中断进行中的处理。

        Args:
            request_id: 要中断的请求标识；None 表示由引擎自行决定（如中断全部）。

        Returns:
            True 表示成功发出中断。
        """
        return False

    # ── 配置与状态 ──

    @abstractmethod
    async def validate_config(self) -> bool:
        """验证当前配置是否有效（如 sidecar 是否可达）"""
        ...

    async def get_info(self) -> dict[str, Any]:
        """获取引擎信息（模型/provider/工具/能力标志），子类可覆写"""
        return {}

    # ── 生命周期 ──

    async def close(self):
        """释放引擎占用的资源，子类可覆写"""
        pass

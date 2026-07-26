"""记忆提供者协议

对齐 tests/参考文档/AI-Agent开发指南.md 4.3 节的 MemoryBase 契约。
用 Protocol（而非 ABC）定义，便于将来长期记忆模块独立实现而不反向依赖 app/agent。

Phase 1 提供 ConversationStoreMemory 适配现有短期记忆
（app/memory/short_term/store.py），store 零改动。
"""

from typing import Optional, Protocol, runtime_checkable

from app.memory.short_term import get_conversation_store


@runtime_checkable
class MemoryProvider(Protocol):
    """记忆提供者协议（与 MemoryBase 契约同形）"""

    def add_user_message(self, text: str) -> None:
        """添加用户消息"""
        ...

    def add_ai_message(self, text: str) -> None:
        """添加 AI 回复"""
        ...

    def get_context(self, max_tokens: int = 4000) -> list[dict]:
        """
        获取对话上下文。

        Returns:
            消息列表 [{"role": ..., "content": ...}]
        """
        ...

    def clear(self) -> None:
        """清空记忆"""
        ...


class ConversationStoreMemory:
    """短期记忆适配器 — 包装现有 ConversationStore（每会话一实例）"""

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self._store = get_conversation_store()

    def add_user_message(self, text: str) -> Optional[object]:
        """写入用户消息；会话不存在时返回 None（与 store 行为一致）"""
        return self._store.append_message(self.conversation_id, "user", text)

    def add_ai_message(self, text: str) -> Optional[object]:
        """写入 AI 回复；会话不存在时返回 None"""
        return self._store.append_message(self.conversation_id, "assistant", text)

    def get_context(self, max_tokens: int = 4000) -> Optional[list[dict]]:
        """
        获取最近上下文（当前由 store.build_context 的条数截断策略决定，
        max_tokens 参数留待长期记忆/token 预算实现时生效）。

        会话不存在返回 None。
        """
        return self._store.build_context(self.conversation_id)

    def clear(self) -> None:
        """清空记忆 — ConversationStore 暂无清空消息的公开 API，
        待长期记忆设计时一并补齐（Phase 4）。"""
        raise NotImplementedError("短期记忆清空待 ConversationStore 提供公开 API")

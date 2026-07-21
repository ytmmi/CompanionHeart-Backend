"""短期记忆 — 多对话上下文存储

提供 ConversationStore：以 JSON 文件持久化的多对话（会话）管理，
支持开启新对话、追加消息、组装 LLM 上下文、历史对话列表/加载/删除/重命名。
"""

from .store import ConversationStore, Conversation, ConversationMeta, get_conversation_store

__all__ = [
    "ConversationStore",
    "Conversation",
    "ConversationMeta",
    "get_conversation_store",
]

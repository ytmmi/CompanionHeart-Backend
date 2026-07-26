"""Agent 智能代理模块

pi（earendil-works/pi）的 pi-agent-core 作为代理引擎框架，
经 custom_plugin/AGENT_pi sidecar（无状态 HTTP 服务）接入。
记忆与 pi 完全分离：上下文由 Python 侧短期记忆组装、每轮 role 化注入。
"""

from .base import AgentBase
from .factories import AgentFactory
from .memory_provider import ConversationStoreMemory, MemoryProvider
from .pi_sidecar import PiSidecarAgentEngine

__all__ = [
    "AgentBase",
    "AgentFactory",
    "MemoryProvider",
    "ConversationStoreMemory",
    "PiSidecarAgentEngine",
]

"""Agent 智能代理模块

pi（earendil-works/pi）的 pi-agent-core 作为代理引擎框架，
经 custom_plugin/AGENT_pi sidecar（无状态 HTTP 服务）接入。
记忆与 pi 完全分离：上下文由 Python 侧短期记忆组装、每轮 role 化注入。

子模块 llm/ 是 Agent 的推理底座（openai / ollama / anthropic 三种格式）。
"""

from .base import AgentBase
from .factories import AgentFactory
from .llm import (
    SUPPORTED_PROVIDERS,
    AnthropicLLM,
    LLMBase,
    LLMFactory,
    OllamaLLM,
    OpenAILLM,
)
from .memory_provider import ConversationStoreMemory, MemoryProvider
from .pi_sidecar import PiSidecarAgentEngine

__all__ = [
    # Agent 层
    "AgentBase",
    "AgentFactory",
    "MemoryProvider",
    "ConversationStoreMemory",
    "PiSidecarAgentEngine",
    # LLM 层
    "LLMBase",
    "LLMFactory",
    "OpenAILLM",
    "OllamaLLM",
    "AnthropicLLM",
    "SUPPORTED_PROVIDERS",
]

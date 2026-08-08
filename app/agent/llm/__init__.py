"""LLM 大语言模型模块（Agent 的推理底座）

仅支持三种格式:
    - openai:     OpenAI 兼容格式（OpenAI / DeepSeek / vLLM / LM Studio 等）
    - ollama:     Ollama 本地推理（需安装 Ollama）
    - anthropic:  Anthropic Messages API 格式（Claude 系列及兼容中转）

对话链路的对外入口是 app.agent 的 Agent 引擎；本模块提供裸 LLM 调用能力。
"""

from .anthropic import AnthropicLLM
from .base import LLMBase
from .factories import SUPPORTED_PROVIDERS, LLMFactory
from .ollama import OllamaLLM
from .openai_llm import OpenAILLM

__all__ = [
    "LLMBase",
    "OpenAILLM",
    "OllamaLLM",
    "AnthropicLLM",
    "LLMFactory",
    "SUPPORTED_PROVIDERS",
]

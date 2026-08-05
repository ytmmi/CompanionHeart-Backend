"""LLM 大语言模型模块

支持的引擎:
    - openai:    OpenAI 兼容格式（支持 DeepSeek / OpenAI / 任何兼容 API）
    - ollama:    Ollama 本地推理（需安装 Ollama）
    - claude:    Anthropic Claude（Messages API）
    - gemini:    Google Gemini（预留接口）
    - deepseek:  DeepSeek（预留接口）
"""

from .base import LLMBase
from .openai_llm import OpenAILLM
from .ollama import OllamaLLM
from .claude import ClaudeLLM
from .factories import LLMFactory

__all__ = [
    "LLMBase",
    "OpenAILLM",
    "OllamaLLM",
    "ClaudeLLM",
    "LLMFactory",
]

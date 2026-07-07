"""DeepSeek LLM 引擎（预留接口）

TODO:
    - 安装依赖: pip install openai（已安装，复用 OpenAI 兼容格式）
    - 实现 LLMBase 抽象方法
    - 支持 DeepSeek 专用 API 特性（如 FIM 补全、前缀续写等）

注意:
    DeepSeek API 兼容 OpenAI Chat Completions 格式，
    当前可通过 LLMFactory.create("openai", ...) 使用。
    此预留接口用于未来实现 DeepSeek 特有功能。

API 文档:
    https://api-docs.deepseek.com/

使用示例（待实现）:
    from app.llm import LLMFactory

    llm = LLMFactory.create("deepseek", api_key="sk-...", model="deepseek-v4-flash")
    reply = await llm.chat([{"role": "user", "content": "你好"}])
"""

from typing import AsyncIterator

from ..base import LLMBase


class DeepSeekLLM(LLMBase):
    """DeepSeek LLM 引擎（预留）"""

    def __init__(self, **kwargs):
        raise NotImplementedError(
            "DeepSeekLLM 尚未实现。"
            "DeepSeek 兼容 OpenAI API 格式，当前请使用 "
            "LLMFactory.create('openai', base_url='https://api.deepseek.com', ...)。"
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        raise NotImplementedError

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        raise NotImplementedError

    async def validate_config(self) -> bool:
        raise NotImplementedError

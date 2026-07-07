"""Google Gemini LLM 引擎（预留接口）

TODO:
    - 安装依赖: pip install google-genai
    - 实现 LLMBase 抽象方法
    - 支持 Gemini API (GenerativeModel)
    - 支持流式对话

API 文档:
    https://ai.google.dev/gemini-api/docs

使用示例（待实现）:
    from app.llm import LLMFactory

    llm = LLMFactory.create("gemini", api_key="...", model="gemini-2.0-flash")
    reply = await llm.chat([{"role": "user", "content": "你好"}])
"""

from typing import AsyncIterator

from ..base import LLMBase


class GeminiLLM(LLMBase):
    """Google Gemini LLM 引擎（预留）"""

    def __init__(self, **kwargs):
        raise NotImplementedError(
            "GeminiLLM 尚未实现。"
            "请使用 LLMFactory.create('openai', ...) 或等待后续版本。"
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        raise NotImplementedError

    async def chat_stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        raise NotImplementedError

    async def validate_config(self) -> bool:
        raise NotImplementedError

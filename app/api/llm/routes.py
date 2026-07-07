"""LLM 对话 API 路由

端点:
    GET    /api/llm/models       — 获取可用模型列表
    GET    /api/llm/status        — 获取 LLM 引擎状态
    POST   /api/llm/chat         — 非流式对话（返回完整回复文本）
    POST   /api/llm/chat/stream  — 流式对话（SSE，逐 chunk 返回文本）

支持的 LLM 引擎:
    - openai:  OpenAI 兼容格式（DeepSeek / OpenAI / 任何兼容 API）
             参数: model, temperature, max_tokens, top_p, system_prompt
    - ollama:  Ollama 本地推理
             参数: model, temperature, max_tokens, top_p, system_prompt

流式 / 非流式:
    - POST /api/llm/chat        → chat()         → 完整回复 JSON
    - POST /api/llm/chat/stream → chat_stream()  → SSE text/event-stream
"""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.llm import LLMBase, LLMFactory

logger = logging.getLogger(__name__)

# ── 路由定义 ──
router = APIRouter(prefix="/api/llm", tags=["LLM"])


# ── 请求/响应模型 ──

class Message(BaseModel):
    """对话消息"""
    role: str = Field(..., pattern=r"^(system|user|assistant)$", description="角色: system / user / assistant")
    content: str = Field(..., min_length=1, description="消息内容")


class ChatRequest(BaseModel):
    """对话请求"""
    messages: list[Message] = Field(
        ..., min_length=1, max_length=100,
        description="对话消息列表（支持多轮上下文）",
        examples=[[{"role": "user", "content": "你好"}]],
    )
    model: Optional[str] = Field(None, description="模型名称（覆盖配置中的默认模型）")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="采样温度 0~2")
    max_tokens: Optional[int] = Field(None, ge=1, le=65536, description="最大输出 token 数")
    top_p: Optional[float] = Field(None, ge=0.0, le=1.0, description="核采样阈值 0~1")
    system_prompt: Optional[str] = Field(None, description="临时覆盖系统提示词（仅本次对话）")


class ChatResponse(BaseModel):
    """对话响应"""
    reply: str = Field(..., description="模型回复文本")
    model: str = Field(..., description="使用的模型名称")
    engine: str = Field(..., description="引擎类型")


class ModelInfo(BaseModel):
    """模型信息"""
    id: str = Field(..., description="模型标识")
    engine: str = Field(..., description="所属引擎")


class ModelsResponse(BaseModel):
    """模型列表响应"""
    models: list[ModelInfo] = Field(..., description="可用模型列表")
    engine: str = Field(..., description="当前引擎类型")
    default_model: str = Field(..., description="默认模型名称")


class LLMStatus(BaseModel):
    """LLM 引擎状态"""
    engine: str = Field(..., description="引擎类型")
    model: str = Field(..., description="当前模型")
    streaming_supported: bool = Field(..., description="是否支持流式")
    config_valid: bool = Field(..., description="配置是否有效")


# ── 依赖注入 ──

_llm_engine: Optional[LLMBase] = None
_llm_config: Optional[dict] = None


async def get_llm_engine() -> LLMBase:
    """获取 LLM 引擎实例（单例）"""
    global _llm_engine
    if _llm_engine is None:
        try:
            config = _load_llm_config()
            _llm_engine = LLMFactory.create_from_config(config)
            logger.info("LLM 引擎初始化成功: %s (model=%s)",
                        type(_llm_engine).__name__, _llm_engine.model)
        except (NotImplementedError, ValueError) as e:
            logger.error("LLM 引擎初始化失败（配置错误）: %s", e)
            raise HTTPException(status_code=500, detail=f"LLM 配置错误: {e}")
        except Exception as e:
            logger.error("LLM 引擎初始化失败: %s", e)
            raise HTTPException(status_code=500, detail=f"LLM 引擎初始化失败: {e}")
    return _llm_engine


def _load_llm_config() -> dict:
    """从 YAML 文件加载 LLM 配置"""
    global _llm_config
    if _llm_config is not None:
        return _llm_config

    import yaml

    # app/api/llm/routes.py → app/configs/llm/config.yaml
    config_path = Path(__file__).parents[2] / "configs" / "llm" / "config.yaml"
    if not config_path.exists():
        logger.warning("LLM 配置文件不存在: %s，使用默认配置", config_path)
        _llm_config = {
            "mode": "openai",
            "openai": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "gpt-4o",
                "timeout": 60,
                "default_params": {"temperature": 0.7, "max_tokens": 2048},
                "system_prompt": "你是一个有用的AI助手。",
            },
        }
        return _llm_config

    with open(config_path, "r", encoding="utf-8") as f:
        _llm_config = yaml.safe_load(f)
    return _llm_config


def _get_engine_type(engine: LLMBase) -> str:
    """获取引擎类型名称"""
    return type(engine).__name__.replace("LLM", "").lower()


def _build_chat_kwargs(request: ChatRequest, engine: LLMBase) -> dict:
    """
    根据请求参数构建引擎调用参数。
    合并默认参数和请求中的覆盖参数。
    """
    kwargs: dict = {}

    # 模型覆盖
    if request.model:
        engine.model = request.model

    # 参数覆盖
    param_overrides = {}
    if request.temperature is not None:
        param_overrides["temperature"] = request.temperature
    if request.max_tokens is not None:
        param_overrides["max_tokens"] = request.max_tokens
    if request.top_p is not None:
        param_overrides["top_p"] = request.top_p

    if param_overrides:
        kwargs.update(param_overrides)

    # 临时 system prompt 覆盖
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    if request.system_prompt is not None:
        # 替换或添加 system prompt
        messages = [m for m in messages if m["role"] != "system"]
        messages.insert(0, {"role": "system", "content": request.system_prompt})

    kwargs["messages"] = messages
    return kwargs


# ── 路由 ──

@router.get("/models", response_model=ModelsResponse)
async def list_models(
    engine: LLMBase = Depends(get_llm_engine),
):
    """
    获取当前 LLM 引擎可用的模型列表。

    返回模型 ID 列表、当前引擎类型和默认模型名称。
    """
    try:
        models = await engine.get_models()
        engine_type = _get_engine_type(engine)

        if models:
            model_list = [ModelInfo(id=m, engine=engine_type) for m in models]
        else:
            # 引擎不支持列出模型时，返回当前模型
            model_list = [ModelInfo(id=engine.model, engine=engine_type)]

        return ModelsResponse(
            models=model_list,
            engine=engine_type,
            default_model=engine.model,
        )
    except Exception as e:
        logger.error("获取模型列表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {e}")


@router.get("/status", response_model=LLMStatus)
async def llm_status(
    engine: LLMBase = Depends(get_llm_engine),
):
    """获取当前 LLM 引擎的状态信息（类型、模型、流式支持、配置有效性）"""
    try:
        config_valid = await engine.validate_config()
        return LLMStatus(
            engine=_get_engine_type(engine),
            model=engine.model,
            streaming_supported=True,
            config_valid=config_valid,
        )
    except Exception as e:
        logger.error("获取 LLM 状态失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取 LLM 状态失败: {e}")


# ── 非流式对话：返回完整回复 ──

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    engine: LLMBase = Depends(get_llm_engine),
):
    """
    非流式对话 — 发送消息列表，返回完整回复文本。

    支持多轮上下文（messages 中传入多轮对话历史）。
    可通过参数覆盖临时调整 temperature / max_tokens / top_p。
    可通过 system_prompt 临时覆盖系统提示词。
    """
    try:
        kwargs = _build_chat_kwargs(request, engine)
        messages = kwargs.pop("messages")

        reply = await engine.chat(messages=messages, **kwargs)

        logger.info("LLM 对话成功: model=%s, messages=%d, reply_len=%d",
                    engine.model, len(messages), len(reply))

        return ChatResponse(
            reply=reply,
            model=engine.model,
            engine=_get_engine_type(engine),
        )
    except Exception as e:
        logger.error("LLM 对话失败: %s", e)
        raise HTTPException(status_code=500, detail=f"LLM 对话失败: {e}")


# ── 流式对话：SSE 逐 chunk 返回文本 ──

@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    engine: LLMBase = Depends(get_llm_engine),
):
    """
    流式对话 — SSE (text/event-stream) 逐 chunk 返回回复文本。

    每个 chunk 格式: `data: {"content": "...", "model": "...", "engine": "..."}\n\n`
    结束标志: `data: [DONE]\n\n`

    适用于实时显示 LLM 输出的场景（如打字机效果）。
    """
    try:
        kwargs = _build_chat_kwargs(request, engine)
        messages = kwargs.pop("messages")

        async def event_stream():
            try:
                full_reply = []
                async for chunk in engine.chat_stream(messages=messages, **kwargs):
                    full_reply.append(chunk)
                    yield f"data: {json.dumps({'content': chunk, 'model': engine.model, 'engine': _get_engine_type(engine)}, ensure_ascii=False)}\n\n"

                yield "data: [DONE]\n\n"
                logger.info("LLM 流式对话完成: model=%s, messages=%d, reply_len=%d",
                            engine.model, len(messages), sum(len(c) for c in full_reply))
            except Exception as e:
                logger.error("LLM 流式对话中断: %s", e)
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            content=event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Engine-Type": _get_engine_type(engine),
                "X-Model": engine.model,
            },
        )
    except Exception as e:
        logger.error("LLM 流式对话启动失败: %s", e)
        raise HTTPException(status_code=500, detail=f"LLM 流式对话失败: {e}")

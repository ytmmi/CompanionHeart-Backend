"""Agent 对话 API 路由

端点:
    GET    /api/agent/status         — Agent 引擎状态（sidecar health/info 透传）
    GET    /api/agent/tools          — 可用工具列表
    POST   /api/agent/chat           — 非流式对话（完整回复 + 工具调用摘要）
    POST   /api/agent/chat/stream    — 流式对话（SSE）
    POST   /api/agent/chat/stream/sentences — 句子级流式（NDJSON，文本+TTS 音频成对到达）
    POST   /api/agent/abort          — 中断进行中的对话

对话模式（二选一）:
    - 无状态模式: 传 messages，多轮上下文由调用方维护
    - 会话模式:   传 conversation_id + text，上下文由后端短期记忆组装，
                用户消息与回复自动持久化（记忆唯一真源在 Python 侧，
                sidecar 完全无状态 —— 记忆与 pi 分离的核心保证）

SSE 输出格式:
    data: {"content": ...} 逐块下发，末尾 data: [DONE]；
    工具事件作为附加 key（"tool"）出现，不消费的前端忽略即可。
    —— 旧 /api/llm 路由已下线，对话统一收敛至本路由。
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.agent import AgentBase, AgentFactory
from app.agent.companion import (
    CompanionChatService,
    ConversationNotFound,
    InvalidChatMode,
    ResolvedChatTurn,
)
from app.memory.roles import RoleConfigError
from app.memory.life import LifeMemoryService, create_life_memory_service
from app.developer import (
    DeveloperAuthAction,
    DeveloperAuthInterceptor,
    DeveloperAuthOutcome,
    DeveloperChatService,
    get_developer_auth,
)
from app.developer import configure_developer_auth as configure_developer_auth_runtime
from app.utils.sentence import SentenceSplitter

logger = logging.getLogger(__name__)

# ── 路由定义 ──
router = APIRouter(prefix="/api/agent", tags=["Agent"])


# ── 请求/响应模型 ──

class Message(BaseModel):
    """对话消息"""
    role: str = Field(..., pattern=r"^(system|user|assistant)$", description="角色: system / user / assistant")
    content: str = Field(..., min_length=1, description="消息内容")


class AgentChatRequest(BaseModel):
    """对话请求 — 两种模式（二选一）"""
    messages: Optional[list[Message]] = Field(
        None, min_length=1, max_length=100,
        description="无状态模式：对话消息列表（支持多轮上下文）",
        examples=[[{"role": "user", "content": "你好"}]],
    )
    conversation_id: Optional[str] = Field(
        None, description="会话模式：会话 ID（由 POST /api/conversations 创建）",
    )
    role_name_en: Optional[str] = Field(
        None,
        description="角色英文名；缺省使用 app/configs/roles 中的默认角色",
    )
    text: Optional[str] = Field(
        None, min_length=1, description="会话模式：本次用户消息文本",
    )
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="采样温度 0~2")
    max_tokens: Optional[int] = Field(None, ge=1, le=65536, description="最大输出 token 数")
    system_prompt: Optional[str] = Field(None, description="临时覆盖系统提示词（仅本次对话）")
    include_thinking: bool = Field(False, description="流式模式下是否输出思考增量")


class ToolCallInfo(BaseModel):
    """工具调用摘要"""
    name: str = Field(..., description="工具名称")
    args: Optional[dict] = Field(None, description="调用参数")
    is_error: bool = Field(False, description="执行是否出错")


class AgentChatResponse(BaseModel):
    """对话响应"""
    reply: str = Field(..., description="agent 回复文本")
    tool_calls: list[ToolCallInfo] = Field(default_factory=list, description="本轮工具调用摘要")
    model: str = Field(..., description="使用的模型名称")
    engine: str = Field(..., description="引擎类型")
    conversation_id: Optional[str] = Field(None, description="会话模式下回传会话 ID")
    role_name_en: str = Field(..., description="本轮对话所属角色英文名")


class AgentStatus(BaseModel):
    """Agent 引擎状态"""
    engine: str = Field(..., description="引擎类型")
    pi_version: str = Field("", description="pi-agent-core 版本")
    provider: str = Field("", description="LLM provider")
    model: str = Field("", description="当前模型")
    tools: list[str] = Field(default_factory=list, description="已启用工具")
    sidecar_healthy: bool = Field(..., description="sidecar 是否可达")
    capabilities: dict = Field(default_factory=dict, description="能力标志（如 top_p: false 表示不支持）")


class AbortRequest(BaseModel):
    """中断请求"""
    conversation_id: Optional[str] = Field(None, description="要中断的会话；不传则中断全部")
    role_name_en: Optional[str] = Field(None, description="会话所属角色；缺省使用默认角色")


# ── 依赖注入 ──

_agent_engine: Optional[AgentBase] = None
_agent_config: Optional[dict] = None
_chat_service: Optional[CompanionChatService] = None
_life_memory_service: Optional[LifeMemoryService] = None
_developer_chat = DeveloperChatService()


def configure_developer_auth(interceptor: DeveloperAuthInterceptor) -> None:
    """测试/应用装配注入；开发密钥仍只能由 interceptor 的安全 provider 提供。"""
    configure_developer_auth_runtime(interceptor)


def configure_developer_chat_service(service: DeveloperChatService) -> None:
    global _developer_chat
    _developer_chat = service


def _developer_preflight(
    payload: AgentChatRequest, http_request: Request
) -> DeveloperAuthOutcome:
    """必须在 sidecar 检查、会话写入和日志之前执行。"""
    text = payload.text
    if text is None and payload.messages:
        users = [message.content for message in payload.messages if message.role == "user"]
        text = users[-1] if users else ""
    session_id = (
        http_request.headers.get("X-Developer-Session-Id")
        or http_request.cookies.get("companionheart_dev_session")
    )
    client_id = http_request.headers.get("X-Companion-Client-Id", "local-desktop")
    return get_developer_auth().inspect(
        text or "", client_id=client_id, session_id=session_id
    )


def _developer_status_code(outcome: DeveloperAuthOutcome) -> int:
    if outcome.action == DeveloperAuthAction.DENIED:
        return 401
    if outcome.action == DeveloperAuthAction.RATE_LIMITED:
        return 429
    return 200


def _set_developer_headers(response, outcome: DeveloperAuthOutcome) -> None:
    response.headers["X-Developer-Mode"] = "active" if outcome.developer_mode else "inactive"
    if outcome.session_id:
        response.headers["X-Developer-Session-Id"] = outcome.session_id
        response.set_cookie(
            "companionheart_dev_session",
            outcome.session_id,
            max_age=1800,
            httponly=True,
            samesite="strict",
        )
    elif outcome.action == DeveloperAuthAction.EXITED:
        response.delete_cookie("companionheart_dev_session")


def _developer_json_response(
    payload: AgentChatRequest, outcome: DeveloperAuthOutcome
) -> JSONResponse:
    try:
        role = get_companion_chat_service().role_registry.resolve(payload.role_name_en)
        role_name_en = role.name_en
    except RoleConfigError:
        role_name_en = payload.role_name_en or ""
    response = JSONResponse(
        status_code=_developer_status_code(outcome),
        content={
            "reply": outcome.message,
            "tool_calls": [],
            "model": "",
            "engine": "developer-auth",
            "conversation_id": payload.conversation_id,
            "role_name_en": role_name_en,
        },
    )
    _set_developer_headers(response, outcome)
    return response


def _developer_stream_response(
    outcome: DeveloperAuthOutcome, *, sentences: bool = False
) -> StreamingResponse:
    async def content():
        if sentences:
            yield (json.dumps({"type": "sentence", "text": outcome.message}, ensure_ascii=False) + "\n").encode()
            yield b'{"type":"done"}\n'
        else:
            yield f"data: {json.dumps({'content': outcome.message, 'engine': 'developer-auth'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    response = StreamingResponse(
        content(),
        status_code=_developer_status_code(outcome),
        media_type="application/x-ndjson" if sentences else "text/event-stream",
    )
    _set_developer_headers(response, outcome)
    return response


def _load_agent_config() -> dict:
    """从 YAML 文件加载 Agent 配置"""
    global _agent_config
    if _agent_config is not None:
        return _agent_config

    import yaml

    config_path = Path(__file__).parents[2] / "configs" / "agent" / "config.yaml"
    if not config_path.exists():
        logger.warning("Agent 配置文件不存在: %s，使用默认配置", config_path)
        _agent_config = {"mode": "pi_sidecar", "pi_sidecar": {"base_url": "http://localhost:8300"}}
        return _agent_config

    with open(config_path, "r", encoding="utf-8") as f:
        _agent_config = yaml.safe_load(f)
    return _agent_config


def _resolve_system_prompt(config: dict) -> str:
    """人格提示词：agent config 优先，缺省回退 llm config 的 system_prompt"""
    if config.get("system_prompt"):
        return config["system_prompt"]

    import yaml

    llm_config_path = Path(__file__).parents[2] / "configs" / "llm" / "config.yaml"
    if llm_config_path.exists():
        with open(llm_config_path, "r", encoding="utf-8") as f:
            llm_config = yaml.safe_load(f)
        mode = llm_config.get("mode", "openai")
        return llm_config.get(mode, {}).get("system_prompt", "")
    return ""


async def get_agent_engine() -> AgentBase:
    """获取 Agent 引擎实例（单例）"""
    global _agent_engine
    if _agent_engine is None:
        try:
            config = _load_agent_config()
            config = {**config, "system_prompt": _resolve_system_prompt(config)}
            _agent_engine = AgentFactory.create_from_config(config)
            logger.info("Agent 引擎初始化成功: %s", type(_agent_engine).__name__)
        except (NotImplementedError, ValueError) as e:
            logger.error("Agent 引擎初始化失败（配置错误）: %s", e)
            raise HTTPException(status_code=500, detail=f"Agent 配置错误: {e}")
        except Exception as e:
            logger.error("Agent 引擎初始化失败: %s", e)
            raise HTTPException(status_code=500, detail=f"Agent 引擎初始化失败: {e}")
    return _agent_engine


async def _ensure_sidecar(engine: AgentBase) -> None:
    """sidecar 崩溃自愈：不可达时尝试重启一次插件，仍失败则 503"""
    if await engine.validate_config():
        return
    from app.main import restart_agent_plugin

    logger.warning("sidecar 不可达，尝试自动重启...")
    if restart_agent_plugin() and await engine.validate_config():
        logger.info("sidecar 自愈成功")
        return
    raise HTTPException(status_code=503, detail="agent sidecar 不可用（自动重启失败）")


# ── 聊天编排 ──

def get_companion_chat_service() -> CompanionChatService:
    """获取陪伴聊天编排服务单例。"""
    global _chat_service
    if _chat_service is None:
        _chat_service = CompanionChatService(life_memory=get_life_memory_service())
    return _chat_service


def get_life_memory_service() -> LifeMemoryService | None:
    """从记忆配置创建协议转发器；真正的记忆处理只在 MEMORY_omni 内完成。"""
    global _life_memory_service
    if _life_memory_service is not None:
        return _life_memory_service
    _life_memory_service = create_life_memory_service()
    return _life_memory_service


async def _resolve_turn(
    request: AgentChatRequest,
    developer: DeveloperAuthOutcome | None = None,
    developer_client_id: str = "local-desktop",
) -> ResolvedChatTurn:
    """把 API 请求解析为角色 scope 感知的聊天轮次。"""
    messages = (
        [{"role": message.role, "content": message.content} for message in request.messages]
        if request.messages
        else None
    )
    try:
        if developer and developer.developer_mode and developer.session_id:
            return await _developer_chat.begin_turn(
                session_id=developer.session_id,
                text=request.text,
                messages=messages,
                role_name_en=request.role_name_en,
                client_id=developer_client_id,
            )
        return await get_companion_chat_service().begin_turn(
            conversation_id=request.conversation_id,
            text=request.text,
            messages=messages,
            role_name_en=request.role_name_en,
        )
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidChatMode, RoleConfigError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _save_reply(
    turn: ResolvedChatTurn,
    reply: str,
    *,
    allow_memory_write: bool = True,
) -> None:
    """会话模式下把 agent 回复交给编排服务保存（无状态模式为 no-op）。

    注意：工具调用摘要不写入短期记忆（只存对话文本，保持记忆干净）。
    """
    try:
        if turn.developer_session_id:
            await _developer_chat.save_reply(turn, reply)
            return
        await get_companion_chat_service().save_reply(
            turn, reply, allow_memory_write=allow_memory_write
        )
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _build_kwargs(
    request: AgentChatRequest,
    turn: Optional[ResolvedChatTurn] = None,
) -> dict:
    """构建引擎调用参数"""
    kwargs: dict = {}
    if request.temperature is not None:
        kwargs["temperature"] = request.temperature
    if request.max_tokens is not None:
        kwargs["max_tokens"] = request.max_tokens
    if request.system_prompt is not None:
        kwargs["system_prompt"] = request.system_prompt
    if turn and turn.memory_context:
        base_prompt = kwargs.get("system_prompt") or _resolve_system_prompt(_load_agent_config())
        kwargs["system_prompt"] = f"{base_prompt}\n\n{turn.memory_context}".strip()
    if turn and turn.track_key is not None:
        # 角色 + 会话 ID 作为中断追踪键，避免跨角色冲突。
        kwargs["track_key"] = turn.track_key
    if turn:
        # 工具上下文由后端确定；不把生活 namespace、记忆召回或完整历史交给工具。
        kwargs["tool_context"] = {
            "role_name_en": turn.role_name_en,
            "stable_user_id": "local-default",
        }
        if turn.developer_session_id:
            kwargs["tool_context"].update(
                {
                    "developer_session_id": turn.developer_session_id,
                    "client_id": turn.developer_client_id or "local-desktop",
                }
            )
    return kwargs


# ── 路由 ──

@router.get("/status", response_model=AgentStatus)
async def agent_status(
    engine: AgentBase = Depends(get_agent_engine),
):
    """获取 Agent 引擎状态（sidecar 健康度、模型、工具、能力标志）"""
    try:
        healthy = await engine.validate_config()
        info = await engine.get_info() if healthy else {}
        return AgentStatus(
            engine=type(engine).__name__.replace("AgentEngine", "").lower(),
            pi_version=info.get("pi_version", ""),
            provider=info.get("provider", ""),
            model=info.get("model", ""),
            tools=info.get("tools", []),
            sidecar_healthy=healthy,
            capabilities=info.get("capabilities", {}),
        )
    except Exception as e:
        logger.error("获取 Agent 状态失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取 Agent 状态失败: {e}")


@router.get("/tools")
async def list_tools(
    engine: AgentBase = Depends(get_agent_engine),
):
    """获取 agent 已启用的工具列表（Phase 1 为空，Phase 2 起白名单放开）"""
    try:
        info = await engine.get_info()
        return {"tools": info.get("tools", [])}
    except Exception as e:
        logger.error("获取工具列表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取工具列表失败: {e}")


@router.post("/chat", response_model=AgentChatResponse)
async def chat(
    request: AgentChatRequest,
    http_request: Request,
):
    """
    非流式对话 — agent 循环（LLM + 工具调用）跑完后返回完整回复与工具调用摘要。
    """
    try:
        developer = _developer_preflight(request, http_request)
        if developer.consume_message:
            return _developer_json_response(request, developer)
        engine = await get_agent_engine()
        await _ensure_sidecar(engine)
        turn = await _resolve_turn(
            request,
            developer,
            http_request.headers.get("X-Companion-Client-Id", "local-desktop"),
        )
        result = await engine.process_text(turn.messages, **_build_kwargs(request, turn))
        await _save_reply(turn, result["reply"], allow_memory_write=not result["tool_calls"])

        info = await engine.get_info()
        logger.info("Agent 对话成功: messages=%d, reply_len=%d, tools=%d",
                    len(turn.messages), len(result["reply"]), len(result["tool_calls"]))

        return AgentChatResponse(
            reply=result["reply"],
            tool_calls=[ToolCallInfo(**tc) if isinstance(tc, dict) else tc
                        for tc in result["tool_calls"]],
            model=info.get("model", ""),
            engine="pi_sidecar",
            conversation_id=request.conversation_id,
            role_name_en=turn.role_name_en,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Agent 对话失败: %s", e)
        raise HTTPException(status_code=500, detail=f"Agent 对话失败: {e}")


@router.post("/chat/stream")
async def chat_stream(
    request: AgentChatRequest,
    http_request: Request,
):
    """
    流式对话 — SSE (text/event-stream) 逐 chunk 返回。

    SSE 格式:
        文本增量: `data: {"content": "...", "engine": "pi_sidecar"}`
        工具事件: `data: {"tool": {"name": ..., "phase": "start"|"end"}}`（附加 key）
        结束标志: `data: [DONE]`
    会话模式下完整回复在流结束后自动写回会话存储（中断时保留已生成部分）。
    """
    try:
        developer = _developer_preflight(request, http_request)
        if developer.consume_message:
            return _developer_stream_response(developer)
        engine = await get_agent_engine()
        await _ensure_sidecar(engine)
        turn = await _resolve_turn(
            request,
            developer,
            http_request.headers.get("X-Companion-Client-Id", "local-desktop"),
        )
        kwargs = _build_kwargs(request, turn)

        async def event_stream():
            full_reply = []
            saw_tool = False
            try:
                async for event in engine.process_text_stream(turn.messages, **kwargs):
                    etype = event.get("type")
                    if etype == "delta":
                        full_reply.append(event["content"])
                        yield f"data: {json.dumps({'content': event['content'], 'engine': 'pi_sidecar'}, ensure_ascii=False)}\n\n"
                    elif etype == "thinking" and request.include_thinking:
                        yield f"data: {json.dumps({'thinking': event['content']}, ensure_ascii=False)}\n\n"
                    elif etype == "tool":
                        saw_tool = True
                        payload = {"tool": {"name": event.get("name"), "phase": event.get("phase")}}
                        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    elif etype == "error":
                        yield f"data: {json.dumps({'error': event.get('message', '未知错误')}, ensure_ascii=False)}\n\n"
                    # done 事件不单独输出，统一以 [DONE] 收尾

                await _save_reply(turn, "".join(full_reply), allow_memory_write=not saw_tool)
                yield "data: [DONE]\n\n"
                logger.info("Agent 流式对话完成: messages=%d, reply_len=%d",
                            len(turn.messages), sum(len(c) for c in full_reply))
            except Exception as e:
                logger.error("Agent 流式对话中断: %s", e)
                # 中断时已生成的部分回复也写回会话，保持上下文连贯
                await _save_reply(turn, "".join(full_reply), allow_memory_write=False)
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            content=event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Engine-Type": "pi_sidecar",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Agent 流式对话启动失败: %s", e)
        raise HTTPException(status_code=500, detail=f"Agent 流式对话失败: {e}")


@router.post("/chat/stream/sentences")
async def chat_stream_sentences(
    request: AgentChatRequest,
    http_request: Request,
):
    """
    句子级流式对话 — NDJSON (application/x-ndjson)。

    agent 文本增量经增量分句器凑句，每句立即 TTS 合成（串行保序），
    文本与音频成对到达，前端可边收边播（对齐 /api/tts/stream/sentences 契约）。

    每行一个 JSON 对象，type 字段区分:
        {"type": "sentence", "text": 句子, "audio": base64, "duration_ms": 时长,
         "audio_format": "pcm"|"mp3"|...}   — TTS 可用时
        {"type": "sentence", "text": 句子}   — TTS 禁用/不可用时的纯文本退化
        {"type": "tool", "name": ..., "phase": "start"|"end"}
        {"type": "error", "message": ...}
        {"type": "done"}

    首句阈值放小（见 app/utils/sentence.py），让桌宠尽快开口。
    会话模式下完整回复在流结束后写回会话存储。
    """
    from app.api.tts.routes import _tts_enabled, get_tts_engine

    try:
        developer = _developer_preflight(request, http_request)
        if developer.consume_message:
            return _developer_stream_response(developer, sentences=True)
        engine = await get_agent_engine()
        await _ensure_sidecar(engine)
        turn = await _resolve_turn(
            request,
            developer,
            http_request.headers.get("X-Companion-Client-Id", "local-desktop"),
        )
        kwargs = _build_kwargs(request, turn)

        # TTS 引擎（禁用或初始化失败时退化为纯文本行）
        tts = None
        if _tts_enabled:
            try:
                tts = await get_tts_engine()
            except HTTPException as e:
                logger.warning("TTS 引擎不可用，句子级流式退化为纯文本: %s", e.detail)

        async def synthesize_sentence(sentence: str):
            """单句 TTS 合成 → NDJSON 行（bytes 可迭代）。失败退化为纯文本行。"""
            if tts is None:
                yield _ndjson_line({"type": "sentence", "text": sentence})
                return
            try:
                if tts.supports_sentence_stream:
                    # 插件引擎：透传其 NDJSON 行（已含 text/audio/duration_ms），补 type。
                    # chunk 是任意字节块，一行大 JSON（含 base64 音频）会跨多个 chunk，
                    # 必须按 \n 缓冲后再解析。
                    buffer = b""
                    async for chunk in tts.stream_sentences(text=sentence):
                        buffer += chunk
                        while b"\n" in buffer:
                            raw, buffer = buffer.split(b"\n", 1)
                            if not raw.strip():
                                continue
                            item = json.loads(raw)
                            item.setdefault("type", "sentence")
                            item.setdefault("audio_format", "pcm")
                            yield _ndjson_line(item)
                    if buffer.strip():
                        item = json.loads(buffer)
                        item.setdefault("type", "sentence")
                        item.setdefault("audio_format", "pcm")
                        yield _ndjson_line(item)
                else:
                    # 非句子级引擎（如 EdgeTTS）：整句合成
                    import base64
                    audio = await tts.synthesize(sentence)
                    fmt = "mp3" if tts.media_type == "audio/mpeg" else "wav"
                    yield _ndjson_line({
                        "type": "sentence", "text": sentence,
                        "audio": base64.b64encode(audio).decode("ascii"),
                        "audio_format": fmt,
                    })
            except Exception as e:
                logger.warning("句子 TTS 合成失败，退化为纯文本: %s", e)
                yield _ndjson_line({"type": "sentence", "text": sentence})

        async def ndjson_stream():
            full_reply = []
            saw_tool = False
            splitter = SentenceSplitter()
            try:
                async for event in engine.process_text_stream(turn.messages, **kwargs):
                    etype = event.get("type")
                    if etype == "delta":
                        full_reply.append(event["content"])
                        for sentence in splitter.feed(event["content"]):
                            async for line in synthesize_sentence(sentence):
                                yield line
                    elif etype == "tool":
                        saw_tool = True
                        yield _ndjson_line({
                            "type": "tool",
                            "name": event.get("name"),
                            "phase": event.get("phase"),
                        })
                    elif etype == "error":
                        yield _ndjson_line({"type": "error", "message": event.get("message", "未知错误")})

                # 收尾：残留文本
                rest = splitter.flush()
                if rest:
                    async for line in synthesize_sentence(rest):
                        yield line

                await _save_reply(turn, "".join(full_reply), allow_memory_write=not saw_tool)
                yield _ndjson_line({"type": "done"})
                logger.info("Agent 句子级流式完成: messages=%d, reply_len=%d",
                            len(turn.messages), sum(len(c) for c in full_reply))
            except Exception as e:
                logger.error("Agent 句子级流式中断: %s", e)
                await _save_reply(turn, "".join(full_reply), allow_memory_write=False)
                yield _ndjson_line({"type": "error", "message": str(e)})
                yield _ndjson_line({"type": "done"})

        return StreamingResponse(
            content=ndjson_stream(),
            media_type="application/x-ndjson",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Engine-Type": "pi_sidecar",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Agent 句子级流式启动失败: %s", e)
        raise HTTPException(status_code=500, detail=f"Agent 句子级流式失败: {e}")


def _ndjson_line(obj: dict) -> bytes:
    """编码一行 NDJSON"""
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


@router.post("/restart")
async def restart_sidecar():
    """重启 agent sidecar 插件（配置变更后 / sidecar 异常时手动触发）"""
    from app.main import restart_agent_plugin

    try:
        ok = restart_agent_plugin()
        if not ok:
            raise HTTPException(status_code=500, detail="sidecar 重启失败，见后端日志")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("sidecar 重启失败: %s", e)
        raise HTTPException(status_code=500, detail=f"sidecar 重启失败: {e}")


@router.post("/abort")
async def abort(
    request: AbortRequest,
    engine: AgentBase = Depends(get_agent_engine),
):
    """中断进行中的对话（传 conversation_id 中断指定会话，不传中断全部）"""
    try:
        track_key = None
        if request.conversation_id:
            try:
                role = get_companion_chat_service().role_registry.resolve(request.role_name_en)
            except RoleConfigError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            track_key = f"{role.name_en}:{request.conversation_id}"
        ok = await engine.abort(track_key)
        return {"ok": ok}
    except Exception as e:
        logger.error("Agent 中断失败: %s", e)
        raise HTTPException(status_code=500, detail=f"Agent 中断失败: {e}")

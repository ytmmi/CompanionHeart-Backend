"""会话（多对话上下文）API 路由

端点:
    POST   /api/conversations        — 开启新对话
    GET    /api/conversations        — 历史对话列表（按更新时间倒序）
    GET    /api/conversations/{id}   — 获取某对话的完整消息记录
    PATCH  /api/conversations/{id}   — 重命名对话
    DELETE /api/conversations/{id}   — 删除对话

存储由 app.memory.short_term.ConversationStore 提供（JSON 文件持久化）。
对话消息的写入发生在 /api/agent/chat 携带 conversation_id 调用时（后端自动
追加用户消息与模型回复），本模块只做会话生命周期管理。
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.memory.roles import RoleConfigError
from app.memory.short_term import get_conversation_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])


# ── 请求/响应模型 ──

class ConversationCreateRequest(BaseModel):
    """新对话请求"""
    title: Optional[str] = Field(None, max_length=100, description="标题（缺省自动取首条用户消息）")
    role_name_en: Optional[str] = Field(
        None,
        description="角色英文名；缺省使用 app/configs/roles 中的默认角色",
    )


class ConversationRenameRequest(BaseModel):
    """重命名请求"""
    title: str = Field(..., min_length=1, max_length=100, description="新标题")


class ConversationMetaResponse(BaseModel):
    """会话元信息（列表条目）"""
    id: str = Field(..., description="会话 ID")
    role_name_en: str = Field(..., description="会话所属角色英文名")
    title: str = Field(..., description="标题")
    created_at: str = Field(..., description="创建时间（ISO 8601 UTC）")
    updated_at: str = Field(..., description="最后更新时间（ISO 8601 UTC）")
    message_count: int = Field(0, description="消息条数")
    preview: str = Field("", description="最后一条消息预览")


class ConversationListResponse(BaseModel):
    """历史对话列表响应"""
    conversations: list[ConversationMetaResponse] = Field(..., description="按更新时间倒序")


class MessageResponse(BaseModel):
    """会话内单条消息"""
    role: str = Field(..., description="角色: user / assistant")
    content: str = Field(..., description="消息内容")
    timestamp: str = Field("", description="消息时间（ISO 8601 UTC）")


class ConversationDetailResponse(BaseModel):
    """完整会话响应"""
    id: str
    role_name_en: str
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageResponse]


# ── 路由 ──

def _store_for(role_name_en: Optional[str] = None):
    try:
        return get_conversation_store(role_name_en)
    except RoleConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("", response_model=ConversationMetaResponse)
async def create_conversation(request: ConversationCreateRequest):
    """开启新对话，返回新会话元信息（前端保存 id 用于后续 chat 调用）"""
    store = _store_for(request.role_name_en)
    conv = store.create(title=request.title)
    return ConversationMetaResponse(
        id=conv.id,
        role_name_en=conv.role_name_en,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
        preview="",
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(role_name_en: Optional[str] = None):
    """历史对话列表（元信息，按更新时间倒序，不含消息内容）"""
    store = _store_for(role_name_en)
    metas = store.list()
    return ConversationListResponse(
        conversations=[
            ConversationMetaResponse(
                id=m.id,
                role_name_en=m.role_name_en,
                title=m.title,
                created_at=m.created_at,
                updated_at=m.updated_at,
                message_count=m.message_count,
                preview=m.preview,
            )
            for m in metas
        ]
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(conversation_id: str, role_name_en: Optional[str] = None):
    """获取某对话的完整消息记录（进入历史对话时加载）"""
    store = _store_for(role_name_en)
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"对话不存在: {conversation_id}")
    return ConversationDetailResponse(
        id=conv.id,
        role_name_en=conv.role_name_en,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageResponse(
                role=m.get("role", ""),
                content=m.get("content", ""),
                timestamp=m.get("timestamp", ""),
            )
            for m in conv.messages
        ],
    )


@router.patch("/{conversation_id}", response_model=ConversationMetaResponse)
async def rename_conversation(
    conversation_id: str,
    request: ConversationRenameRequest,
    role_name_en: Optional[str] = None,
):
    """重命名对话"""
    store = _store_for(role_name_en)
    if not store.rename(conversation_id, request.title):
        raise HTTPException(status_code=404, detail=f"对话不存在: {conversation_id}")
    conv = store.get(conversation_id)
    return ConversationMetaResponse(
        id=conv.id,
        role_name_en=conv.role_name_en,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=len(conv.messages),
        preview=conv.messages[-1]["content"][:50] if conv.messages else "",
    )


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, role_name_en: Optional[str] = None):
    """删除对话"""
    store = _store_for(role_name_en)
    if not store.delete(conversation_id):
        raise HTTPException(status_code=404, detail=f"对话不存在: {conversation_id}")
    return {"deleted": conversation_id, "role_name_en": store.role_name_en}

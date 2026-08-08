"""开发者对话编排：只读写 developer_memory，不接触生活记忆。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.agent.companion import InvalidChatMode, ResolvedChatTurn
from app.memory.developer import DeveloperMemoryStore
from app.memory.roles import get_role_registry


class DeveloperChatService:
    def __init__(self, *, data_root: Path | None = None) -> None:
        self.data_root = data_root

    def store(self, session_id: str) -> DeveloperMemoryStore:
        return DeveloperMemoryStore(session_id, data_root=self.data_root)

    async def begin_turn(
        self,
        *,
        session_id: str,
        text: str | None,
        messages: Iterable[dict] | None,
        role_name_en: str | None,
        client_id: str,
    ) -> ResolvedChatTurn:
        role = get_role_registry().resolve(role_name_en)
        user_text = text or next(
            (
                str(message.get("content", ""))
                for message in reversed(list(messages or []))
                if message.get("role") == "user"
            ),
            "",
        )
        if not user_text.strip():
            raise InvalidChatMode("开发者模式必须提供用户文本")
        store = self.store(session_id)
        store.append(role.name_en, "user", user_text)
        return ResolvedChatTurn(
            messages=store.context_messages(),
            role_name_en=role.name_en,
            user_text=user_text,
            developer_session_id=session_id,
            developer_client_id=client_id,
            memory_context=(
                '<developer_mode marker="dve:ytmmi">\n'
                "当前是已认证开发/调试会话。不得把本会话写入普通生活或工作长期记忆。\n"
                "</developer_mode>"
            ),
        )

    async def save_reply(self, turn: ResolvedChatTurn, reply: str) -> None:
        if turn.developer_session_id and reply.strip():
            self.store(turn.developer_session_id).append(
                turn.role_name_en, "assistant", reply
            )

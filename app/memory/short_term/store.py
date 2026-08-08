"""ConversationStore — 多对话上下文的 JSON 文件存储

存储布局（app/memory/temp_memory/<role_name_en>/short_term/）:
    index.json          — 会话索引（元信息列表，按 updated_at 倒序读取）
    {conversation_id}.json — 单个会话的完整消息记录

设计:
    - 每个会话一个 JSON 文件，索引单独存放，列表页无需读取全部消息
    - 写入采用「临时文件 + 原子替换」防止进程中断产生半截文件
    - 单进程内存锁（threading.Lock）保证并发请求下索引读写一致；
      FastAPI 单进程部署下足够，多进程部署需换外部存储
    - 上下文组装：取最近 MAX_CONTEXT_MESSAGES 条（条数截断，后续可
      在此内部升级为 token 预算截断/摘要压缩，不影响调用方）
"""

# 惰性注解求值：类体内的 list 方法会遮蔽内置 list，注解需延迟解析
from __future__ import annotations

import json
import logging
import shutil
import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.memory.paths import resolve_role_temp_path, role_key
from app.memory.roles import get_role_registry

logger = logging.getLogger(__name__)

# ── 配置 ──

# 组装 LLM 上下文时携带的最近消息条数上限
MAX_CONTEXT_MESSAGES = 10
# 新会话默认标题取首条用户消息的前 N 个字符
TITLE_MAX_CHARS = 20
# 列表预览取最后一条消息的前 N 个字符
PREVIEW_MAX_CHARS = 50


def _utc_now() -> str:
    """ISO 8601 UTC 时间戳"""
    return datetime.now(timezone.utc).isoformat()


# ── 数据模型 ──

@dataclass
class ConversationMeta:
    """会话元信息（索引条目，列表页使用）"""
    id: str
    title: str
    created_at: str
    updated_at: str
    role_name_en: str = ""
    message_count: int = 0
    preview: str = ""  # 最后一条消息的截断预览


@dataclass
class Conversation:
    """完整会话（含消息记录）"""
    id: str
    title: str
    created_at: str
    updated_at: str
    role_name_en: str = ""
    messages: list[dict] = field(default_factory=list)  # {role, content, timestamp}


# ── 存储实现 ──

class ConversationStore:
    """多对话 JSON 文件存储（线程安全，进程内单例使用）"""

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        *,
        role_name_en: str = "",
    ):
        self.role_name_en = role_name_en
        self._data_dir = data_dir or Path(__file__).parent / "data"
        self._index_path = self._data_dir / "index.json"
        self._lock = threading.Lock()
        self._data_dir.mkdir(parents=True, exist_ok=True)

    # ── 内部工具 ──

    def _conv_path(self, conversation_id: str) -> Path:
        return self._data_dir / f"{conversation_id}.json"

    @staticmethod
    def _atomic_write(path: Path, data: dict | list) -> None:
        """临时文件 + 原子替换写入，防止半截文件"""
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    def _load_index(self) -> list[dict]:
        if not self._index_path.exists():
            return []
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                index = json.load(f)
            return index if isinstance(index, list) else []
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("会话索引读取失败，返回空列表: %s", e)
            return []

    def _save_index(self, index: list[dict]) -> None:
        self._atomic_write(self._index_path, index)

    def _update_index_entry(self, meta: ConversationMeta) -> None:
        """插入或更新索引条目（调用方需持有锁）"""
        index = self._load_index()
        index = [e for e in index if e.get("id") != meta.id]
        index.append(asdict(meta))
        self._save_index(index)

    @staticmethod
    def _make_preview(messages: list[dict]) -> str:
        if not messages:
            return ""
        content = messages[-1].get("content", "")
        return content[:PREVIEW_MAX_CHARS]

    # ── 公开 API ──

    def create(self, title: Optional[str] = None) -> Conversation:
        """开启新对话"""
        now = _utc_now()
        conv = Conversation(
            id=uuid.uuid4().hex,
            title=title or "新对话",
            created_at=now,
            updated_at=now,
            role_name_en=self.role_name_en,
        )
        with self._lock:
            self._atomic_write(self._conv_path(conv.id), asdict(conv))
            self._update_index_entry(ConversationMeta(
                id=conv.id, title=conv.title,
                created_at=now, updated_at=now,
                role_name_en=conv.role_name_en,
            ))
        logger.info("新对话已创建: %s", conv.id)
        return conv

    def get(self, conversation_id: str) -> Optional[Conversation]:
        """读取完整会话；不存在返回 None"""
        path = self._conv_path(conversation_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Conversation(
                id=data["id"],
                title=data.get("title", "对话"),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                role_name_en=data.get("role_name_en", self.role_name_en),
                messages=data.get("messages", []),
            )
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.error("会话读取失败 %s: %s", conversation_id, e)
            return None

    def list(self) -> list[ConversationMeta]:
        """历史对话列表（按 updated_at 倒序）"""
        with self._lock:
            index = self._load_index()
        metas = [
            ConversationMeta(
                id=e["id"],
                title=e.get("title", "对话"),
                created_at=e.get("created_at", ""),
                updated_at=e.get("updated_at", ""),
                role_name_en=e.get("role_name_en", self.role_name_en),
                message_count=e.get("message_count", 0),
                preview=e.get("preview", ""),
            )
            for e in index
            if "id" in e
        ]
        metas.sort(key=lambda m: m.updated_at, reverse=True)
        return metas

    def append_message(
        self, conversation_id: str, role: str, content: str,
    ) -> Optional[Conversation]:
        """追加一条消息并更新索引；会话不存在返回 None。

        首条用户消息会自动设为标题（会话仍为默认标题时）。
        """
        with self._lock:
            conv = self.get(conversation_id)
            if conv is None:
                return None
            conv.messages.append({
                "role": role,
                "content": content,
                "timestamp": _utc_now(),
            })
            conv.updated_at = _utc_now()
            # 首条用户消息 → 自动标题
            if conv.title == "新对话" and role == "user":
                conv.title = content[:TITLE_MAX_CHARS]
            self._atomic_write(self._conv_path(conv.id), asdict(conv))
            self._update_index_entry(ConversationMeta(
                id=conv.id, title=conv.title,
                created_at=conv.created_at, updated_at=conv.updated_at,
                role_name_en=conv.role_name_en,
                message_count=len(conv.messages),
                preview=self._make_preview(conv.messages),
            ))
        return conv

    def build_context(self, conversation_id: str) -> Optional[list[dict]]:
        """组装 LLM 上下文：最近 MAX_CONTEXT_MESSAGES 条 {role, content}。

        会话不存在返回 None。system 消息不在会话内存储（由 LLM 配置提供）。
        """
        conv = self.get(conversation_id)
        if conv is None:
            return None
        recent = conv.messages[-MAX_CONTEXT_MESSAGES:]
        return [{"role": m["role"], "content": m["content"]} for m in recent]

    def rename(self, conversation_id: str, title: str) -> bool:
        """重命名会话；不存在返回 False"""
        with self._lock:
            conv = self.get(conversation_id)
            if conv is None:
                return False
            conv.title = title
            conv.updated_at = _utc_now()
            self._atomic_write(self._conv_path(conv.id), asdict(conv))
            self._update_index_entry(ConversationMeta(
                id=conv.id, title=conv.title,
                created_at=conv.created_at, updated_at=conv.updated_at,
                role_name_en=conv.role_name_en,
                message_count=len(conv.messages),
                preview=self._make_preview(conv.messages),
            ))
        return True

    def delete(self, conversation_id: str) -> bool:
        """删除会话（文件 + 索引条目）；不存在返回 False"""
        with self._lock:
            path = self._conv_path(conversation_id)
            existed = path.exists()
            if existed:
                path.unlink()
            index = self._load_index()
            new_index = [e for e in index if e.get("id") != conversation_id]
            if len(new_index) != len(index):
                self._save_index(new_index)
                existed = True
        if existed:
            logger.info("对话已删除: %s", conversation_id)
        return existed


# ── 进程内单例 ──

_store: Optional[ConversationStore] = None
_role_stores: dict[str, ConversationStore] = {}
_store_lock = threading.Lock()


def _migrate_legacy_data(target_dir: Path, role_name_en: str) -> None:
    """把历史原始短期文件迁入 temp_memory，源目录暂保留备份。"""
    legacy_dirs = [
        Path(__file__).parent / "data",
        Path(__file__).parents[1] / "data_memory" / role_name_en / "short_term",
    ]
    copied = 0
    for legacy_dir in legacy_dirs:
        if not legacy_dir.exists():
            continue
        for source in legacy_dir.glob("*.json"):
            target = target_dir / source.name
            if target.exists():
                continue
            temporary = target.with_suffix(target.suffix + ".migrating")
            shutil.copy2(source, temporary)
            temporary.replace(target)
            copied += 1
    if copied:
        logger.info(
            "已将 %d 个旧原始短期文件迁入 temp_memory 角色 %s；源目录保留为备份",
            copied,
            role_name_en,
        )

    # 旧格式没有角色字段；在新目录内补齐，旧目录始终保持原样。
    for path in target_dir.glob("*.json"):
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            changed = False
            if isinstance(data, dict):
                if data.get("role_name_en") != role_name_en:
                    data["role_name_en"] = role_name_en
                    changed = True
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("role_name_en") != role_name_en:
                        item["role_name_en"] = role_name_en
                        changed = True
            if changed:
                ConversationStore._atomic_write(path, data)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("迁移会话角色字段失败 %s: %s", path, exc)


def get_conversation_store(role_name_en: Optional[str] = None) -> ConversationStore:
    """获取角色隔离的 ConversationStore；缺省使用角色配置中的默认角色。"""
    global _store

    registry = get_role_registry()
    role = registry.resolve(role_name_en)
    key = role_key(role.name_en)
    store = _role_stores.get(key)
    if store is not None:
        return store

    with _store_lock:
        store = _role_stores.get(key)
        if store is None:
            data_dir = resolve_role_temp_path(
                role.name_en,
                "short_term",
                create=True,
            )
            if registry.default_role and key == role_key(registry.default_role.name_en):
                _migrate_legacy_data(data_dir, role.name_en)
            store = ConversationStore(data_dir, role_name_en=role.name_en)
            _role_stores[key] = store
            if registry.default_role and key == role_key(registry.default_role.name_en):
                _store = store
    return store

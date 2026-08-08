"""在 LLM、日志和记忆之前消费开发者认证消息。"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum


_AUTH_RE = re.compile(r"^dve_([a-z][a-z0-9_-]{1,63})_([^\s]{1,256})$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DeveloperAuthAction(StrEnum):
    NORMAL = "normal"
    ACTIVE = "active"
    ENTERED = "entered"
    EXITED = "exited"
    DISABLED = "disabled"
    DENIED = "denied"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class DeveloperSession:
    session_id: str
    developer_name: str
    client_fingerprint: str
    created_at: datetime
    last_seen_at: datetime


@dataclass(frozen=True)
class DeveloperAuthOutcome:
    action: DeveloperAuthAction
    consume_message: bool
    developer_mode: bool
    message: str = ""
    session_id: str | None = None


class DeveloperAuthInterceptor:
    DEVELOPER_NAME = "ytmmi"
    DISPLAY_NAME = "云兔mmi"
    IDLE_TIMEOUT = timedelta(minutes=30)
    FAILURE_WINDOW = timedelta(minutes=1)
    MAX_FAILURES = 5
    BLOCK_DURATION = timedelta(minutes=5)

    def __init__(
        self,
        *,
        key_provider: Callable[[], str | None] | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        # key_provider 每次认证才读取；密钥不保存在对象、session 或异常中。
        self._key_provider = key_provider or (
            lambda: os.environ.get("COMPANIONHEART_DEVELOPER_KEY")
        )
        self._clock = clock
        self._sessions: dict[str, DeveloperSession] = {}
        self._failures: dict[str, deque[datetime]] = defaultdict(deque)
        self._blocked_until: dict[str, datetime] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _fingerprint(client_id: str) -> str:
        return hashlib.sha256(client_id.encode("utf-8")).hexdigest()

    def _active_session(
        self, session_id: str | None, client_fingerprint: str, now: datetime
    ) -> DeveloperSession | None:
        if not session_id:
            return None
        session = self._sessions.get(session_id)
        if session is None or session.client_fingerprint != client_fingerprint:
            return None
        if now - session.last_seen_at >= self.IDLE_TIMEOUT:
            self._sessions.pop(session_id, None)
            return None
        refreshed = DeveloperSession(
            session_id=session.session_id,
            developer_name=session.developer_name,
            client_fingerprint=session.client_fingerprint,
            created_at=session.created_at,
            last_seen_at=now,
        )
        self._sessions[session_id] = refreshed
        return refreshed

    def _is_blocked(self, fingerprint: str, now: datetime) -> bool:
        until = self._blocked_until.get(fingerprint)
        if until is None:
            return False
        if now >= until:
            self._blocked_until.pop(fingerprint, None)
            self._failures.pop(fingerprint, None)
            return False
        return True

    def _record_failure(self, fingerprint: str, now: datetime) -> bool:
        failures = self._failures[fingerprint]
        threshold = now - self.FAILURE_WINDOW
        while failures and failures[0] < threshold:
            failures.popleft()
        failures.append(now)
        if len(failures) >= self.MAX_FAILURES:
            self._blocked_until[fingerprint] = now + self.BLOCK_DURATION
            failures.clear()
            return True
        return False

    def inspect(
        self,
        text: str,
        *,
        client_id: str,
        session_id: str | None = None,
    ) -> DeveloperAuthOutcome:
        """检查单条用户消息；认证/退出消息由此消费，调用方不得继续处理。"""
        now = self._clock()
        fingerprint = self._fingerprint(client_id)
        normalized = text.strip()
        with self._lock:
            active = self._active_session(session_id, fingerprint, now)
            if normalized == "dve_exit":
                if active is not None:
                    self._sessions.pop(active.session_id, None)
                return DeveloperAuthOutcome(
                    action=DeveloperAuthAction.EXITED,
                    consume_message=True,
                    developer_mode=False,
                    message="已退出开发者模式。",
                )

            match = _AUTH_RE.fullmatch(normalized)
            if match:
                if self._is_blocked(fingerprint, now):
                    return DeveloperAuthOutcome(
                        action=DeveloperAuthAction.RATE_LIMITED,
                        consume_message=True,
                        developer_mode=False,
                        message="开发者认证尝试过多，请稍后再试。",
                    )
                configured_key = self._key_provider()
                if not configured_key:
                    return DeveloperAuthOutcome(
                        action=DeveloperAuthAction.DISABLED,
                        consume_message=True,
                        developer_mode=False,
                        message="开发者模式尚未配置密钥，当前保持禁用。",
                    )
                developer_name, candidate_key = match.groups()
                valid = developer_name == self.DEVELOPER_NAME and hmac.compare_digest(
                    candidate_key.encode("utf-8"), configured_key.encode("utf-8")
                )
                # 尽快解除局部引用；任何返回值、日志和 session 都不含 candidate/configured。
                candidate_key = ""
                configured_key = ""
                if not valid:
                    limited = self._record_failure(fingerprint, now)
                    return DeveloperAuthOutcome(
                        action=(
                            DeveloperAuthAction.RATE_LIMITED
                            if limited
                            else DeveloperAuthAction.DENIED
                        ),
                        consume_message=True,
                        developer_mode=False,
                        message=(
                            "开发者认证尝试过多，请稍后再试。"
                            if limited
                            else "开发者认证失败。"
                        ),
                    )
                new_session = DeveloperSession(
                    session_id=uuid.uuid4().hex,
                    developer_name=self.DEVELOPER_NAME,
                    client_fingerprint=fingerprint,
                    created_at=now,
                    last_seen_at=now,
                )
                self._sessions[new_session.session_id] = new_session
                self._failures.pop(fingerprint, None)
                self._blocked_until.pop(fingerprint, None)
                return DeveloperAuthOutcome(
                    action=DeveloperAuthAction.ENTERED,
                    consume_message=True,
                    developer_mode=True,
                    session_id=new_session.session_id,
                    message=f"已进入 {self.DISPLAY_NAME} 的开发者模式。",
                )

            if active is not None:
                return DeveloperAuthOutcome(
                    action=DeveloperAuthAction.ACTIVE,
                    consume_message=False,
                    developer_mode=True,
                    session_id=active.session_id,
                )
            return DeveloperAuthOutcome(
                action=DeveloperAuthAction.NORMAL,
                consume_message=False,
                developer_mode=False,
            )

    def session(self, session_id: str) -> DeveloperSession | None:
        """仅供受控后端组件查询；不会导出认证密钥。"""
        with self._lock:
            return self._sessions.get(session_id)

    def validate_session(
        self, session_id: str | None, *, client_id: str
    ) -> DeveloperSession | None:
        """验证并刷新会话；供开发 API 网关使用，不接受开发者名字或密钥。"""
        with self._lock:
            return self._active_session(
                session_id, self._fingerprint(client_id), self._clock()
            )

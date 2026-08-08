"""按角色和用户 scope 隔离的 WorkCoordinator 注册表。"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from app.agent.work_sidecar import WorkAgentClient, WorkAgentGateway
from app.memory.roles import get_role_registry
from app.memory.work import WorkMemoryScope

from .coordinator import WorkCoordinator
from .coordinator import CompletionListener


_USER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@+-]{0,255}$")


def validate_stable_user_id(value: str) -> str:
    if not isinstance(value, str) or not _USER_ID_RE.fullmatch(value):
        raise ValueError("stable user id 不合法")
    return value


class WorkCoordinatorRegistry:
    def __init__(
        self,
        *,
        namespace_secret: str | None = None,
        gateway_factory: Callable[[], WorkAgentGateway] | None = None,
        work_root: Path | None = None,
        completion_listeners: Iterable[CompletionListener] = (),
    ) -> None:
        self.namespace_secret = namespace_secret or os.environ.get(
            "WORK_MEMORY_NAMESPACE_SECRET", "companionheart-local-work-dev"
        )
        self.gateway_factory = gateway_factory or WorkAgentClient
        self.work_root = work_root
        self.completion_listeners = tuple(completion_listeners)
        self._coordinators: dict[str, WorkCoordinator] = {}

    def scope_for(self, role_name_en: str | None, stable_user_id: str) -> WorkMemoryScope:
        role = get_role_registry().resolve(role_name_en)
        return WorkMemoryScope.from_identity(
            role.name_en,
            validate_stable_user_id(stable_user_id),
            namespace_secret=self.namespace_secret,
        )

    def get(self, role_name_en: str | None, stable_user_id: str) -> WorkCoordinator:
        scope = self.scope_for(role_name_en, stable_user_id)
        coordinator = self._coordinators.get(scope.key)
        if coordinator is None:
            coordinator = WorkCoordinator(
                scope,
                self.gateway_factory(),
                work_root=self.work_root,
            )
            for listener in self.completion_listeners:
                coordinator.add_completion_listener(listener)
            self._coordinators[scope.key] = coordinator
        return coordinator

"""生活长期记忆身份映射与 Provider 门面。"""

from __future__ import annotations

import hashlib
import hmac

from app.memory.roles import MemoryRoleRegistry, get_role_registry

from .base import LifeMemoryProvider
from .models import (
    DeleteReceipt,
    LifeMemoryCandidate,
    LifeMemoryHit,
    LifeMemoryQuery,
    LifeMemoryRecord,
    LifeMemoryScope,
    ProviderHealth,
)


class LifeMemoryService:
    """只有本服务可以从角色/用户身份构造 Provider scope。"""

    def __init__(
        self,
        provider: LifeMemoryProvider,
        *,
        namespace_secret: str,
        role_registry: MemoryRoleRegistry | None = None,
    ) -> None:
        if not namespace_secret:
            raise ValueError("namespace_secret 不能为空")
        self.provider = provider
        self.namespace_secret = namespace_secret.encode("utf-8")
        self.role_registry = role_registry or get_role_registry()

    def scope_for(
        self,
        role_name_en: str | None,
        stable_user_id: str = "local-default",
    ) -> LifeMemoryScope:
        role = self.role_registry.resolve(role_name_en)
        digest = hmac.new(
            self.namespace_secret,
            stable_user_id.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return LifeMemoryScope(
            role_name_en=role.name_en,
            user_namespace=f"life_{digest}",
        )

    async def remember(
        self,
        scope: LifeMemoryScope,
        candidate: LifeMemoryCandidate,
    ) -> str:
        return await self.provider.upsert(
            scope,
            LifeMemoryRecord(**candidate.model_dump()),
        )

    async def search(
        self,
        scope: LifeMemoryScope,
        query: LifeMemoryQuery,
    ) -> list[LifeMemoryHit]:
        return await self.provider.search(scope, query)

    async def forget_scope(self, scope: LifeMemoryScope) -> DeleteReceipt:
        return await self.provider.delete_scope(scope)

    async def health(self) -> ProviderHealth:
        return await self.provider.health()

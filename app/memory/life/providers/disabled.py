"""关闭长期记忆时的显式 Provider。"""

from __future__ import annotations

from ..base import MemoryProviderUnavailable
from ..models import (
    DeleteReceipt,
    LifeMemoryHit,
    LifeMemoryQuery,
    LifeMemoryRecord,
    LifeMemoryScope,
    MemoryRevision,
    ProviderHealth,
    ProviderStatus,
)


class DisabledLifeMemoryProvider:
    async def upsert(self, scope: LifeMemoryScope, record: LifeMemoryRecord) -> str:
        raise MemoryProviderUnavailable("生活长期记忆未启用")

    async def search(
        self, scope: LifeMemoryScope, query: LifeMemoryQuery,
    ) -> list[LifeMemoryHit]:
        return []

    async def get(
        self, scope: LifeMemoryScope, memory_id: str,
    ) -> LifeMemoryRecord | None:
        return None

    async def revise(
        self, scope: LifeMemoryScope, memory_id: str, revision: MemoryRevision,
    ) -> str:
        raise MemoryProviderUnavailable("生活长期记忆未启用")

    async def delete(
        self, scope: LifeMemoryScope, memory_id: str,
    ) -> DeleteReceipt:
        raise MemoryProviderUnavailable("生活长期记忆未启用")

    async def delete_scope(self, scope: LifeMemoryScope) -> DeleteReceipt:
        raise MemoryProviderUnavailable("生活长期记忆未启用")

    async def status(self, scope: LifeMemoryScope) -> ProviderStatus:
        return ProviderStatus(scope=scope, record_count=0, index_ready=False)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            available=False,
            provider="disabled",
            detail="生活长期记忆未启用",
        )

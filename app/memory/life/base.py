"""生活长期记忆 Provider 协议。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    DeleteReceipt,
    LifeMemoryHit,
    LifeMemoryQuery,
    LifeMemoryRecord,
    LifeMemoryScope,
    MemoryRevision,
    ProviderHealth,
    ProviderStatus,
)


class MemoryProviderUnavailable(RuntimeError):
    """长期记忆 Provider 未启用或当前不可用。"""


@runtime_checkable
class LifeMemoryProvider(Protocol):
    async def upsert(self, scope: LifeMemoryScope, record: LifeMemoryRecord) -> str: ...

    async def search(
        self, scope: LifeMemoryScope, query: LifeMemoryQuery,
    ) -> list[LifeMemoryHit]: ...

    async def get(
        self, scope: LifeMemoryScope, memory_id: str,
    ) -> LifeMemoryRecord | None: ...

    async def revise(
        self, scope: LifeMemoryScope, memory_id: str, revision: MemoryRevision,
    ) -> str: ...

    async def delete(
        self, scope: LifeMemoryScope, memory_id: str,
    ) -> DeleteReceipt: ...

    async def delete_scope(self, scope: LifeMemoryScope) -> DeleteReceipt: ...

    async def status(self, scope: LifeMemoryScope) -> ProviderStatus: ...

    async def health(self) -> ProviderHealth: ...

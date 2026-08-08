"""角色/用户隔离的后端工作记忆。"""

from .models import (
    WorkCommand,
    WorkEvent,
    WorkEventType,
    WorkMemoryKind,
    WorkMemoryRecord,
    WorkMemoryStatus,
    WorkMemoryScope,
    WorkModel,
    WorkResult,
    WorkStatus,
)
from .paths import (
    WORK_MEMORY_ROOT,
    InvalidWorkNamespace,
    UnsafeWorkMemoryPath,
    resolve_work_memory_path,
    resolve_work_scope_root,
    validate_work_namespace,
)
from .short_term import (
    InvalidWorkJob,
    InvalidWorkTransition,
    WorkEventLogCorrupted,
    WorkJobStore,
    validate_job_id,
)
from .long_term import LongTermWorkMemoryStore, WorkLongTermMemoryCorrupted
from .environment import EnvironmentFact, WorkEnvironmentCollector
from .archive import (
    REDACTED,
    WorkArchiveRecord,
    WorkArchiveStore,
    redact_work_payload,
)

__all__ = [
    "InvalidWorkNamespace",
    "UnsafeWorkMemoryPath",
    "WORK_MEMORY_ROOT",
    "WorkMemoryScope",
    "WorkModel",
    "WorkCommand",
    "WorkEvent",
    "WorkEventType",
    "WorkMemoryKind",
    "WorkMemoryRecord",
    "WorkMemoryStatus",
    "WorkResult",
    "WorkStatus",
    "resolve_work_memory_path",
    "resolve_work_scope_root",
    "validate_work_namespace",
    "InvalidWorkJob",
    "InvalidWorkTransition",
    "WorkEventLogCorrupted",
    "WorkJobStore",
    "validate_job_id",
    "LongTermWorkMemoryStore",
    "WorkLongTermMemoryCorrupted",
    "EnvironmentFact",
    "WorkEnvironmentCollector",
    "REDACTED",
    "WorkArchiveRecord",
    "WorkArchiveStore",
    "redact_work_payload",
]

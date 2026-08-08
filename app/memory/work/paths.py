"""工作记忆的数据根和角色/用户物理隔离路径。"""

from __future__ import annotations

import re
from pathlib import Path

from app.memory.paths import validate_role_name


WORK_MEMORY_ROOT = Path(__file__).resolve().parents[1] / "work_memory"
WORK_NAMESPACE_PATTERN = re.compile(r"^work_[A-Fa-f0-9]{64}$")


class InvalidWorkNamespace(ValueError):
    """工作用户 namespace 不满足服务端 HMAC 格式。"""


class UnsafeWorkMemoryPath(ValueError):
    """工作记忆路径越出固定数据根。"""


def validate_work_namespace(work_user_namespace: str) -> str:
    if not isinstance(work_user_namespace, str) or not WORK_NAMESPACE_PATTERN.fullmatch(
        work_user_namespace
    ):
        raise InvalidWorkNamespace("work_user_namespace 必须是 work_ 加 64 位十六进制 HMAC")
    return work_user_namespace.lower()


def resolve_work_scope_root(
    role_name_en: str,
    work_user_namespace: str,
    *,
    work_root: Path | None = None,
    create: bool = False,
) -> Path:
    role = validate_role_name(role_name_en)
    namespace = validate_work_namespace(work_user_namespace)
    root = (work_root or WORK_MEMORY_ROOT).resolve()
    candidate = (root / role / namespace).resolve()
    if root not in candidate.parents or candidate.parent.parent != root:
        raise UnsafeWorkMemoryPath(f"工作记忆 scope 越出固定数据根: {candidate}")
    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def resolve_work_memory_path(
    role_name_en: str,
    work_user_namespace: str,
    *parts: str,
    work_root: Path | None = None,
    create: bool = False,
) -> Path:
    scope_root = resolve_work_scope_root(
        role_name_en,
        work_user_namespace,
        work_root=work_root,
        create=create,
    )
    candidate = scope_root
    for part in parts:
        if not isinstance(part, str) or not part or Path(part).is_absolute():
            raise UnsafeWorkMemoryPath(f"非法工作记忆路径片段: {part!r}")
        if part in {".", ".."} or len(Path(part).parts) != 1:
            raise UnsafeWorkMemoryPath(f"工作记忆路径必须逐级传入安全片段: {part!r}")
        candidate /= part
    resolved = candidate.resolve()
    try:
        resolved.relative_to(scope_root)
    except ValueError as exc:
        raise UnsafeWorkMemoryPath(f"工作记忆路径越出用户 scope: {resolved}") from exc
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved

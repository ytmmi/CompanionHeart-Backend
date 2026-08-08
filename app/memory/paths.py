"""记忆数据路径与角色目录安全边界。"""

from __future__ import annotations

import re
from pathlib import Path


MEMORY_DATA_ROOT = Path(__file__).resolve().parent / "data_memory"
# 未标准化的短期原始记忆（会话、临时摄入片段）与标准记忆分离。
TEMP_MEMORY_ROOT = Path(__file__).resolve().parent / "temp_memory"
ROLE_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


class InvalidRoleName(ValueError):
    """角色英文名不满足目录标识约束。"""


class UnsafeMemoryPath(ValueError):
    """目标路径逃逸出允许的角色记忆目录。"""


def validate_role_name(role_name_en: str) -> str:
    """校验并返回角色英文名，不自动音译或改写大小写。"""
    if not isinstance(role_name_en, str) or not ROLE_NAME_PATTERN.fullmatch(role_name_en):
        raise InvalidRoleName(
            "role_name_en 必须以 ASCII 字母开头，且只能包含字母、数字、_、-（最长 64）"
        )
    return role_name_en


def role_key(role_name_en: str) -> str:
    """返回用于大小写不敏感比较和缓存的角色键。"""
    return validate_role_name(role_name_en).casefold()


def resolve_role_root(
    role_name_en: str,
    *,
    data_root: Path | None = None,
    create: bool = False,
) -> Path:
    """解析角色一级目录，并保证它位于唯一记忆数据根内。"""
    validated = validate_role_name(role_name_en)
    root = (data_root or MEMORY_DATA_ROOT).resolve()
    candidate = (root / validated).resolve()
    if candidate.parent != root:
        raise UnsafeMemoryPath(f"角色目录逃逸出记忆数据根: {candidate}")
    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def resolve_role_memory_path(
    role_name_en: str,
    *parts: str,
    data_root: Path | None = None,
    create: bool = False,
) -> Path:
    """解析角色内路径，拒绝绝对路径、父目录和符号链接逃逸。"""
    role_root = resolve_role_root(role_name_en, data_root=data_root, create=create)
    candidate = role_root
    for part in parts:
        if not isinstance(part, str) or not part or Path(part).is_absolute():
            raise UnsafeMemoryPath(f"非法记忆路径片段: {part!r}")
        if part in {".", ".."} or len(Path(part).parts) != 1:
            raise UnsafeMemoryPath(f"记忆路径必须逐级传入安全片段: {part!r}")
        candidate /= part

    resolved = candidate.resolve()
    try:
        resolved.relative_to(role_root)
    except ValueError as exc:
        raise UnsafeMemoryPath(f"记忆路径逃逸出角色目录: {resolved}") from exc
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_role_temp_path(
    role_name_en: str,
    *parts: str,
    temp_root: Path | None = None,
    create: bool = False,
) -> Path:
    """解析角色的未标准化短期记忆路径。"""
    return resolve_role_memory_path(
        role_name_en,
        *parts,
        data_root=(temp_root or TEMP_MEMORY_ROOT),
        create=create,
    )

"""记忆模块：角色隔离的短期、生活长期与工作记忆基础设施。"""

from .paths import (
    MEMORY_DATA_ROOT,
    TEMP_MEMORY_ROOT,
    InvalidRoleName,
    UnsafeMemoryPath,
    resolve_role_memory_path,
    resolve_role_root,
    resolve_role_temp_path,
    role_key,
    validate_role_name,
)
from .roles import (
    ROLE_CONFIG_DIR,
    DuplicateMemoryRole,
    Live2DModelConfig,
    MemoryRole,
    MemoryRoleRegistry,
    RoleConfigError,
    RolePersonaConfig,
    RoleTTSConfig,
    UnknownMemoryRole,
    get_role_registry,
    load_role_registry,
)

__all__ = [
    "MEMORY_DATA_ROOT",
    "TEMP_MEMORY_ROOT",
    "InvalidRoleName",
    "UnsafeMemoryPath",
    "resolve_role_memory_path",
    "resolve_role_root",
    "resolve_role_temp_path",
    "role_key",
    "validate_role_name",
    "DuplicateMemoryRole",
    "ROLE_CONFIG_DIR",
    "Live2DModelConfig",
    "MemoryRole",
    "MemoryRoleRegistry",
    "RoleConfigError",
    "RolePersonaConfig",
    "RoleTTSConfig",
    "UnknownMemoryRole",
    "get_role_registry",
    "load_role_registry",
]

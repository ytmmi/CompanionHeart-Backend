"""服务端角色配置、注册和默认角色解析。"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any, Iterable

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .paths import role_key, validate_role_name


ROLE_CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs" / "roles"


class RoleConfigError(ValueError):
    """角色配置文件无效。"""


class UnknownMemoryRole(RoleConfigError):
    """请求使用了未注册的记忆角色。"""


class DuplicateMemoryRole(RoleConfigError):
    """角色英文名发生大小写不敏感冲突。"""


class Live2DModelConfig(BaseModel):
    """一个角色可选用的 Live2D 模型引用。"""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    default: bool = False
    name: str = ""


class RoleTTSConfig(BaseModel):
    """角色的 TTS 引擎与音色选择；密钥仍由模块配置提供。"""

    model_config = ConfigDict(extra="allow")

    mode: str = ""
    voice: str = ""
    character_name: str = ""
    emotion: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)


class RolePersonaConfig(BaseModel):
    """角色人格和展示设定。"""

    model_config = ConfigDict(extra="allow")

    system_prompt: str = ""
    description: str = ""
    greeting: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)


class MemoryRole(BaseModel):
    """一个完整的陪伴角色配置。"""

    model_config = ConfigDict(extra="allow", frozen=True)

    name: str = Field(..., min_length=1, description="角色显示名")
    name_en: str = Field(..., min_length=1, description="稳定英文标识和记忆目录名")
    enabled: bool = True
    default: bool = False
    live2d_models: tuple[Live2DModelConfig, ...] = ()
    tts: RoleTTSConfig = Field(default_factory=RoleTTSConfig)
    persona: RolePersonaConfig = Field(default_factory=RolePersonaConfig)
    settings: dict[str, Any] = Field(default_factory=dict)
    source_path: str = Field("", exclude=True)

    @model_validator(mode="after")
    def validate_identity_and_models(self) -> "MemoryRole":
        validate_role_name(self.name_en)
        defaults = [model for model in self.live2d_models if model.default]
        if len(defaults) > 1:
            raise ValueError("同一角色最多只能有一个默认 Live2D 模型")
        ids = [model.id.casefold() for model in self.live2d_models]
        if len(ids) != len(set(ids)):
            raise ValueError("同一角色的 Live2D 模型 id 必须大小写不敏感唯一")
        return self


class MemoryRoleRegistry:
    """服务端角色白名单；不会从显示名或 TTS 音色自动推导角色。"""

    def __init__(
        self,
        roles: Iterable[MemoryRole | str] = (),
        *,
        default_role_name_en: str | None = None,
    ) -> None:
        self._roles: dict[str, MemoryRole] = {}
        configured_defaults: list[str] = []
        for item in roles:
            role = item if isinstance(item, MemoryRole) else MemoryRole(name=item, name_en=item)
            key = role_key(role.name_en)
            if key in self._roles:
                raise DuplicateMemoryRole(f"角色英文名大小写冲突: {role.name_en}")
            self._roles[key] = role
            if role.default:
                configured_defaults.append(key)

        if len(configured_defaults) > 1:
            names = [self._roles[key].name_en for key in configured_defaults]
            raise DuplicateMemoryRole(f"只能配置一个默认角色: {', '.join(names)}")

        self._default_key: str | None = configured_defaults[0] if configured_defaults else None
        if default_role_name_en:
            explicit_key = role_key(default_role_name_en)
            if explicit_key not in self._roles:
                raise UnknownMemoryRole(f"默认角色未注册: {default_role_name_en}")
            if self._default_key is not None and self._default_key != explicit_key:
                raise DuplicateMemoryRole("显式默认角色与角色文件中的 default 标记冲突")
            self._default_key = explicit_key

    @property
    def default_role(self) -> MemoryRole | None:
        return self._roles.get(self._default_key) if self._default_key else None

    def resolve(self, role_name_en: str | None = None) -> MemoryRole:
        """解析显式角色或默认角色；不存在时拒绝，不做猜测。"""
        key = role_key(role_name_en) if role_name_en else self._default_key
        if key is None or key not in self._roles:
            if role_name_en:
                raise UnknownMemoryRole(f"未注册的角色英文名: {role_name_en}")
            raise UnknownMemoryRole("未配置默认角色英文名，必须显式提供 role_name_en")
        return self._roles[key]

    def list(self) -> list[MemoryRole]:
        return list(self._roles.values())


def load_role_registry(config_dir: Path | None = None) -> MemoryRoleRegistry:
    """扫描 ``app/configs/roles/*.yaml``，每个文件注册一个角色。"""
    directory = (config_dir or ROLE_CONFIG_DIR).resolve()
    if not directory.exists():
        return MemoryRoleRegistry()

    roles: list[MemoryRole] = []
    config_files = sorted((*directory.glob("*.yaml"), *directory.glob("*.yml")))
    for path in config_files:
        if ".example." in path.name:
            continue
        try:
            with path.open("r", encoding="utf-8") as file:
                raw = yaml.safe_load(file) or {}
            role = MemoryRole.model_validate({**raw, "source_path": str(path)})
        except Exception as exc:
            raise RoleConfigError(f"角色配置无效 {path}: {exc}") from exc
        if path.stem.casefold() != role.name_en.casefold():
            raise RoleConfigError(
                f"角色配置文件名必须与 name_en 一致: {path.name} != {role.name_en}.yaml"
            )
        roles.append(role)
    return MemoryRoleRegistry(roles)


_registry: MemoryRoleRegistry | None = None
_registry_lock = threading.Lock()


def get_role_registry(*, refresh: bool = False) -> MemoryRoleRegistry:
    """获取进程内角色注册表；设置服务修改角色文件后可显式刷新。"""
    global _registry
    if refresh or _registry is None:
        with _registry_lock:
            if refresh or _registry is None:
                _registry = load_role_registry()
    return _registry

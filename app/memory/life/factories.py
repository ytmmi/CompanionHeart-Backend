"""生活长期记忆 Provider 工厂。"""

from __future__ import annotations

import os
from pathlib import Path

from .base import LifeMemoryProvider
from .providers import DisabledLifeMemoryProvider, OmniPluginLifeMemoryProvider
from .service import LifeMemoryService


def _load_config() -> dict:
    import yaml

    path = Path(__file__).parents[2] / "configs" / "memory" / "config.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def create_life_memory_provider(mode: str | None = None) -> LifeMemoryProvider:
    config = _load_config()
    if mode is None:
        mode = config.get("mode") if config.get("enabled", False) else "disabled"
    plugin_config = config.get("omni_plugin", {}) or {}
    if mode == "disabled":
        return DisabledLifeMemoryProvider()
    if mode == "omni_plugin":
        return OmniPluginLifeMemoryProvider(
            base_url=plugin_config.get("base_url", "http://localhost:8500"),
            timeout=int(plugin_config.get("timeout", 30)),
        )
    raise ValueError(f"不支持的生活记忆 Provider: {mode}")


def create_life_memory_service() -> LifeMemoryService | None:
    """按后端记忆配置创建协议门面；未启用插件时返回 None。"""
    provider = create_life_memory_provider()
    if isinstance(provider, DisabledLifeMemoryProvider):
        return None
    return LifeMemoryService(
        provider,
        namespace_secret=os.environ.get(
            "MEMORY_NAMESPACE_SECRET", "companionheart-local-memory-dev"
        ),
    )

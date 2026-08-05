"""YAML 读取、路径下钻、扁平化与类型归一化。

写入走 `yaml_patch.set_scalar`（保留注释），这里只负责读与取值。
"""
from __future__ import annotations

from pathlib import Path

import yaml


def read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def dig(d: dict, dotted: str, default=None):
    """按 a.b.c 取值，任一层缺失返回 default"""
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def flatten_keys(d: dict, prefix: str = "") -> dict:
    result = {}
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(flatten_keys(v, full_key))
        else:
            result[full_key] = v
    return result


def coerce_value(value, old_value):
    """
    把前端传来的值按配置里原值的类型归一化。

    前端 input 一律给字符串，直接写进去会把 timeout: 60 变成 timeout: "60"，
    后端读到字符串再做算术就炸了。以文件里的现有值为准做类型对齐。
    """
    if isinstance(old_value, bool):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    if isinstance(old_value, int) and not isinstance(old_value, bool):
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return old_value
    if isinstance(old_value, float):
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return old_value
    if value is None:
        return ""
    return value

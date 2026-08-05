"""扁平 key 的批量读写。

写入优先走 yaml_patch 的行级替换保留注释；key 在文件里不存在时才回退到
「读 → 合并 → 重写」，那条路径会丢注释，因此会在 warnings 里点名。
改插件端口时同步写 custom_plugin/<插件>/plugin.yaml，避免两处端口跑偏。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .backups import backup_module
from .descriptions import KEY_DESCRIPTIONS
from .paths import CONFIG_PATHS, PLUGIN_ROOT, logger
from .ports import port_from
from .yaml_io import coerce_value, dig, flatten_keys, read_yaml
from .yaml_patch import set_scalar


def get_all_keys() -> dict:
    all_keys = {}
    for module_name, config_path in CONFIG_PATHS.items():
        flat = flatten_keys(read_yaml(config_path), module_name)
        for full_key, value in flat.items():
            all_keys[full_key] = {
                "value": value,
                "description": KEY_DESCRIPTIONS.get(full_key, ""),
            }
    return all_keys


def update_keys(updates: dict) -> dict:
    """批量更新（扁平 module.key.subkey = value）"""
    by_module: dict[str, dict] = {}
    for flat_key, value in updates.items():
        module, _, rest = flat_key.partition(".")
        if not rest or module not in CONFIG_PATHS:
            continue
        by_module.setdefault(module, {})[rest] = value

    updated, warnings, port_syncs = [], [], []

    for module, flat in by_module.items():
        path = CONFIG_PATHS[module]
        current = read_yaml(path)
        backup_module(module)

        rebuild_needed = {}
        for dotted, value in flat.items():
            old = dig(current, dotted)
            coerced = coerce_value(value, old)
            if set_scalar(path, dotted, coerced):
                continue
            # 文件里没有这个 key（或它是映射节点）→ 只能重建写入
            rebuild_needed[dotted] = coerced

        if rebuild_needed:
            _rebuild_write(path, rebuild_needed)
            warnings.append(
                f"{module}: {', '.join(rebuild_needed)} 在配置文件中不存在，已新增（该文件的注释可能丢失）"
            )

        updated.append(module)
        logger.info("已更新配置 [%s]: %s", module, list(flat.keys()))

        # 插件端口双写：config.yaml 与 plugin.yaml 必须一致，否则
        # manager 按 plugin.yaml 起进程、客户端按 config.yaml 拨号，静默跑偏
        port_syncs += _sync_plugin_ports(module, flat)

    return {"ok": True, "updated_modules": updated,
            "warnings": warnings, "port_syncs": port_syncs}


def _rebuild_write(path: Path, flat: dict) -> None:
    """回退路径：新增 config.yaml 中原本不存在的 key（会重排格式）"""
    data = read_yaml(path)
    for dotted, value in flat.items():
        parts = dotted.split(".")
        cur = data
        for p in parts[:-1]:
            if not isinstance(cur.get(p), dict):
                cur[p] = {}
            cur = cur[p]
        cur[parts[-1]] = value
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _sync_plugin_ports(module: str, flat: dict) -> list[str]:
    """把改过的插件端口同步写进 custom_plugin/<插件>/plugin.yaml 的 service.port"""
    # (被改的配置 key, 插件名所在 key)
    watch = {
        "tts":   ("plugin.port", "plugin.name"),
        "asr":   ("plugin.base_url", "plugin.name"),
        "agent": ("pi_sidecar.base_url", "pi_sidecar.plugin_name"),
    }
    if module not in watch:
        return []
    port_key, name_key = watch[module]
    if port_key not in flat:
        return []

    port = port_from(flat[port_key])
    if port is None:
        return []

    config = read_yaml(CONFIG_PATHS[module])
    plugin_name = dig(config, name_key)
    if not plugin_name:
        return []

    manifest = PLUGIN_ROOT / str(plugin_name) / "plugin.yaml"
    if not manifest.exists():
        return [f"未找到 {plugin_name}/plugin.yaml，端口未同步"]

    if dig(read_yaml(manifest), "service.port") == port:
        return []

    if set_scalar(manifest, "service.port", port):
        logger.info("已同步端口 %s/plugin.yaml service.port → %d", plugin_name, port)
        return [f"已同步 {plugin_name}/plugin.yaml 的 service.port → {port}"]
    return [f"{plugin_name}/plugin.yaml 写入失败，请手动核对 service.port"]


# 兼容旧接口：前端已不用，保留以防外部脚本仍在调
def get_llm_port() -> dict:
    llm = read_yaml(CONFIG_PATHS["llm"])
    result = {}
    for mode in ("ollama", "openai", "claude"):
        conf = llm.get(mode, {}) or {}
        base_url = conf.get("base_url", "")
        result[mode] = {
            "base_url": base_url,
            "model": conf.get("model", ""),
            "port": port_from(base_url) if base_url else None,
        }
    result["current_mode"] = llm.get("mode", "openai")
    return result

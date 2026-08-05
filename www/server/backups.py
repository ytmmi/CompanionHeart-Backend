"""配置文件的备份 / 恢复 / 重置为 config.example.yaml。

每次保存、恢复、重置前都会先快照一份到 www/.backups/<模块>/，
保留最近 30 份，让任何一次误操作都可逆。
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .paths import BACKUP_DIR, CONFIG_PATHS, logger


def backup_module(module: str) -> str | None:
    """保存前快照一份，返回备份文件名"""
    src = CONFIG_PATHS[module]
    if not src.exists():
        return None
    dst_dir = BACKUP_DIR / module
    dst_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = dst_dir / f"{stamp}.yaml"
    n = 1
    while dst.exists():
        dst = dst_dir / f"{stamp}-{n}.yaml"
        n += 1
    shutil.copy2(src, dst)
    _prune_backups(dst_dir, keep=30)
    return dst.name


def _prune_backups(d: Path, keep: int = 30) -> None:
    files = sorted(d.glob("*.yaml"), key=lambda p: p.name, reverse=True)
    for old in files[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def list_backups() -> dict:
    out = {}
    for module in CONFIG_PATHS:
        d = BACKUP_DIR / module
        items = []
        if d.exists():
            for p in sorted(d.glob("*.yaml"), key=lambda x: x.name, reverse=True):
                st = p.stat()
                items.append({
                    "file": p.name,
                    "size": st.st_size,
                    "time": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })
        example = CONFIG_PATHS[module].with_name("config.example.yaml")
        out[module] = {"backups": items, "has_example": example.exists()}
    return out


def restore_backup(module: str, filename: str) -> dict:
    if module not in CONFIG_PATHS:
        return {"ok": False, "error": f"未知模块: {module}"}
    src = BACKUP_DIR / module / filename
    # 防目录穿越
    if not src.exists() or src.parent.resolve() != (BACKUP_DIR / module).resolve():
        return {"ok": False, "error": "备份文件不存在"}
    backup_module(module)  # 恢复前也备份当前状态，避免误操作不可逆
    shutil.copy2(src, CONFIG_PATHS[module])
    logger.info("已恢复配置 [%s] ← %s", module, filename)
    return {"ok": True, "module": module, "restored": filename}


def reset_to_example(module: str) -> dict:
    if module not in CONFIG_PATHS:
        return {"ok": False, "error": f"未知模块: {module}"}
    example = CONFIG_PATHS[module].with_name("config.example.yaml")
    if not example.exists():
        return {"ok": False, "error": "该模块没有 config.example.yaml"}
    backup = backup_module(module)
    shutil.copy2(example, CONFIG_PATHS[module])
    logger.info("已重置配置 [%s] ← config.example.yaml (备份 %s)", module, backup)
    return {"ok": True, "module": module, "backup": backup}

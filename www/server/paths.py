"""全局常量：路径、端口、端口段约定、日志器。

其余模块一律从这里取路径，不再各自 `Path(__file__).parent...` 推算，
避免拆分后各模块对项目根的理解不一致。
"""
from __future__ import annotations

import logging
from pathlib import Path

# server/ 的上一级是 www/，再上一级才是项目根
WWW_DIR = Path(__file__).parent.parent.resolve()
PROJECT_ROOT = WWW_DIR.parent.resolve()

BACKUP_DIR = WWW_DIR / ".backups"
PLUGIN_ROOT = PROJECT_ROOT / "custom_plugin"
PLUGIN_TRASH = PLUGIN_ROOT / ".trash"

CONFIG_PATHS = {
    "llm":   PROJECT_ROOT / "app" / "configs" / "llm" / "config.yaml",
    "tts":   PROJECT_ROOT / "app" / "configs" / "tts" / "config.yaml",
    "agent": PROJECT_ROOT / "app" / "configs" / "agent" / "config.yaml",
    "asr":   PROJECT_ROOT / "app" / "configs" / "asr" / "config.yaml",
}

BACKEND_URL = "http://127.0.0.1:18000"
BACKEND_PORT = 18000
SETTINGS_PORT = 17999

# 插件端口段约定（README / CONFIG.md）
PORT_BANDS = {
    "tts":   (8100, 8199),
    "llm":   (8200, 8299),
    "agent": (8300, 8399),
    "asr":   (8400, 8499),
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("settings-server")

"""设置服务入口。"""
from __future__ import annotations

import sys
from http.server import ThreadingHTTPServer

from .http_api import SettingsHandler
from .paths import SETTINGS_PORT, logger
from .ports import port_in_use


class _SettingsServer(ThreadingHTTPServer):
    # Windows 下 SO_REUSEADDR 允许多个进程绑同一端口，谁抢到算谁的 ——
    # 结果是改了代码重启后请求还落在旧进程上，排查半天。这里禁掉复用，
    # 端口被占就直接报错退出。
    allow_reuse_address = False
    daemon_threads = True


def main():
    if port_in_use(SETTINGS_PORT):
        logger.error(
            "端口 %d 已被占用 —— 设置服务可能已经在运行。"
            "请先关掉旧窗口，或用 `netstat -ano | findstr %d` 找出进程后结束它。",
            SETTINGS_PORT, SETTINGS_PORT,
        )
        sys.exit(1)

    server = _SettingsServer(("127.0.0.1", SETTINGS_PORT), SettingsHandler)
    logger.info("CompanionHeart 设置服务已启动: http://127.0.0.1:%d", SETTINGS_PORT)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("设置服务已停止")
        server.shutdown()

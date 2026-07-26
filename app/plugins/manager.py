"""插件管理器

负责插件的扫描、注册、启动和停止。
插件作为独立进程运行，提供HTTP服务。
"""

import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

from .base import Plugin

logger = logging.getLogger(__name__)


class PluginManager:
    """插件管理器"""

    def __init__(self, plugin_dir: Path):
        """
        初始化插件管理器。

        Args:
            plugin_dir: 插件根目录（如 custom_plugin/）
        """
        self.plugin_dir = plugin_dir
        self.plugins: dict[str, Plugin] = {}
        self.processes: dict[str, subprocess.Popen] = {}
        self._log_files: dict[str, object] = {}  # 插件日志文件句柄（进程退出时关闭）

    def scan_plugins(self) -> list[Plugin]:
        """
        扫描插件目录，加载所有 plugin.yaml。

        Returns:
            插件列表
        """
        if not self.plugin_dir.exists():
            logger.warning("插件目录不存在: %s", self.plugin_dir)
            self.plugin_dir.mkdir(parents=True, exist_ok=True)
            return []

        plugins = []
        for item in self.plugin_dir.iterdir():
            if not item.is_dir():
                continue

            config_file = item / "plugin.yaml"
            if not config_file.exists():
                logger.debug("跳过无效插件目录: %s（缺少 plugin.yaml）", item.name)
                continue

            try:
                plugin = Plugin.from_yaml(config_file)
                self.plugins[plugin.name] = plugin
                plugins.append(plugin)
                logger.info("发现插件: %s v%s (%s)", plugin.name, plugin.version, plugin.type)
            except Exception as e:
                logger.error("加载插件失败 %s: %s", config_file, e)

        return plugins

    def start_plugin(
        self,
        plugin_name: str,
        wait_timeout: int = 10,
        env: Optional[dict[str, str]] = None,
    ) -> bool:
        """
        启动插件HTTP服务（子进程）。

        Args:
            plugin_name: 插件名称
            wait_timeout: 等待健康检查的超时时间（秒）
            env: 附加环境变量（叠加在当前进程环境之上，如 agent 插件的 LLM 配置）

        Returns:
            True 表示启动成功，False 表示失败
        """
        if plugin_name not in self.plugins:
            logger.error("插件不存在: %s", plugin_name)
            return False

        plugin = self.plugins[plugin_name]

        # 启动命令：plugin.yaml 的 service.command 优先，缺省回退 python server.py
        if plugin.service.command:
            cmd = [*plugin.service.command, "--port", str(plugin.service.port)]
        else:
            server_script = plugin.path / "server.py"
            if not server_script.exists():
                logger.error("插件服务脚本不存在: %s", server_script)
                return False
            # 使用项目虚拟环境的Python
            cmd = [sys.executable, str(server_script), "--port", str(plugin.service.port)]

        # 检查端口是否已占用
        if self._is_port_in_use(plugin.service.port):
            logger.warning("端口 %d 已被占用，尝试连接现有服务", plugin.service.port)
            if self._wait_for_health(plugin, timeout=3):
                logger.info("插件 %s 已在运行", plugin_name)
                return True
            logger.error("端口 %d 被占用但服务不健康", plugin.service.port)
            return False

        # 启动子进程
        try:
            logger.info("启动插件: %s (端口 %d)", plugin_name, plugin.service.port)
            proc_env = None
            if env:
                import os
                proc_env = {**os.environ, **env}
            # 子进程输出落日志文件（不能用 PIPE：无人读取时缓冲区写满会
            # 阻塞子进程 —— Genie 模型加载日志量大，曾导致插件整体卡死）
            log_dir = self.plugin_dir / ".logs"
            log_dir.mkdir(exist_ok=True)
            log_file = open(log_dir / f"{plugin_name}.log", "a", encoding="utf-8", errors="replace")
            proc = subprocess.Popen(
                cmd,
                cwd=str(plugin.path),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                env=proc_env,
            )
            self._log_files[plugin_name] = log_file
            self.processes[plugin_name] = proc

            # 等待健康检查通过
            if self._wait_for_health(plugin, timeout=wait_timeout):
                logger.info("插件 %s 启动成功", plugin_name)
                return True
            else:
                logger.error("插件 %s 启动超时或失败", plugin_name)
                self.stop_plugin(plugin_name)
                return False

        except Exception as e:
            logger.error("启动插件 %s 失败: %s", plugin_name, e)
            return False

    def stop_plugin(self, plugin_name: str, timeout: int = 5) -> bool:
        """
        停止插件进程。

        Args:
            plugin_name: 插件名称
            timeout: 等待进程退出的超时时间（秒）

        Returns:
            True 表示停止成功，False 表示失败
        """
        if plugin_name not in self.processes:
            logger.debug("插件 %s 未运行", plugin_name)
            return True

        proc = self.processes[plugin_name]
        try:
            logger.info("停止插件: %s", plugin_name)
            proc.terminate()
            proc.wait(timeout=timeout)
            logger.info("插件 %s 已停止", plugin_name)
        except subprocess.TimeoutExpired:
            logger.warning("插件 %s 未能在 %d 秒内停止，强制终止", plugin_name, timeout)
            proc.kill()
            proc.wait()
        except Exception as e:
            logger.error("停止插件 %s 失败: %s", plugin_name, e)
            return False
        finally:
            del self.processes[plugin_name]
            log_file = self._log_files.pop(plugin_name, None)
            if log_file is not None:
                try:
                    log_file.close()
                except Exception:
                    pass

        return True

    def stop_all_plugins(self):
        """停止所有插件进程"""
        plugin_names = list(self.processes.keys())
        for name in plugin_names:
            self.stop_plugin(name)

    def get_plugin(self, plugin_name: str) -> Optional[Plugin]:
        """获取插件元数据"""
        return self.plugins.get(plugin_name)

    def is_plugin_running(self, plugin_name: str) -> bool:
        """检查插件是否在运行"""
        if plugin_name not in self.processes:
            return False
        proc = self.processes[plugin_name]
        return proc.poll() is None

    def _wait_for_health(self, plugin: Plugin, timeout: int = 10) -> bool:
        """
        等待插件健康检查通过。

        Args:
            plugin: 插件对象
            timeout: 超时时间（秒）

        Returns:
            True 表示健康，False 表示超时或失败
        """
        health_url = f"{plugin.base_url}{plugin.service.health_check}"
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                resp = httpx.get(health_url, timeout=2.0)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(0.5)

        return False

    def _is_port_in_use(self, port: int) -> bool:
        """检查端口是否被占用"""
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("localhost", port)) == 0

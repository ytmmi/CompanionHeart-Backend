"""插件安装器

支持从Git仓库安装插件，依赖安装到项目虚拟环境。
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PluginInstaller:
    """插件安装器"""

    def __init__(self, plugin_dir: Path):
        """
        初始化插件安装器。

        Args:
            plugin_dir: 插件根目录（如 custom_plugin/）
        """
        self.plugin_dir = plugin_dir
        self.plugin_dir.mkdir(parents=True, exist_ok=True)

    def install_from_git(
        self,
        repo_url: str,
        plugin_name: Optional[str] = None,
        branch: str = "main",
    ) -> bool:
        """
        从Git仓库安装插件。

        依赖安装到项目的虚拟环境（不创建独立虚拟环境）。

        Args:
            repo_url: Git仓库地址
            plugin_name: 插件名称（不提供则从仓库URL解析）
            branch: 分支名称

        Returns:
            True 表示安装成功，False 表示失败
        """
        # 解析插件名称
        if plugin_name is None:
            plugin_name = self._parse_plugin_name_from_url(repo_url)

        plugin_path = self.plugin_dir / plugin_name

        # 检查插件是否已存在
        if plugin_path.exists():
            logger.warning("插件已存在: %s，跳过安装", plugin_name)
            return False

        # 1. git clone
        logger.info("正在克隆插件仓库: %s", repo_url)
        try:
            subprocess.run(
                ["git", "clone", "-b", branch, repo_url, str(plugin_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("克隆成功: %s", plugin_path)
        except subprocess.CalledProcessError as e:
            logger.error("克隆失败: %s", e.stderr)
            return False

        # 2. 检查 plugin.yaml 是否存在
        config_file = plugin_path / "plugin.yaml"
        if not config_file.exists():
            logger.error("无效的插件: 缺少 plugin.yaml")
            self._cleanup_plugin(plugin_path)
            return False

        # 3. 安装依赖到项目虚拟环境
        requirements = plugin_path / "requirements.txt"
        if requirements.exists():
            logger.info("正在安装插件依赖: %s", requirements)
            if not self._install_dependencies(requirements):
                logger.error("依赖安装失败，插件安装中止")
                self._cleanup_plugin(plugin_path)
                return False
        else:
            logger.info("插件无依赖文件（requirements.txt）")

        logger.info("插件安装成功: %s", plugin_name)
        return True

    def install_from_local(self, local_path: Path) -> bool:
        """
        从本地目录安装插件（复制或软链接）。

        Args:
            local_path: 本地插件目录

        Returns:
            True 表示安装成功，False 表示失败
        """
        if not local_path.exists():
            logger.error("本地插件路径不存在: %s", local_path)
            return False

        config_file = local_path / "plugin.yaml"
        if not config_file.exists():
            logger.error("无效的插件: 缺少 plugin.yaml")
            return False

        plugin_name = local_path.name
        plugin_path = self.plugin_dir / plugin_name

        if plugin_path.exists():
            logger.warning("插件已存在: %s", plugin_name)
            return False

        # 创建软链接（Windows需要管理员权限，可能失败）
        try:
            import shutil
            shutil.copytree(local_path, plugin_path)
            logger.info("插件复制成功: %s -> %s", local_path, plugin_path)
        except Exception as e:
            logger.error("插件复制失败: %s", e)
            return False

        # 安装依赖
        requirements = plugin_path / "requirements.txt"
        if requirements.exists():
            if not self._install_dependencies(requirements):
                logger.error("依赖安装失败")
                self._cleanup_plugin(plugin_path)
                return False

        logger.info("插件安装成功: %s", plugin_name)
        return True

    def uninstall(self, plugin_name: str) -> bool:
        """
        卸载插件（删除插件目录，不卸载依赖）。

        Args:
            plugin_name: 插件名称

        Returns:
            True 表示卸载成功，False 表示失败
        """
        plugin_path = self.plugin_dir / plugin_name

        if not plugin_path.exists():
            logger.warning("插件不存在: %s", plugin_name)
            return False

        try:
            self._cleanup_plugin(plugin_path)
            logger.info("插件已卸载: %s", plugin_name)
            return True
        except Exception as e:
            logger.error("卸载插件失败: %s", e)
            return False

    def _install_dependencies(self, requirements: Path) -> bool:
        """
        安装依赖到项目虚拟环境。

        Args:
            requirements: requirements.txt 文件路径

        Returns:
            True 表示安装成功，False 表示失败
        """
        # 使用当前Python环境的pip
        pip_exe = sys.executable

        try:
            subprocess.run(
                [pip_exe, "-m", "pip", "install", "-r", str(requirements)],
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info("依赖安装成功")
            return True
        except subprocess.CalledProcessError as e:
            logger.error("依赖安装失败: %s", e.stderr)
            return False

    def _parse_plugin_name_from_url(self, repo_url: str) -> str:
        """
        从Git仓库URL解析插件名称。

        Args:
            repo_url: Git仓库地址

        Returns:
            插件名称
        """
        # 示例: https://github.com/user/TTS_genie_tts.git -> TTS_genie_tts
        parts = repo_url.rstrip("/").split("/")
        name = parts[-1]
        if name.endswith(".git"):
            name = name[:-4]
        return name

    def _cleanup_plugin(self, plugin_path: Path):
        """删除插件目录"""
        import shutil
        if plugin_path.exists():
            shutil.rmtree(plugin_path)

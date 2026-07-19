"""插件系统

提供插件管理、安装和HTTP客户端功能。
支持从Git仓库安装插件，依赖安装到项目虚拟环境。
"""

from .manager import PluginManager
from .installer import PluginInstaller
from .client import PluginHTTPClient

__all__ = ["PluginManager", "PluginInstaller", "PluginHTTPClient"]

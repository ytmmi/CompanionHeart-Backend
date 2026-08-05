"""
CompanionHeart 设置服务入口（端口 17999）

实现已按职责拆分到 www/server/ 包，本文件只负责把包挂上 sys.path 并启动，
以便 `.venv\\python.exe www\\settings_server.py` 这样的老调用方式继续可用。
各模块的职责见 www/server/__init__.py。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 直接以脚本方式运行时，www/ 不在 sys.path 上，import server 会失败
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from server.main import main  # noqa: E402

if __name__ == "__main__":
    main()

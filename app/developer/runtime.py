"""同一后端进程共享的开发认证运行时；重启自然清空。"""

from __future__ import annotations

from .auth import DeveloperAuthInterceptor


_interceptor = DeveloperAuthInterceptor()


def get_developer_auth() -> DeveloperAuthInterceptor:
    return _interceptor


def configure_developer_auth(interceptor: DeveloperAuthInterceptor) -> None:
    global _interceptor
    _interceptor = interceptor

"""轻量 HTTP 请求封装，供状态探测 / 连接测试 / 模型列表复用。"""
from __future__ import annotations


def http_request(method: str, url: str, timeout: float = 6.0,
                 json_body=None, headers=None):
    """轻量 HTTP，用 requests（venv 已装）；返回 (状态码, 文本, 错误)"""
    import requests
    try:
        r = requests.request(method, url, timeout=timeout, json=json_body, headers=headers or {})
        return r.status_code, r.text, None
    except Exception as e:
        return None, None, f"{type(e).__name__}: {e}"

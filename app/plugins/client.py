"""插件HTTP客户端基类"""

import logging
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)


class PluginHTTPClient:
    """插件HTTP客户端基类"""

    def __init__(self, base_url: str, timeout: int = 120):
        """
        初始化插件HTTP客户端。

        Args:
            base_url: 插件服务地址（如 http://localhost:8100）
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def health_check(self) -> bool:
        """
        健康检查。

        Returns:
            True 表示插件服务正常，False 表示异常。
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception as e:
            logger.warning("插件健康检查失败: %s", e)
            return False

    async def post(
        self,
        endpoint: str,
        json: Optional[dict] = None,
        **kwargs,
    ) -> httpx.Response:
        """
        发送POST请求。

        Args:
            endpoint: API端点（如 /synthesize）
            json: 请求体JSON（与 kwargs 的 files/data 互斥）
            **kwargs: 其他httpx参数（如 files/data 用于 multipart 上传）

        Returns:
            响应对象
        """
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if json is not None:
                return await client.post(url, json=json, **kwargs)
            return await client.post(url, **kwargs)

    async def get(self, endpoint: str, **kwargs) -> httpx.Response:
        """
        发送GET请求。

        Args:
            endpoint: API端点（如 /voices）
            **kwargs: 其他httpx参数

        Returns:
            响应对象
        """
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.get(url, **kwargs)

    async def delete(
        self,
        endpoint: str,
        json: Optional[dict] = None,
        **kwargs,
    ) -> httpx.Response:
        """发送 DELETE 请求（可选 JSON 请求体）。"""
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            return await client.delete(url, json=json, **kwargs)

    async def stream_post(
        self,
        endpoint: str,
        json: Optional[dict] = None,
        **kwargs,
    ) -> AsyncIterator[bytes]:
        """
        发送POST请求并流式接收响应。

        Args:
            endpoint: API端点（如 /stream）
            json: 请求体JSON
            **kwargs: 其他httpx参数

        Yields:
            响应数据块
        """
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=json, **kwargs) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes():
                    yield chunk

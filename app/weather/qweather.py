"""和风天气 QWeather 引擎（Ed25519 私钥自动签发 JWT，v1 API）"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx
import jwt

from .base import SunTimes, WeatherData, WeatherEngine

logger = logging.getLogger(__name__)

_JWT_TTL = 840  # JWT 有效期 14 分钟（留 1 分钟余量）
_TOKEN_CACHE: tuple[float, str] | None = None  # (expire_ts, token)

# 天气现象代码 → 中文描述
_WEATHER_CODE_MAP: dict[str, str] = {
    "100": "晴", "101": "多云", "102": "少云", "103": "晴间多云",
    "104": "阴",
    "300": "阵雨", "301": "强阵雨", "302": "雷阵雨", "303": "强雷阵雨",
    "304": "雷阵雨伴有冰雹", "305": "小雨", "306": "中雨", "307": "大雨",
    "308": "极端降雨", "309": "毛毛雨/细雨", "310": "暴雨", "311": "大暴雨",
    "312": "特大暴雨", "313": "冻雨", "314": "小到中雨", "315": "中到大雨",
    "316": "大到暴雨", "317": "暴雨到大暴雨", "318": "大暴雨到特大暴雨",
    "399": "雨",
    "400": "小雪", "401": "中雪", "402": "大雪", "403": "暴雪",
    "404": "雨夹雪", "405": "雨雪天气", "406": "阵雨夹雪", "407": "阵雪",
    "408": "小到中雪", "409": "中到大雪", "410": "大到暴雪",
    "499": "雪",
}


def _to_bg_weather(code: str) -> str:
    c = str(code)
    if c == "100":
        return "晴"
    if c.startswith("3"):
        return "雨"
    if c.startswith("4"):
        return "雪"
    return "多云"


class QWeatherEngine(WeatherEngine):
    """和风天气 v1 API 引擎（Ed25519 私钥 → 自动签发 JWT Bearer Token）"""

    def __init__(
        self,
        private_key: str = "",
        kid: str = "",
        sub: str = "",
        api_host: str = "",
        timeout: int = 10,
    ):
        self.private_key = private_key
        self.kid = kid
        self.sub = sub
        api_host = api_host.strip().rstrip("/")
        if api_host and not api_host.startswith("http"):
            api_host = f"https://{api_host}"
        self.api_host = api_host
        self.timeout = timeout

    def _get_token(self) -> str:
        """获取或自动签发 JWT（进程内缓存，14 分钟有效）"""
        global _TOKEN_CACHE
        now = time.time()
        if _TOKEN_CACHE and _TOKEN_CACHE[0] > now + 30:
            return _TOKEN_CACHE[1]

        iat = int(now) - 30
        exp = iat + _JWT_TTL
        token = jwt.encode(
            payload={"sub": self.sub, "iat": iat, "exp": exp},
            key=self.private_key,
            algorithm="EdDSA",
            headers={"kid": self.kid},
        )
        _TOKEN_CACHE = (exp, token)
        return token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    async def get_current(self, lat: float, lon: float) -> WeatherData:
        url = f"{self.api_host}/weather/v1/current/{lat}/{lon}"
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            resp = await cli.get(url, headers=self._auth_headers())
            resp.raise_for_status()
            data = resp.json()
        return self._parse_current(data)

    async def get_sun_times(self, lat: float, lon: float, date: str = "") -> SunTimes:
        d = date or datetime.now().strftime("%Y%m%d")
        url = f"{self.api_host}/astronomy/v1/sun/{lat}/{lon}"
        async with httpx.AsyncClient(timeout=self.timeout) as cli:
            resp = await cli.get(url, headers=self._auth_headers(), params={"date": d})
            resp.raise_for_status()
            data = resp.json()
        return SunTimes(
            sunrise=data.get("sunrise", "06:00")[:5],
            sunset=data.get("sunset", "18:00")[:5],
        )

    async def validate_config(self) -> bool:
        """用北京坐标发一次请求验证配置是否有效"""
        try:
            await self.get_current(39.92, 116.41)
            return True
        except Exception as e:
            logger.warning("QWeather 验证失败: %s", e)
            return False

    @staticmethod
    def _parse_current(data: dict) -> WeatherData:
        cond = data.get("condition", {})
        code = str(cond.get("code", "100"))
        temp = data.get("temperature", {})
        wind = data.get("wind", {})
        return WeatherData(
            weather=_WEATHER_CODE_MAP.get(code, _to_bg_weather(code)),
            temperature=round(temp.get("value", 0), 1),
            humidity=data.get("humidity", 0),
            wind_scale=wind.get("scale", 0),
            icon_code=code,
            city="",
        )

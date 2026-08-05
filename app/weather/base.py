"""天气模块基类 — 数据模型与抽象引擎"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class WeatherData:
    """实时天气数据"""
    weather: str          # 天气描述（晴/多云/阴/雨/雪）
    temperature: float    # 实时温度 (°C)
    humidity: float       # 相对湿度 (0~1)
    wind_scale: int       # 蒲福风级 (0~12)
    icon_code: str        # 和风天气图标代码（如 "100"）
    city: str = ""        # 城市名（可选）


@dataclass
class SunTimes:
    """日出日落时间"""
    sunrise: str  # "HH:MM"
    sunset: str   # "HH:MM"


class WeatherEngine(ABC):
    """天气引擎抽象基类"""

    @abstractmethod
    async def get_current(self, lat: float, lon: float) -> WeatherData:
        """获取指定经纬度的实时天气"""

    @abstractmethod
    async def get_sun_times(self, lat: float, lon: float, date: str = "") -> SunTimes:
        """获取指定经纬度的日出日落时间。date 格式 yyyyMMdd，空取今天"""

    async def validate_config(self) -> bool:
        """验证引擎配置是否可用（子类可选覆盖）"""
        return True

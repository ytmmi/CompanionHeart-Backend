"""天气引擎工厂"""

from __future__ import annotations

import logging

from .base import WeatherEngine
from .qweather import QWeatherEngine

logger = logging.getLogger(__name__)


class WeatherFactory:
    """天气引擎工厂：从 config.yaml / 代码创建实例"""

    @staticmethod
    def create_from_config(config: dict) -> WeatherEngine:
        weather_config = config.get("weather", {}) or {}
        return QWeatherEngine(
            private_key=weather_config.get("private_key", ""),
            kid=weather_config.get("kid", ""),
            sub=weather_config.get("sub", ""),
            api_host=weather_config.get("api_host", ""),
            timeout=weather_config.get("timeout", 10),
        )

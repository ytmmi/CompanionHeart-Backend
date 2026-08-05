"""天气 API 路由（和风天气）"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.weather import WeatherData, WeatherEngine, WeatherFactory, SunTimes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Weather"])

_engine: Optional[WeatherEngine] = None


def _load_config() -> dict:
    import yaml
    config_path = Path(__file__).resolve().parents[2] / "configs" / "weather" / "config.yaml"
    if not config_path.exists():
        return {"enabled": False}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _is_enabled() -> bool:
    return bool(_load_config().get("enabled", False))


def get_engine() -> WeatherEngine:
    global _engine
    if _engine is None:
        _engine = WeatherFactory.create_from_config(_load_config())
    return _engine


@router.get("/weather/current", response_model=dict)
async def weather_current(
    lat: float = Query(..., ge=-90, le=90, description="纬度"),
    lon: float = Query(..., ge=-180, le=180, description="经度"),
    engine: WeatherEngine = Depends(get_engine),
):
    """获取指定经纬度的实时天气"""
    if not _is_enabled():
        raise HTTPException(status_code=403, detail="天气模块已禁用")
    try:
        data = await engine.get_current(lat, lon)
    except Exception as e:
        logger.error("天气查询失败: %s", e)
        raise HTTPException(status_code=503, detail=f"天气服务不可用: {e}")
    return {
        "weather": data.weather,
        "temperature": data.temperature,
        "humidity": data.humidity,
        "wind_scale": data.wind_scale,
        "icon_code": data.icon_code,
        "city": data.city,
    }


@router.get("/sun/times", response_model=dict)
async def sun_times(
    lat: float = Query(..., ge=-90, le=90, description="纬度"),
    lon: float = Query(..., ge=-180, le=180, description="经度"),
    date: str = Query("", description="日期，格式 yyyyMMdd，空取今天"),
    engine: WeatherEngine = Depends(get_engine),
):
    """获取指定经纬度的日出日落时间"""
    if not _is_enabled():
        raise HTTPException(status_code=403, detail="天气模块已禁用")
    try:
        data = await engine.get_sun_times(lat, lon, date)
    except Exception as e:
        logger.error("日出日落查询失败: %s", e)
        raise HTTPException(status_code=503, detail=f"日出日落服务不可用: {e}")
    return {
        "sunrise": data.sunrise,
        "sunset": data.sunset,
    }

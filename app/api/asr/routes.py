"""ASR 语音识别 API 路由。

端点：
    GET  /api/voice/asr/status    - 查询 ASR 配置和插件可用性
    GET  /api/voice/asr/enabled   - 查询 ASR 是否启用
    POST /api/voice/asr/enabled   - 设置 ASR 启用/禁用（前端控制）
    GET  /api/voice/asr/languages - 查询支持语言
    POST /api/voice/asr           - 上传音频并转写

ASR 模型由 app/configs/asr/config.yaml 控制，通常以独立插件运行。
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.asr import ASRBase, ASRFactory, TranscriptionResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice/asr", tags=["ASR"])


class ASRStatus(BaseModel):
    enabled: bool = Field(..., description="ASR 是否启用")
    engine: str = Field(..., description="ASR 引擎类型")
    available: bool = Field(..., description="ASR 引擎是否可达")
    supported_formats: list[str] = Field(default_factory=list)


class ASRResponse(BaseModel):
    text: str
    emotion: Optional[str] = None
    events: list[str] = Field(default_factory=list)
    detected_language: Optional[str] = None
    language: str = "auto"


class ASREnabledRequest(BaseModel):
    enabled: bool = Field(..., description="是否启用 ASR")


class ASREnabledResponse(BaseModel):
    enabled: bool = Field(..., description="ASR 当前是否启用")


_asr_engine: Optional[ASRBase] = None
_asr_config: Optional[dict] = None
# 运行时启用开关（前端控制，进程内状态）。初始值取配置的 enabled；
# 注意：配置 enabled=false 时插件子进程不会随后端启动，
# 运行时打开后请求仍会因插件不可达而 503 —— 属于预期行为。
_asr_enabled: Optional[bool] = None


def _load_asr_config() -> dict:
    import yaml

    config_path = Path(__file__).parents[2] / "configs" / "asr" / "config.yaml"
    if not config_path.exists():
        logger.warning("ASR 配置文件不存在: %s，使用默认配置", config_path)
        return {
            "mode": "plugin",
            "enabled": False,
            "plugin": {
                "name": "ASR_funasr",
                "base_url": "http://localhost:8400",
                "timeout": 120,
                "language": "auto",
                "use_itn": True,
            },
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _get_asr_config() -> dict:
    global _asr_config
    if _asr_config is None:
        _asr_config = _load_asr_config()
    return _asr_config


async def get_asr_engine() -> ASRBase:
    global _asr_engine
    if _asr_engine is None:
        config = _get_asr_config()
        try:
            _asr_engine = ASRFactory.create_from_config(config)
            logger.info("ASR 引擎初始化成功: %s", type(_asr_engine).__name__)
        except Exception as e:
            logger.error("ASR 引擎初始化失败: %s", e)
            raise HTTPException(status_code=500, detail=f"ASR 引擎初始化失败: {e}")
    return _asr_engine


def _is_asr_enabled() -> bool:
    global _asr_enabled
    if _asr_enabled is None:
        _asr_enabled = bool(_get_asr_config().get("enabled", False))
    return _asr_enabled


def _require_asr_enabled() -> None:
    """ASR 禁用时拒绝转写请求（403）"""
    if not _is_asr_enabled():
        raise HTTPException(status_code=403, detail="ASR 已禁用，请先在开发设置或后端开启 ASR")


@router.get("/status", response_model=ASRStatus)
async def asr_status(asr: ASRBase = Depends(get_asr_engine)):
    """查询 ASR 配置及插件服务是否可达。"""
    config = _get_asr_config()
    try:
        available = await asr.validate_config()
    except Exception:
        available = False
    return ASRStatus(
        enabled=_is_asr_enabled(),
        engine=type(asr).__name__,
        available=available,
        supported_formats=list(asr.supported_formats),
    )


@router.get("/enabled", response_model=ASREnabledResponse)
async def get_asr_enabled():
    """查询 ASR 是否启用"""
    return ASREnabledResponse(enabled=_is_asr_enabled())


@router.post("/enabled", response_model=ASREnabledResponse)
async def set_asr_enabled(request: ASREnabledRequest):
    """设置 ASR 启用/禁用（前端控制；禁用后转写端点返回 403）"""
    global _asr_enabled
    _asr_enabled = request.enabled
    logger.info("ASR 启用状态设为: %s", _asr_enabled)
    return ASREnabledResponse(enabled=_asr_enabled)


@router.get("/languages")
async def asr_languages(asr: ASRBase = Depends(get_asr_engine)):
    """查询 ASR 插件支持的语言。"""
    languages = await asr.get_languages()
    return {"languages": languages}


@router.post("", response_model=ASRResponse)
async def transcribe_audio(
    audio: UploadFile = File(..., description="待识别音频文件"),
    language: str = Form("auto"),
    use_itn: Optional[bool] = Form(None),
    asr: ASRBase = Depends(get_asr_engine),
):
    """上传音频并返回纯文本及可选情感/事件信号。"""
    _require_asr_enabled()

    audio_data = await audio.read()
    if not audio_data:
        raise HTTPException(status_code=422, detail="音频文件为空")

    kwargs: dict = {"audio_filename": audio.filename or "audio.wav"}
    if use_itn is not None:
        kwargs["use_itn"] = use_itn

    try:
        result: TranscriptionResult = await asr.transcribe_detailed(
            audio_data,
            language=language,
            **kwargs,
        )
    except RuntimeError as e:
        logger.error("ASR 转写失败: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("ASR 转写发生未处理异常")
        raise HTTPException(status_code=500, detail=f"ASR 转写失败: {e}")

    return ASRResponse(
        text=result.text,
        emotion=result.emotion,
        events=result.events,
        detected_language=result.detected_language,
        language=language,
    )

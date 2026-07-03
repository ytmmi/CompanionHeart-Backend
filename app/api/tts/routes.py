"""TTS 语音合成 API 路由

端点:
    GET    /api/voice/tts/voices       — 获取可用语音/角色列表
    GET    /api/voice/tts/status        — 获取 TTS 引擎状态
    POST   /api/voice/tts              — 语音合成（非流式，返回完整音频文件）
    POST   /api/voice/tts/stream       — 流式语音合成（逐 chunk 返回音频数据）

支持的 TTS 引擎:
    - edge:  微软 Edge-TTS（在线，免费）
             参数: voice, rate, volume, pitch
    - local: Genie-TTS（本地 ONNX 推理）
             参数: character_name, split_sentence

流式 / 非流式:
    - POST /api/voice/tts        → synthesize()  → 完整音频 bytes
    - POST /api/voice/tts/stream → stream()      → AsyncIterator[bytes]
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.tts import TTSBase, TTSFactory, GenieTTS

logger = logging.getLogger(__name__)

# ── 路由定义 ──
router = APIRouter(prefix="/api/voice/tts", tags=["TTS"])


# ── 请求/响应模型 ──

class TTSRequest(BaseModel):
    """语音合成请求（兼容 EdgeTTS 和 GenieTTS）"""
    # 公共参数
    text: str = Field(..., min_length=1, max_length=2000, description="要合成的文本")

    # EdgeTTS 参数
    voice: Optional[str] = Field(None, description="EdgeTTS: 语音名称，如 zh-CN-XiaoxiaoNeural")
    rate: Optional[str] = Field(None, description="EdgeTTS: 语速 -50% ~ +50%")
    volume: Optional[str] = Field(None, description="EdgeTTS: 音量 -50% ~ +50%")
    pitch: Optional[str] = Field(None, description="EdgeTTS: 音调 -50Hz ~ +50Hz")

    # GenieTTS 参数
    character_name: Optional[str] = Field(None, description="GenieTTS: 角色名称（如 mika / feibi / thirtyseven）")
    split_sentence: Optional[bool] = Field(None, description="GenieTTS: 是否按分句合成")


class VoiceInfo(BaseModel):
    """语音信息"""
    voice: str = Field(..., description="语音标识")
    language: str = Field(..., description="语言代码")
    description: str = Field(..., description="描述")


class VoicesResponse(BaseModel):
    """语音列表响应"""
    voices: list[VoiceInfo] = Field(..., description="可用语音列表")
    engine: str = Field(..., description="当前 TTS 引擎类型")


class TTSStatus(BaseModel):
    """TTS 引擎状态"""
    engine: str = Field(..., description="引擎类型")
    voices_count: int = Field(..., description="可用语音数")
    streaming_supported: bool = Field(..., description="是否支持流式")


# ── 依赖注入 ──

_tts_engine: Optional[TTSBase] = None


async def get_tts_engine() -> TTSBase:
    """获取 TTS 引擎实例（单例）"""
    global _tts_engine
    if _tts_engine is None:
        try:
            config = _load_tts_config()
            _tts_engine = TTSFactory.create_from_config(config)
            logger.info("TTS 引擎初始化成功: %s", type(_tts_engine).__name__)
        except Exception as e:
            logger.error("TTS 引擎初始化失败: %s", e)
            raise HTTPException(status_code=500, detail=f"TTS 引擎初始化失败: {e}")
    return _tts_engine


def _build_engine_kwargs(request: TTSRequest) -> dict:
    """
    根据请求参数构建引擎调用参数。
    自动传递非 None 的参数，与引擎无关。
    """
    kwargs: dict = {"text": request.text}
    for field in ("voice", "rate", "volume", "pitch", "character_name", "split_sentence"):
        val = getattr(request, field, None)
        if val is not None:
            kwargs[field] = val
    return kwargs


def _load_tts_config() -> dict:
    """从 YAML 文件加载 TTS 配置"""
    import yaml

    # app/api/tts/routes.py → app/configs/tts/config.yaml
    config_path = Path(__file__).parents[2] / "configs" / "tts" / "config.yaml"
    if not config_path.exists():
        logger.warning("TTS 配置文件不存在: %s，使用默认配置", config_path)
        return {
            "mode": "edge",
            "edge": {
                "voices": {
                    "zh": {"voice": "zh-CN-XiaoxiaoNeural", "language": "zh", "description": "中文女声 (晓晓)"},
                    "en": {"voice": "en-US-AriaNeural", "language": "en", "description": "英文女声 (Aria)"},
                    "jp": {"voice": "ja-JP-NanamiNeural", "language": "jp", "description": "日语女声 (Nanami)"},
                },
                "default_params": {"rate": "+0%", "volume": "+0%", "pitch": "+0Hz"},
            },
        }

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── 路由 ──

@router.get("/voices", response_model=VoicesResponse)
async def list_voices(
    tts: TTSBase = Depends(get_tts_engine),
):
    """
    获取当前 TTS 引擎支持的语音/角色列表。

    返回语音名称、语言代码、描述信息和当前引擎类型。
    """
    try:
        voices = await tts.get_voices()
        engine_type = type(tts).__name__
        return VoicesResponse(
            voices=[
                VoiceInfo(voice=v["voice"], language=v["language"], description=v["description"])
                for v in voices
            ],
            engine=engine_type,
        )
    except Exception as e:
        logger.error("获取语音列表失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取语音列表失败: {e}")


@router.get("/status", response_model=TTSStatus)
async def tts_status(
    tts: TTSBase = Depends(get_tts_engine),
):
    """获取当前 TTS 引擎的状态信息（类型、可用语音数、流式支持）"""
    try:
        voices = await tts.get_voices()
        engine_type = type(tts).__name__
        return TTSStatus(
            engine=engine_type,
            voices_count=len(voices),
            streaming_supported=True,
        )
    except Exception as e:
        logger.error("获取 TTS 状态失败: %s", e)
        raise HTTPException(status_code=500, detail=f"获取 TTS 状态失败: {e}")


# ── 非流式合成：返回完整音频文件 ──

@router.post("")
async def synthesize(
    request: TTSRequest,
    tts: TTSBase = Depends(get_tts_engine),
):
    """
    语音合成 — 非流式（返回完整音频文件）。

    EdgeTTS 返回 MP3，GenieTTS 返回 WAV。
    引擎无关的参数自动传递，无关参数自动忽略。
    """
    try:
        kwargs = _build_engine_kwargs(request)
        text = kwargs.pop("text")
        audio_data = await tts.synthesize(text=text, **kwargs)

        if isinstance(tts, GenieTTS):
            media_type = "audio/wav"
            filename = "tts_output.wav"
        else:
            media_type = "audio/mpeg"
            filename = "tts_output.mp3"

        return Response(
            content=audio_data,
            media_type=media_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "Content-Length": str(len(audio_data)),
            },
        )
    except ImportError as e:
        logger.error("TTS 库未安装: %s", e)
        raise HTTPException(status_code=500, detail=f"TTS 库未安装，请执行: pip install {str(e).split()[-1]}")
    except Exception as e:
        logger.error("语音合成失败: %s", e)
        raise HTTPException(status_code=500, detail=f"语音合成失败: {e}")


# ── 流式合成：逐 chunk 返回音频数据 ──

@router.post("/stream")
async def synthesize_stream(
    request: TTSRequest,
    tts: TTSBase = Depends(get_tts_engine),
):
    """
    语音合成 — 流式（逐 chunk 返回音频数据）。

    EdgeTTS 逐 chunk 返回 MP3，GenieTTS 使用 tts_async 逐 chunk 返回 WAV。
    适用于实时播放场景（如与 LLM 流式输出联动）。
    """
    try:
        kwargs = _build_engine_kwargs(request)
        text = kwargs.pop("text")

        if isinstance(tts, GenieTTS):
            media_type = "audio/wav"
        else:
            media_type = "audio/mpeg"

        async def audio_stream():
            async for chunk in tts.stream(text=text, **kwargs):
                yield chunk

        return StreamingResponse(
            content=audio_stream(),
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Engine-Type": type(tts).__name__,
            },
        )
    except ImportError as e:
        logger.error("TTS 库未安装: %s", e)
        raise HTTPException(status_code=500, detail=f"TTS 库未安装，请执行: pip install {str(e).split()[-1]}")
    except Exception as e:
        logger.error("流式语音合成失败: %s", e)
        raise HTTPException(status_code=500, detail=f"流式语音合成失败: {e}")

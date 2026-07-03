"""
CompanionHeart Backend — FastAPI 应用入口

启动方式:
    uvicorn app.main:app --reload --port 8000
"""

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.tts import router as tts_router

# ── 日志配置 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── FastAPI 应用 ──
app = FastAPI(
    title="CompanionHeart API",
    version="0.1.0",
    description="AI 陪伴助手后端 API",
)

# ── CORS 配置（允许前端跨域访问） ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──
app.include_router(tts_router)


# ── 健康检查 ──

@app.get("/api/health")
async def health_check():
    """健康检查接口"""
    return {"status": "ok", "service": "CompanionHeart"}


@app.get("/api/state")
async def service_state():
    """服务状态接口"""
    return {
        "status": "running",
        "version": "0.1.0",
        "tts_available": True,
    }

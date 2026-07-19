"""
CompanionHeart Backend — FastAPI 应用入口

启动方式:
    uvicorn app.main:app --reload --port 8000
"""

import atexit
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.tts import router as tts_router
from app.api.llm import router as llm_router
from app.plugins.manager import PluginManager

# ── 日志配置 ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 插件管理器 ──
_plugin_manager: PluginManager = None

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
app.include_router(llm_router)


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
        "llm_available": True,
    }


# ── 插件系统 ──

def initialize_plugins():
    """初始化插件系统"""
    global _plugin_manager

    # 插件目录
    plugin_dir = Path(__file__).parent.parent / "custom_plugin"
    _plugin_manager = PluginManager(plugin_dir)

    # 扫描插件
    plugins = _plugin_manager.scan_plugins()
    if not plugins:
        logger.info("未发现插件")
        return

    # 读取配置，确定需要启动的插件
    enabled_plugins = _get_enabled_plugins()

    # 启动插件
    for plugin_name in enabled_plugins:
        plugin = _plugin_manager.get_plugin(plugin_name)
        if plugin:
            logger.info("启动插件: %s", plugin_name)
            success = _plugin_manager.start_plugin(plugin_name)
            if not success:
                logger.error("插件启动失败: %s", plugin_name)
        else:
            logger.warning("配置的插件不存在: %s", plugin_name)


def _get_enabled_plugins() -> list[str]:
    """从配置中读取需要启动的插件列表"""
    import yaml

    enabled = []

    # 检查TTS配置
    tts_config_path = Path(__file__).parent / "configs" / "tts" / "config.yaml"
    if tts_config_path.exists():
        with open(tts_config_path, "r", encoding="utf-8") as f:
            tts_config = yaml.safe_load(f)
            if tts_config.get("mode") == "plugin":
                plugin_name = tts_config.get("plugin", {}).get("name")
                if plugin_name:
                    enabled.append(plugin_name)

    # 检查LLM配置（预留）
    llm_config_path = Path(__file__).parent / "configs" / "llm" / "config.yaml"
    if llm_config_path.exists():
        with open(llm_config_path, "r", encoding="utf-8") as f:
            llm_config = yaml.safe_load(f)
            if llm_config.get("mode") == "plugin":
                plugin_name = llm_config.get("plugin", {}).get("name")
                if plugin_name:
                    enabled.append(plugin_name)

    return enabled


def shutdown_plugins():
    """停止所有插件"""
    global _plugin_manager
    if _plugin_manager:
        logger.info("正在停止所有插件...")
        _plugin_manager.stop_all_plugins()
        logger.info("插件已停止")


# ── 启动和关闭事件 ──

@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("CompanionHeart 后端启动")
    initialize_plugins()


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("CompanionHeart 后端关闭")
    shutdown_plugins()


# 注册进程退出时的清理函数
atexit.register(shutdown_plugins)

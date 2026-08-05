"""
CompanionHeart Backend — FastAPI 应用入口

启动方式:
    uvicorn app.main:app --reload --port 18000
"""

import atexit
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.tts import router as tts_router
from app.api.llm import router as llm_router
from app.api.agent import router as agent_router
from app.api.asr import router as asr_router
from app.api.weather import router as weather_router
from app.api.conversations import router as conversations_router
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
app.include_router(agent_router)
app.include_router(asr_router)
app.include_router(weather_router)
app.include_router(conversations_router)


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
            # agent 插件需要注入 LLM 配置环境变量（配置单一真源: configs/llm/config.yaml）
            env = _build_agent_sidecar_env() if plugin.type == "agent" else None
            # ASR 插件模型较重（后台加载仍需时间），放宽健康检查等待；插件侧已改为
            # 后台加载模型，/health 会立即就绪，此超时仅为慢机器的防御性余量
            wait_timeout = 60 if plugin.type == "asr" else 10
            success = _plugin_manager.start_plugin(
                plugin_name, env=env, wait_timeout=wait_timeout)
            if not success:
                logger.error("插件启动失败: %s", plugin_name)
        else:
            logger.warning("配置的插件不存在: %s", plugin_name)


def _build_agent_sidecar_env() -> dict:
    """把 LLM 配置翻译为 agent sidecar 的环境变量（key 不落盘、不进 argv）

    映射规则:
        mode=openai 且官方 DeepSeek 端点 → LLM_PROVIDER=deepseek（pi 内置 provider）
        mode=openai 自定义端点          → LLM_PROVIDER=custom + LLM_BASE_URL
        mode=ollama                     → LLM_PROVIDER=custom + <base_url>/v1
    """
    import yaml

    llm_config_path = Path(__file__).parent / "configs" / "llm" / "config.yaml"
    if not llm_config_path.exists():
        logger.warning("LLM 配置不存在，agent sidecar 将无法初始化 provider")
        return {}

    with open(llm_config_path, "r", encoding="utf-8") as f:
        llm_config = yaml.safe_load(f)

    mode = llm_config.get("mode", "openai")
    conf = llm_config.get(mode, {})
    base_url = (conf.get("base_url") or "").rstrip("/")
    env = {
        "LLM_MODEL": conf.get("model", ""),
        "LLM_API_KEY": conf.get("api_key", ""),
        "LLM_TIMEOUT": str(conf.get("timeout", 60)),
    }

    if mode == "openai" and base_url in ("https://api.deepseek.com", "https://api.deepseek.com/v1"):
        env["LLM_PROVIDER"] = "deepseek"
    elif mode == "ollama":
        env["LLM_PROVIDER"] = "custom"
        env["LLM_BASE_URL"] = f"{base_url}/v1"
    else:
        env["LLM_PROVIDER"] = "custom"
        env["LLM_BASE_URL"] = base_url

    return env


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

    # 检查ASR配置（默认关闭：模型加载约 18 秒会拖慢后端启动）
    asr_config_path = Path(__file__).parent / "configs" / "asr" / "config.yaml"
    if asr_config_path.exists():
        with open(asr_config_path, "r", encoding="utf-8") as f:
            asr_config = yaml.safe_load(f)
            if asr_config.get("enabled", False):
                mode = asr_config.get("mode", "plugin")
                plugin_name = asr_config.get(mode, {}).get("name")
                if plugin_name:
                    enabled.append(plugin_name)

    # 检查Agent配置
    agent_config_path = Path(__file__).parent / "configs" / "agent" / "config.yaml"
    if agent_config_path.exists():
        with open(agent_config_path, "r", encoding="utf-8") as f:
            agent_config = yaml.safe_load(f)
            if agent_config.get("enabled", False):
                mode = agent_config.get("mode", "pi_sidecar")
                plugin_name = agent_config.get(mode, {}).get("plugin_name")
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


def restart_agent_plugin() -> bool:
    """重启 agent sidecar 插件（崩溃自愈 / 配置变更后调用）

    供 /api/agent/restart 端点与健康检查失败时的自愈逻辑使用。
    """
    global _plugin_manager
    if _plugin_manager is None:
        logger.error("插件管理器未初始化，无法重启 agent 插件")
        return False

    import yaml

    agent_config_path = Path(__file__).parent / "configs" / "agent" / "config.yaml"
    if not agent_config_path.exists():
        return False
    with open(agent_config_path, "r", encoding="utf-8") as f:
        agent_config = yaml.safe_load(f)
    mode = agent_config.get("mode", "pi_sidecar")
    plugin_name = agent_config.get(mode, {}).get("plugin_name")
    if not plugin_name:
        return False

    logger.info("重启 agent 插件: %s", plugin_name)
    _plugin_manager.stop_plugin(plugin_name)
    return _plugin_manager.start_plugin(
        plugin_name, env=_build_agent_sidecar_env(), wait_timeout=20)


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

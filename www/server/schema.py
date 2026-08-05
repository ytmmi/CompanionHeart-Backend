"""「简单视图」的分组表单 Schema。

前端只认这份结构：groups[].fields[] 决定渲染成什么控件、有什么校验、
在什么条件下显示（showIf）。值从 config.yaml 现读，不做缓存。
"""
from __future__ import annotations

from .descriptions import KEY_DESCRIPTIONS
from .paths import CONFIG_PATHS, PLUGIN_ROOT, PORT_BANDS
from .voices import scan_plugin_characters
from .yaml_io import dig, read_yaml


def _f(key, label, ftype, value, **extra) -> dict:
    d = {"key": key, "label": label, "type": ftype, "value": value,
         "description": KEY_DESCRIPTIONS.get(key, "")}
    d.update(extra)
    return d


def list_plugins_by_type(ptype: str) -> list[str]:
    """扫描 custom_plugin/ 下 type 匹配的插件目录名"""
    out = []
    if not PLUGIN_ROOT.exists():
        return out
    for d in sorted(PLUGIN_ROOT.iterdir()):
        manifest = d / "plugin.yaml"
        if not d.is_dir() or not manifest.exists():
            continue
        try:
            meta = read_yaml(manifest)
            if meta.get("type") == ptype:
                out.append(d.name)
        except Exception:
            continue
    return out


def _plugin_options(configured: str, ptype: str) -> list[dict]:
    """插件目录名下拉：扫到什么列什么，扫不到就退回配置里写的那个"""
    found = list_plugins_by_type(ptype)
    if found:
        return [{"value": p, "label": p} for p in found]
    return [{"value": configured, "label": configured}]


def _llm_group(llm: dict) -> dict:
    return {
        "id": "llm", "title": "大模型 (LLM)", "badge": "LLM",
        "hint": "对话推理引擎。支持 OpenAI 兼容、Ollama 本地推理、Anthropic Claude 三种模式。",
        "fields": [
            _f("llm.mode", "引擎模式", "select", llm.get("mode", "openai"), options=[
                {"value": "openai", "label": "OpenAI 格式"},
                {"value": "ollama", "label": "Ollama 本地推理"},
                {"value": "claude", "label": "Anthropic 格式"},
            ]),

            _f("llm.openai.api_key", "API 密钥", "password", dig(llm, "openai.api_key", ""),
               showIf={"key": "llm.mode", "equals": "openai"},
               placeholder="sk-..."),
            _f("llm.openai.base_url", "API 端点", "text", dig(llm, "openai.base_url", ""),
               showIf={"key": "llm.mode", "equals": "openai"},
               placeholder="https://api.deepseek.com",
               presets=[
                   {"value": "https://api.deepseek.com", "label": "DeepSeek"},
                   {"value": "https://api.openai.com/v1", "label": "OpenAI"},
                   {"value": "http://localhost:8080/v1", "label": "llama.cpp server"},
                   {"value": "http://localhost:1234/v1", "label": "LM Studio"},
                   {"value": "http://localhost:8000/v1", "label": "vLLM"},
               ]),
            _f("llm.openai.model", "模型", "model", dig(llm, "openai.model", ""),
               showIf={"key": "llm.mode", "equals": "openai"}, modelSource="openai"),
            _f("llm.openai.timeout", "请求超时（秒）", "number", dig(llm, "openai.timeout", 60),
               showIf={"key": "llm.mode", "equals": "openai"}, min=1, max=600, step=1),

            _f("llm.ollama.base_url", "Ollama 地址", "text", dig(llm, "ollama.base_url", ""),
               showIf={"key": "llm.mode", "equals": "ollama"},
               placeholder="http://localhost:11434"),
            _f("llm.ollama.model", "模型", "model", dig(llm, "ollama.model", ""),
               showIf={"key": "llm.mode", "equals": "ollama"}, modelSource="ollama"),
            _f("llm.ollama.timeout", "请求超时（秒）", "number", dig(llm, "ollama.timeout", 120),
               showIf={"key": "llm.mode", "equals": "ollama"}, min=1, max=600, step=1),

            _f("llm.claude.api_key", "API 密钥", "password", dig(llm, "claude.api_key", ""),
               showIf={"key": "llm.mode", "equals": "claude"},
               placeholder="sk-ant-..."),
            _f("llm.claude.base_url", "API 端点", "text", dig(llm, "claude.base_url", ""),
               showIf={"key": "llm.mode", "equals": "claude"},
               placeholder="https://api.anthropic.com"),
            _f("llm.claude.model", "模型", "model", dig(llm, "claude.model", ""),
               showIf={"key": "llm.mode", "equals": "claude"}, modelSource="claude"),
            _f("llm.claude.timeout", "请求超时（秒）", "number", dig(llm, "claude.timeout", 120),
               showIf={"key": "llm.mode", "equals": "claude"}, min=1, max=600, step=1),

            _f("llm.openai.default_params.temperature", "生成温度", "slider",
               dig(llm, "openai.default_params.temperature", 0.7),
               showIf={"key": "llm.mode", "equals": "openai"}, min=0, max=2, step=0.05),
            _f("llm.openai.default_params.max_tokens", "最大输出 token", "number",
               dig(llm, "openai.default_params.max_tokens", 2048),
               showIf={"key": "llm.mode", "equals": "openai"}, min=1, max=65536, step=1),
            _f("llm.openai.default_params.top_p", "核采样 top_p", "slider",
               dig(llm, "openai.default_params.top_p", 0.95),
               showIf={"key": "llm.mode", "equals": "openai"}, min=0, max=1, step=0.01),

            _f("llm.ollama.default_params.temperature", "生成温度", "slider",
               dig(llm, "ollama.default_params.temperature", 0.7),
               showIf={"key": "llm.mode", "equals": "ollama"}, min=0, max=2, step=0.05),
            _f("llm.ollama.default_params.max_tokens", "最大输出 token", "number",
               dig(llm, "ollama.default_params.max_tokens", 2048),
               showIf={"key": "llm.mode", "equals": "ollama"}, min=1, max=65536, step=1),
            _f("llm.ollama.default_params.top_p", "核采样 top_p", "slider",
               dig(llm, "ollama.default_params.top_p", 0.95),
               showIf={"key": "llm.mode", "equals": "ollama"}, min=0, max=1, step=0.01),

            _f("llm.claude.default_params.temperature", "生成温度", "slider",
               dig(llm, "claude.default_params.temperature", 0.7),
               showIf={"key": "llm.mode", "equals": "claude"}, min=0, max=2, step=0.05),
            _f("llm.claude.default_params.max_tokens", "最大输出 token（必填）", "number",
               dig(llm, "claude.default_params.max_tokens", 2048),
               showIf={"key": "llm.mode", "equals": "claude"}, min=1, max=65536, step=1),
            _f("llm.claude.default_params.top_p", "核采样 top_p", "slider",
               dig(llm, "claude.default_params.top_p", 0.95),
               showIf={"key": "llm.mode", "equals": "claude"}, min=0, max=1, step=0.01),
        ],
        "test": "llm",
    }


def _agent_group(agent: dict) -> dict:
    return {
        "id": "agent", "title": "人格与代理 (Agent)", "badge": "AGENT",
        "hint": "pi-agent-core sidecar（Node 子进程）。桌宠人格写在这里；"
                "留空则回退到 LLM 配置里的 system_prompt。sidecar 不存第二份 LLM 配置，"
                "密钥由后端启动时以环境变量注入。",
        "fields": [
            _f("agent.enabled", "随后端启动 Agent", "switch", agent.get("enabled", True)),
            _f("agent.system_prompt", "桌宠人格提示词", "textarea",
               agent.get("system_prompt", ""), rows=6,
               placeholder="例：你是一只黏人的桌面宠物，说话简短、口语化，会主动关心主人。"),
            _f("agent.pi_sidecar.base_url", "sidecar 地址", "text",
               dig(agent, "pi_sidecar.base_url", ""), placeholder="http://localhost:8300"),
            _f("agent.pi_sidecar.default_params.temperature", "Agent 温度", "slider",
               dig(agent, "pi_sidecar.default_params.temperature", 0.7), min=0, max=2, step=0.05),
            _f("agent.pi_sidecar.default_params.max_tokens", "Agent 最大输出 token", "number",
               dig(agent, "pi_sidecar.default_params.max_tokens", 2048), min=1, max=65536, step=1),
            _f("agent.pi_sidecar.timeout", "请求超时（秒）", "number",
               dig(agent, "pi_sidecar.timeout", 120), min=1, max=600, step=1),
        ],
        "test": "agent",
        "actions": [{"id": "restart-agent", "label": "重启 sidecar"}],
    }


def _tts_group(tts: dict) -> dict:
    tts_mode = tts.get("mode", "plugin")
    plugin_chars = scan_plugin_characters(tts)
    char_options = [
        {"value": c["voice"], "label": f'{c["voice"]} — {c.get("description") or "本地角色"}'}
        for c in plugin_chars
    ]
    cur_char = dig(tts, "plugin.config.character_name", "")
    if cur_char and cur_char not in [c["value"] for c in char_options]:
        char_options.insert(0, {"value": cur_char, "label": f"{cur_char}（模型目录中未找到）"})

    emotions = []
    for c in plugin_chars:
        if c["voice"] == cur_char:
            emotions = c.get("emotions", [])
            break

    return {
        "id": "tts", "title": "语音合成 (TTS)", "badge": "TTS",
        "hint": "plugin = Genie-TTS 本地插件（独立进程，支持句子级流式）；"
                "edge = 微软在线 TTS；local 是已废弃的进程内旧路径。"
                "配置里的 api 模式未实现，选了会直接抛错，故不在此列出。",
        "fields": [
            _f("tts.mode", "TTS 引擎", "select", tts_mode, options=[
                {"value": "plugin", "label": "Genie-TTS 插件（本地，推荐）"},
                {"value": "edge", "label": "Edge-TTS（微软在线，免费无需密钥）"},
                {"value": "local", "label": "Genie 进程内（已废弃）"},
            ]),

            # plugin
            _f("tts.plugin.config.character_name", "角色", "select", cur_char,
               showIf={"key": "tts.mode", "equals": "plugin"},
               options=char_options, emotions=emotions),
            _f("tts.plugin.name", "插件目录名", "select", dig(tts, "plugin.name", ""),
               showIf={"key": "tts.mode", "equals": "plugin"},
               options=_plugin_options(dig(tts, "plugin.name", ""), "tts")),
            _f("tts.plugin.port", "插件端口", "port", dig(tts, "plugin.port", 8100),
               showIf={"key": "tts.mode", "equals": "plugin"},
               min=1024, max=65535, band=list(PORT_BANDS["tts"]), pluginKey="tts.plugin.name"),
            _f("tts.plugin.timeout", "请求超时（秒）", "number", dig(tts, "plugin.timeout", 120),
               showIf={"key": "tts.mode", "equals": "plugin"}, min=1, max=600, step=1),

            # edge
            _f("tts.edge.voices.zh.voice", "Edge 语音", "edgevoice",
               dig(tts, "edge.voices.zh.voice", ""),
               showIf={"key": "tts.mode", "equals": "edge"},
               note="后端 factories.py 只读 zh 这一条作为默认语音，jp / en 两项仅供参考。"),
            _f("tts.edge.default_params.rate", "语速", "text",
               dig(tts, "edge.default_params.rate", "+0%"),
               showIf={"key": "tts.mode", "equals": "edge"}, placeholder="+0%"),
            _f("tts.edge.default_params.volume", "音量", "text",
               dig(tts, "edge.default_params.volume", "+0%"),
               showIf={"key": "tts.mode", "equals": "edge"}, placeholder="+0%"),
            _f("tts.edge.default_params.pitch", "音调", "text",
               dig(tts, "edge.default_params.pitch", "+0Hz"),
               showIf={"key": "tts.mode", "equals": "edge"}, placeholder="+0Hz"),

            # local
            _f("tts.local.model_base_dir", "角色模型目录", "text",
               dig(tts, "local.model_base_dir", ""),
               showIf={"key": "tts.mode", "equals": "local"}),
            _f("tts.local.data_dir", "GenieData 目录", "text",
               dig(tts, "local.data_dir", ""),
               showIf={"key": "tts.mode", "equals": "local"}),
        ],
        "test": "tts",
        "preview": True,
    }


def _asr_group(asr: dict) -> dict:
    return {
        "id": "asr", "title": "语音识别 (ASR)", "badge": "ASR",
        "hint": "FunASR + SenseVoiceSmall 本地插件，纯本地无需密钥。"
                "默认关闭：模型加载约 13-18 秒会拖慢后端启动。"
                "注意后端还没有 /api/asr/* 路由，开启后暂时只有插件进程在跑。",
        "fields": [
            _f("asr.enabled", "随后端启动 ASR", "switch", asr.get("enabled", False)),
            _f("asr.plugin.name", "插件目录名", "select", dig(asr, "plugin.name", ""),
               options=_plugin_options(dig(asr, "plugin.name", ""), "asr")),
            _f("asr.plugin.base_url", "插件地址", "text", dig(asr, "plugin.base_url", ""),
               placeholder="http://localhost:8400",
               band=list(PORT_BANDS["asr"]), pluginKey="asr.plugin.name"),
            _f("asr.plugin.language", "识别语言", "select", dig(asr, "plugin.language", "auto"),
               options=[
                   {"value": "auto", "label": "自动检测"},
                   {"value": "zh", "label": "中文"},
                   {"value": "en", "label": "English"},
                   {"value": "yue", "label": "粤语"},
                   {"value": "ja", "label": "日本語"},
                   {"value": "ko", "label": "한국어"},
               ]),
            _f("asr.plugin.use_itn", "逆文本标准化 (ITN)", "switch",
               dig(asr, "plugin.use_itn", True)),
            _f("asr.plugin.timeout", "请求超时（秒）", "number",
               dig(asr, "plugin.timeout", 120), min=1, max=600, step=1),
        ],
        "test": "asr",
    }


def _weather_group(weather: dict) -> dict:
    return {
        "id": "weather", "title": "天气 (Weather)", "badge": "WTH",
        "hint": "和风天气 QWeather Ed25519 私钥自动签发 JWT。"
                "启用后前端通过浏览器 GPS/WiFi 获取模糊位置，自动切换房间背景（晴/雨/雪）与日出日落时间段。",
        "fields": [
            _f("weather.enabled", "启用天气服务", "switch", weather.get("enabled", False)),
            _f("weather.private_key", "Ed25519 私钥", "password",
               weather.get("private_key", ""),
               placeholder="-----BEGIN PRIVATE KEY-----"),
            _f("weather.kid", "凭据 ID（kid）", "text",
               weather.get("kid", ""),
               placeholder="控制台 -> 项目管理 -> 凭据 中查看"),
            _f("weather.sub", "项目 ID（sub）", "text",
               weather.get("sub", ""),
               placeholder="控制台 -> 项目管理 中查看"),
            _f("weather.api_host", "API 主机", "text",
               weather.get("api_host", ""),
               placeholder="控制台 -> 设置 中查看，直接复制即可（自动补 https://）"),
            _f("weather.timeout", "请求超时（秒）", "number",
               weather.get("timeout", 10), min=1, max=60, step=1),
        ],
        "test": "weather",
    }


def get_schema() -> dict:
    """构造简单视图的分组表单，值从 config.yaml 现读"""
    return {"groups": [
        _llm_group(read_yaml(CONFIG_PATHS["llm"])),
        _agent_group(read_yaml(CONFIG_PATHS["agent"])),
        _tts_group(read_yaml(CONFIG_PATHS["tts"])),
        _asr_group(read_yaml(CONFIG_PATHS["asr"])),
        _weather_group(read_yaml(CONFIG_PATHS["weather"])),
    ]}

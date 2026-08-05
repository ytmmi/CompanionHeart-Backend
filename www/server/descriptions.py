"""配置项的中文描述表 —— 高级视图的标签来源，简单视图的字段说明也取自这里。

纯数据模块，不引入任何其他 server 子模块。
"""
from __future__ import annotations

KEY_DESCRIPTIONS = {
    # ── LLM ──
    "llm.mode": "当前激活的 LLM 引擎模式（openai / ollama）",
    "llm.openai.base_url": "OpenAI 兼容 API 端点地址",
    "llm.openai.api_key": "API 密钥",
    "llm.openai.model": "使用的模型名称",
    "llm.openai.timeout": "请求超时时间（秒）",
    "llm.openai.default_params.temperature": "生成温度，越高输出越随机（0~2）",
    "llm.openai.default_params.max_tokens": "单次回复最大 token 数",
    "llm.openai.default_params.top_p": "核采样阈值（0~1）",
    "llm.openai.system_prompt": "系统提示词，定义 AI 角色行为",
    "llm.ollama.base_url": "Ollama 本地推理服务地址",
    "llm.ollama.model": "Ollama 使用的本地模型名称",
    "llm.ollama.timeout": "请求超时时间（秒）",
    "llm.ollama.default_params.temperature": "生成温度，越高输出越随机（0~2）",
    "llm.ollama.default_params.max_tokens": "单次回复最大 token 数",
    "llm.ollama.default_params.top_p": "核采样阈值（0~1）",
    "llm.ollama.system_prompt": "系统提示词，定义 AI 角色行为",

    # ── Agent ──
    "agent.mode": "Agent 引擎模式（pi_sidecar / basic）",
    "agent.enabled": "是否随后端启动 Agent sidecar 插件",
    "agent.pi_sidecar.plugin_name": "Agent sidecar 在 custom_plugin/ 下的目录名",
    "agent.pi_sidecar.base_url": "Agent sidecar HTTP 服务地址",
    "agent.pi_sidecar.timeout": "Agent 请求超时时间（秒）",
    "agent.pi_sidecar.default_params.temperature": "Agent 采样温度（0~2），pi-ai 不支持 top_p",
    "agent.pi_sidecar.default_params.max_tokens": "Agent 单次最大输出 token 数",
    "agent.system_prompt": "桌宠人格提示词，留空则回退到 LLM 配置的 system_prompt",

    # ── TTS ──
    "tts.mode": "当前 TTS 引擎模式（edge / local / plugin）",
    "tts.local.data_dir": "GenieData 资源目录路径",
    "tts.local.model_base_dir": "角色模型根目录路径",
    "tts.local.output_dir": "默认输出音频目录",
    "tts.local.default_params.split_sentence": "是否按分句合成（false=整段合成）",
    "tts.local.default_params.play": "是否合成后自动播放",
    "tts.api.base_url": "远程 TTS 服务地址（api 模式未实现）",
    "tts.api.timeout": "远程 TTS 请求超时时间（秒）",
    "tts.edge.output_dir": "Edge-TTS 输出音频目录",
    "tts.edge.voices.jp.voice": "日语语音标识",
    "tts.edge.voices.zh.voice": "中文语音标识（factories.py 实际只读这一条）",
    "tts.edge.voices.en.voice": "英文语音标识",
    "tts.edge.default_params.rate": "默认语速（-50% ~ +50%）",
    "tts.edge.default_params.volume": "默认音量（-50% ~ +50%）",
    "tts.edge.default_params.pitch": "默认音调（-50Hz ~ +50Hz）",
    "tts.plugin.name": "TTS 插件目录名（custom_plugin/ 下）",
    "tts.plugin.port": "TTS 插件 HTTP 服务端口（8100-8199）",
    "tts.plugin.timeout": "TTS 插件请求超时时间（秒）",
    "tts.plugin.config.character_name": "插件默认角色名称",

    # ── ASR ──
    "asr.mode": "ASR 引擎模式（plugin）",
    "asr.enabled": "是否随后端启动 ASR 插件（模型加载约 13-18 秒，会拖慢启动）",
    "asr.plugin.name": "ASR 插件目录名（custom_plugin/ 下）",
    "asr.plugin.base_url": "ASR 插件 HTTP 服务地址",
    "asr.plugin.timeout": "ASR 请求超时时间（秒）",
    "asr.plugin.language": "识别语言（auto / zh / en / yue / ja / ko）",
    "asr.plugin.use_itn": "逆文本标准化（数字、日期转为书写形式）",
}

# 逐角色的描述按模板生成，不再手写死
for _c, _d in (("mika", "聖園ミカ / 蔚蓝档案"), ("feibi", "菲比 / 鸣潮"), ("thirtyseven", "37 / 重返未来1999")):
    KEY_DESCRIPTIONS[f"tts.local.characters.{_c}.name"] = f"本地角色标识：{_c}"
    KEY_DESCRIPTIONS[f"tts.local.characters.{_c}.language"] = f"本地角色语言（{_d}）"
    KEY_DESCRIPTIONS[f"tts.local.characters.{_c}.description"] = f"本地角色描述：{_d}"
    KEY_DESCRIPTIONS[f"tts.local.characters.{_c}.prompt_wav"] = "参考音频文件名"
    KEY_DESCRIPTIONS[f"tts.local.characters.{_c}.prompt_text"] = "参考音频对应文本"

for _lang, _name in (("jp", "日语"), ("zh", "中文"), ("en", "英文")):
    KEY_DESCRIPTIONS.setdefault(f"tts.edge.voices.{_lang}.language", f"{_name}语言代码")
    KEY_DESCRIPTIONS.setdefault(f"tts.edge.voices.{_lang}.description", f"{_name}语音描述")

for _ep, _desc in (
    ("load_character", "加载角色"), ("set_reference_audio", "设置参考音频"),
    ("tts", "语音合成"), ("unload_character", "卸载角色"),
    ("stop", "停止合成"), ("clear_cache", "清空参考音频缓存"),
):
    KEY_DESCRIPTIONS[f"tts.api.endpoints.{_ep}"] = f"{_desc}接口路径"

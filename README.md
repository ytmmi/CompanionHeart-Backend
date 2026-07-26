# CompanionHeart-Backend

> AI 陪伴助手后端服务 · Python FastAPI

**CompanionHeart-Backend** 是 AI 陪伴助手（桌宠）的后端服务，提供 Agent 代理对话、LLM 对话、TTS 语音合成、ASR 语音识别、会话管理与插件系统。与前端 [CompanionHeart-UI](https://github.com/ytmmi/CompanionHeart-UI)（Tauri + React）完全分离，通过 HTTP REST API 通信。


---

## 功能一览

| 模块         | 状态    | 说明                                                                 |
| ------------ | ------- | -------------------------------------------------------------------- |
| Agent 代理   | ✅      | [pi](https://github.com/earendil-works/pi) 代理引擎（工具调用 + agent loop），Node sidecar 无状态服务；记忆由后端管理 |
| LLM 对话     | ✅      | OpenAI 兼容 / Ollama / DeepSeek / Claude / Gemini 多引擎，流式 + 非流式 |
| TTS 语音合成 | ✅      | EdgeTTS（在线）/ GenieTTS（本地 ONNX）/ 插件模式，非流式 + 流式 + 句子级同步流式 |
| TTS 启用开关 | ✅      | 前端控制 `/api/voice/tts/enabled`，禁用时合成端点 403 不路由引擎     |
| ASR 语音识别 | ✅      | FunASR + SenseVoiceSmall（本地 CPU 推理，多语言），**情感/事件作为独立信号**；暂未接入 API 层 |
| 会话管理     | ✅      | `/api/conversations` 多对话上下文（JSON 文件持久化）                 |
| 插件系统     | ✅      | 本地部署模型以独立进程插件运行（见 `PLUGIN_IMPLEMENTATION.md`）      |
| 长期记忆     | 📋 待开发 | `MemoryProvider` 协议已就位，实现同协议即插即用                    |
| MCP / Live2D | 📋 待开发 | MCP 工具接入、Live2D 动作驱动                                      |

> **路由收敛计划**：`/api/agent/*` 与 `/api/llm/*` 过渡期并存（SSE 格式完全兼容），
> Agent 稳定后将收敛掉 `/api/llm/*`。前端默认已走 `/api/agent/*`。

---

## 快速开始

### 1. 环境准备

- Python 3.10+（当前开发环境 3.13）
- **Node.js 22+**（Agent sidecar 需要；发行版可用 bun 编译独立二进制免除此依赖）
- 创建虚拟环境并安装依赖：

```powershell
cd CompanionHeart-Backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Agent sidecar 依赖（pi-agent-core，版本已 pin）
cd custom_plugin\AGENT_pi
npm install --ignore-scripts
cd ..\..
```

> **ASR 依赖有两个坑**（详见 `custom_plugin/ASR_funasr/requirements.txt`）：
> `funasr` 在清华镜像上没有，需从 PyPI 官方源装；装完后它会把 `onnxruntime`
> 升到 1.27 **破坏 genie-tts**，必须回退 `onnxruntime==1.22.1`。

### 2. 配置

配置文件位于 `app/configs/`，按模块拆分（详见 `tests/参考文档/CONFIG.md`）：

```
app/configs/
├── llm/config.yaml    # LLM 引擎与 API Key（复制 config.example.yaml 修改）
├── tts/config.yaml    # TTS 引擎模式（edge / local / plugin）
├── agent/config.yaml  # Agent 引擎（pi_sidecar），LLM 配置复用 llm/config.yaml
└── asr/config.yaml    # ASR 引擎（plugin），默认 enabled: false
```

**LLM 配置单一真源**：Agent sidecar 不维护第二份 LLM 配置，后端启动它时
把 `llm/config.yaml` 翻译成环境变量注入子进程（API Key 不落盘、不进命令行）。


### 3. 启动服务

```powershell
$env:PYTHONPATH = "E:\CompanionHeart\CompanionHeart-Backend"
.venv\Scripts\uvicorn app.main:app --reload --port 18000
```

服务默认监听 `http://127.0.0.1:18000`（前端默认连接此地址）。
启动时插件系统会按配置自动拉起 TTS / Agent 插件子进程。

验证：

```powershell
curl http://127.0.0.1:18000/api/health
# {"status": "ok", "service": "CompanionHeart"}

curl http://127.0.0.1:18000/api/agent/status
# {"engine":"pisidecar","pi_version":"0.82.1","provider":"deepseek",
#  "model":"deepseek-v4-flash","tools":["get_time"],"sidecar_healthy":true,...}
```

---

## API 端点

完整文档见 [`tests/参考文档/API.md`](tests/参考文档/API.md)。

| 方法 | 端点                              | 说明                                     |
| ---- | --------------------------------- | ---------------------------------------- |
| GET  | `/api/health`                     | 健康检查                                 |
| GET  | `/api/state`                      | 服务状态                                 |
| GET  | `/api/agent/status`               | Agent 引擎状态（sidecar 健康度/模型/工具/能力标志） |
| GET  | `/api/agent/tools`                | Agent 可用工具列表                       |
| POST | `/api/agent/chat`                 | Agent 非流式对话（回复 + 工具调用摘要）  |
| POST | `/api/agent/chat/stream`          | Agent 流式对话（SSE，与 `/api/llm/chat/stream` 格式兼容） |
| POST | `/api/agent/chat/stream/sentences`| Agent 句子级流式（NDJSON，文本+TTS 音频成对） |
| POST | `/api/agent/abort`                | 中断进行中的 Agent 对话                  |
| POST | `/api/agent/restart`              | 重启 Agent sidecar 子进程                |
| GET  | `/api/llm/models`                 | 可用模型列表                             |
| GET  | `/api/llm/status`                 | LLM 引擎状态                             |
| POST | `/api/llm/chat`                   | 非流式对话（无状态 / 会话两种模式）      |
| POST | `/api/llm/chat/stream`            | 流式对话（SSE）                          |
| GET  | `/api/voice/tts/voices`           | 语音/角色列表                            |
| GET  | `/api/voice/tts/status`           | TTS 引擎状态                             |
| GET  | `/api/voice/tts/enabled`          | 查询 TTS 是否启用                        |
| POST | `/api/voice/tts/enabled`          | 设置 TTS 启用/禁用（禁用时合成端点 403） |
| POST | `/api/voice/tts`                  | 非流式语音合成（EdgeTTS→MP3 / GenieTTS→WAV） |
| POST | `/api/voice/tts/stream`           | 流式语音合成（逐 chunk）                 |
| POST | `/api/voice/tts/stream/sentences` | 句子级同步流式合成（NDJSON，文本+音频成对，语音-文字严格同步） |
| POST | `/api/conversations`              | 开启新对话                               |
| GET  | `/api/conversations`              | 历史对话列表                             |
| GET  | `/api/conversations/{id}`         | 对话完整消息记录                         |
| PATCH | `/api/conversations/{id}`        | 重命名对话                               |
| DELETE | `/api/conversations/{id}`       | 删除对话                                 |

---

## 项目结构

```
CompanionHeart-Backend/
├── app/
│   ├── main.py            # FastAPI 入口（CORS、路由注册、插件生命周期、sidecar env 注入）
│   ├── api/               # API 路由层（agent / llm / tts / conversations）
│   ├── agent/             # Agent 引擎（base + factories + memory_provider + pi_sidecar/）
│   ├── llm/               # LLM 引擎（base + factories + 各引擎实现）
│   ├── tts/               # TTS 引擎（EdgeTTS / GenieTTS / 插件客户端）
│   ├── asr/               # ASR 引擎（base + factories + 插件客户端，情感信号）
│   ├── memory/            # 会话存储（short_term：JSON 文件持久化）
│   ├── plugins/           # 插件系统（扫描/注册/启动/HTTP 客户端）
│   ├── configs/           # YAML 配置（agent / llm / tts / asr）
│   ├── models/            # AI 模型资源（GenieTTS ONNX 等）
│   ├── utils/             # 通用工具（sentence.py 增量分句器）
│   └── live2d|mcp|skills/ # 待开发模块
├── custom_plugin/         # 本地插件（独立进程服务）
│   ├── AGENT_pi/          #   pi-agent-core sidecar（Node/TS，端口 8300）
│   ├── TTS_genie_tts/     #   Genie-TTS ONNX（Python，端口 8100）
│   ├── ASR_funasr/        #   FunASR + SenseVoice（Python，端口 8400）
│   └── .logs/             #   插件子进程日志（stdout/stderr 落盘）
├── tests/                 # 测试用例与项目文档
│   ├── agent/  asr/  llm/  llm-tts/  tts/  plugins/   # 各模块测试
│   └── 参考文档/          # 📚 API.md / CONFIG.md / 项目规范 / 开发者指南
├── PLUGIN_IMPLEMENTATION.md  # 插件系统实现说明
├── requirements.txt          # 依赖列表
└── requirements-plugin.txt   # 插件宿主最小依赖
```

**插件端口段约定**：TTS `8100-8199` / LLM `8200-8299` / Agent `8300-8399` / ASR `8400-8499`

---

## 与前端的协作

```
┌─────────────────────┐        HTTP REST           ┌──────────────────────┐
│  CompanionHeart-UI  │ ────────────────────────►  │ CompanionHeart-      │
│  (Tauri + React)    │    WebSocket（规划中）     │ Backend (FastAPI)    │
└─────────────────────┘                            └──────────────────────┘
```

- 前端聊天管线：`POST /api/agent/chat` → `POST /api/voice/tts/stream/sentences`（句子级同步，引擎不支持时回退 `/api/voice/tts`）
  - 也可一步到位用 `POST /api/agent/chat/stream/sentences`（后端内部完成分句 + TTS，文本与音频成对流出）
- 对话引擎切换：前端 `VITE_CHAT_ENGINE`（`agent` 默认 / `llm` 回退），两者 SSE 格式兼容
- TTS 开关：前端以 localStorage 持久化为准，启动时 `POST /api/voice/tts/enabled` 同步（后端开关为进程内状态，重启复位）
- 前端可用 `VITE_API_BASE_URL` 覆盖后端地址（默认 `http://127.0.0.1:18000`）

---

## 测试

```powershell
# 需先启动后端（API / 端到端测试）或配置好引擎（模块测试）
.venv\Scripts\python tests\llm\test_llm_module.py
.venv\Scripts\python tests\tts\test_tts_module.py
.venv\Scripts\python tests\plugins\test_basic.py

# Agent：协议单测（fake sidecar，无需真实 sidecar）
.venv\Scripts\python -X utf8 tests\agent\test_agent_module.py
# Agent：端到端（需后端 + sidecar + 有效 API Key）
.venv\Scripts\python -X utf8 tests\agent\test_agent_integration.py
.venv\Scripts\python -X utf8 tests\agent\test_phase2_e2e.py

# ASR：自行启停插件子进程，用 TTS 合成的已知文本音频做闭环
.venv\Scripts\python -X utf8 tests\asr\test_asr_module.py
```

> 中文输出请加 `-X utf8`，否则 Windows GBK 控制台会乱码。

---

## 文档索引

| 文档                              | 说明                             |
| --------------------------------- | -------------------------------- |
| `tests/参考文档/API.md`           | 完整 API 接口文档                |
| `tests/参考文档/CONFIG.md`        | 配置系统说明                     |
| `tests/参考文档/项目规范.md`      | 开发规范                         |
| `tests/参考文档/开发者指南.md`    | 开发者入门指南                   |
| `tests/项目介绍.md`               | 项目现状与结构详述               |
| `PLUGIN_IMPLEMENTATION.md`        | 插件系统实现总结                 |

---

## 参考项目

- [pi](https://github.com/earendil-works/pi) — Agent harness，本项目用其 `pi-agent-core` + `pi-ai` 作代理引擎
- [Genie-TTS](https://github.com/High-Logic/Genie-TTS) — GPT-SoVITS 轻量推理引擎
- [FunASR](https://github.com/modelscope/FunASR) / [SenseVoice](https://github.com/FunAudioLLM/SenseVoice) — 语音识别（多语言 + 情感/事件标签）

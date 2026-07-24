# CompanionHeart-Backend

> AI 陪伴助手后端服务 · Python FastAPI

**CompanionHeart-Backend** 是 AI 陪伴助手（桌宠）的后端服务，提供 LLM 对话、TTS 语音合成、会话管理与插件系统。与前端 [CompanionHeart-UI](https://github.com/ytmmi/CompanionHeart-UI)（Tauri + React）完全分离，通过 HTTP REST API 通信。


---

## 功能一览

| 模块         | 状态    | 说明                                                                 |
| ------------ | ------- | -------------------------------------------------------------------- |
| LLM 对话     | ✅      | OpenAI 兼容 / Ollama / DeepSeek / Claude / Gemini 多引擎，流式 + 非流式 |
| TTS 语音合成 | ✅      | EdgeTTS（在线）/ GenieTTS（本地 ONNX）/ 插件模式，非流式 + 流式 + 句子级同步流式 |
| TTS 启用开关 | ✅      | 前端控制 `/api/voice/tts/enabled`，禁用时合成端点 403 不路由引擎     |
| 会话管理     | ✅      | `/api/conversations` 多对话上下文（JSON 文件持久化）                 |
| 插件系统     | ✅      | 本地部署模型以独立进程插件运行（见 `PLUGIN_IMPLEMENTATION.md`）      |
| ASR 语音识别 | 📋 待开发 | Whisper / SenseVoice                                               |
| Agent / MCP  | 📋 待开发 | 工具调用、电脑控制                                                 |

---

## 快速开始

### 1. 环境准备

- Python 3.10+
- 创建虚拟环境并安装依赖：

```powershell
cd CompanionHeart-Backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 2. 配置

配置文件位于 `app/configs/`，按模块拆分（详见 `tests/参考文档/CONFIG.md`）：

```
app/configs/
├── llm/config.yaml    # LLM 引擎与 API Key（复制 config.example.yaml 修改）
└── tts/config.yaml    # TTS 引擎模式（edge / local / plugin）
```


### 3. 启动服务

```powershell
$env:PYTHONPATH = "E:\CompanionHeart\CompanionHeart-Backend"
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

服务默认监听 `http://127.0.0.1:8000`（前端默认连接此地址）。

验证：

```powershell
curl http://127.0.0.1:8000/api/health
# {"status": "ok", "service": "CompanionHeart"}
```

---

## API 端点

完整文档见 [`tests/参考文档/API.md`](tests/参考文档/API.md)。

| 方法 | 端点                              | 说明                                     |
| ---- | --------------------------------- | ---------------------------------------- |
| GET  | `/api/health`                     | 健康检查                                 |
| GET  | `/api/state`                      | 服务状态                                 |
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
│   ├── main.py            # FastAPI 入口（CORS、路由注册、插件生命周期）
│   ├── api/               # API 路由层（llm / tts / conversations）
│   ├── llm/               # LLM 引擎（base + factories + 各引擎实现）
│   ├── tts/               # TTS 引擎（EdgeTTS / GenieTTS / 插件客户端）
│   ├── memory/            # 会话存储（short_term：JSON 文件持久化）
│   ├── plugins/           # 插件系统（扫描/注册/启动/HTTP 客户端）
│   ├── configs/           # YAML 配置（llm / tts）
│   ├── models/            # AI 模型资源（GenieTTS ONNX 等）
│   └── agent|asr|live2d|mcp|skills|utils/  # 待开发模块
├── custom_plugin/         # 本地插件（TTS_genie_tts：独立进程 FastAPI 服务）
├── tests/                 # 测试用例与项目文档
│   ├── llm/  llm-tts/  tts/  plugins/      # 各模块测试
│   └── 参考文档/          # 📚 API.md / CONFIG.md / 项目规范 / 开发者指南
├── PLUGIN_IMPLEMENTATION.md  # 插件系统实现说明
├── requirements.txt          # 依赖列表
└── requirements-plugin.txt   # 插件宿主最小依赖
```

---

## 与前端的协作

```
┌─────────────────────┐        HTTP REST           ┌──────────────────────┐
│  CompanionHeart-UI  │ ────────────────────────►  │ CompanionHeart-      │
│  (Tauri + React)    │    WebSocket（规划中）     │ Backend (FastAPI)    │
└─────────────────────┘                            └──────────────────────┘
```

- 前端聊天管线：`POST /api/llm/chat` → `POST /api/voice/tts/stream/sentences`（句子级同步，引擎不支持时回退 `/api/voice/tts`）
- TTS 开关：前端以 localStorage 持久化为准，启动时 `POST /api/voice/tts/enabled` 同步（后端开关为进程内状态，重启复位）
- 前端可用 `VITE_API_BASE_URL` 覆盖后端地址（默认 `http://127.0.0.1:8000`）

---

## 测试

```powershell
# 需先启动后端（API 测试）或配置好引擎（模块测试）
.venv\Scripts\python tests\llm\test_llm_module.py
.venv\Scripts\python tests\tts\test_tts_module.py
.venv\Scripts\python tests\plugins\test_basic.py
```

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

- [Genie-TTS](https://github.com/High-Logic/Genie-TTS) — GPT-SoVITS 轻量推理引擎

# CompanionHeart 插件系统实现总结

## ✅ 已完成

### 1. 插件系统核心模块 (`app/plugins/`)
- ✅ `base.py` - 插件元数据模型（Plugin, PluginServiceConfig, PluginAPIConfig）
- ✅ `manager.py` - 插件管理器（扫描、注册、启动、停止）
- ✅ `installer.py` - Git安装器（依赖安装到项目.venv）
- ✅ `client.py` - HTTP客户端基类

### 2. TTS插件客户端
- ✅ `app/tts/plugin_client.py` - TTS插件HTTP客户端
- ✅ `app/tts/factories.py` - 工厂支持plugin模式
- ✅ `app/tts/__init__.py` - 导出TTSPluginClient

### 3. Genie-TTS插件 (`custom_plugin/TTS_genie_tts/`)
- ✅ `plugin.yaml` - 插件元数据
- ✅ `requirements.txt` - 依赖列表
- ✅ `server.py` - FastAPI HTTP服务
- ✅ `engine.py` - 引擎实现（从app/tts/genie_tts迁移）
- ✅ `README.md` - 使用说明

### 4. 后端集成
- ✅ `app/main.py` - 添加插件扫描和启动逻辑
- ✅ `app/configs/tts/config.yaml` - 添加plugin配置段
- ✅ 启动/关闭事件处理
- ✅ 优雅退出清理

### 5. 测试脚本
- ✅ `tests/plugins/test_basic.py` - 基础功能测试
- ✅ `tests/plugins/test_plugin_system.py` - 完整集成测试

### 6. 文档
- ✅ `custom_plugin/README.md` - 插件系统使用指南
- ✅ `custom_plugin/TTS_genie_tts/README.md` - 插件说明

---

## 📋 使用步骤

### 方式1：使用Edge-TTS（在线，默认）
保持配置 `mode: "edge"`，无需任何更改即可使用。

### 方式2：使用Genie-TTS插件（本地部署）

#### 步骤1：安装插件依赖
```powershell
cd E:\CompanionHeart\CompanionHeart-Backend
.venv\Scripts\pip install httpx
.venv\Scripts\pip install -r custom_plugin\TTS_genie_tts\requirements.txt
```

#### 步骤2：设置环境变量
```powershell
$env:GENIE_DATA_DIR = "E:\CompanionHeart\CompanionHeart-Backend\app\models\tts\Genie\GenieData"
```

#### 步骤3：修改配置
编辑 `app/configs/tts/config.yaml`：
```yaml
mode: "plugin"
```

#### 步骤4：启动后端
```powershell
cd CompanionHeart-Backend
$env:PYTHONPATH = "E:\CompanionHeart\CompanionHeart-Backend"
.venv\Scripts\uvicorn app.main:app --reload --port 8000
```

后端会自动：
1. 扫描 `custom_plugin/` 目录
2. 加载 `TTS_genie_tts` 插件配置
3. 启动插件HTTP服务（端口8100）
4. 等待健康检查通过

#### 步骤5：测试API
```bash
# 健康检查
curl http://127.0.0.1:8000/api/health

# 获取语音列表
curl http://127.0.0.1:8000/api/voice/tts/voices

# 合成语音
curl -X POST http://127.0.0.1:8000/api/voice/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"你好世界","character_name":"feibi"}' \
  -o output.wav
```

---

## 🧪 测试

### 基础功能测试（不需要启动后端）
```powershell
cd CompanionHeart-Backend
.venv\Scripts\python tests\plugins\test_basic.py
```

测试内容：
- 插件扫描
- 插件配置加载
- TTS工厂配置解析
- 配置文件读取

### 完整集成测试（需要依赖和环境变量）
```powershell
cd CompanionHeart-Backend
$env:GENIE_DATA_DIR = "E:\CompanionHeart\CompanionHeart-Backend\app\models\tts\Genie\GenieData"
.venv\Scripts\python tests\plugins\test_plugin_system.py
```

测试内容：
- 插件管理器（启动/停止）
- HTTP客户端通信
- TTS插件客户端
- TTS工厂集成

---

## 🔧 架构说明

### 职责分工
| 组件 | 职责 | 通信方式 |
|------|------|---------|
| `app/tts/edge_tts/` | 在线Edge-TTS | 直接调用 |
| `app/llm/openai_llm/` | 在线OpenAI API | HTTP API |
| `app/llm/ollama/` | Ollama客户端 | HTTP API |
| `custom_plugin/TTS_genie_tts/` | 本地Genie-TTS | HTTP (独立进程) |

### 通信流程
```
用户请求
  ↓
FastAPI (/api/voice/tts)
  ↓
TTSFactory.create_from_config()
  ↓
[mode=plugin] → TTSPluginClient
  ↓
HTTP请求 → http://localhost:8100/synthesize
  ↓
插件进程 (server.py)
  ↓
GenieTTS引擎 (engine.py)
  ↓
返回音频数据
```

### 依赖管理
- **所有依赖统一安装到项目 `.venv`**
- 插件不创建独立虚拟环境
- 启动插件时使用项目Python解释器

---

## 🚀 下一步（可选）

### 1. LLM插件支持
- [ ] 创建 `app/llm/plugin_client.py`
- [ ] 修改 `app/llm/factories.py` 支持plugin模式
- [ ] 创建示例LLM插件（如本地模型推理）

### 2. 插件热重载
- [ ] 监听插件目录变化
- [ ] 支持不重启后端更新插件

### 3. 插件管理API
- [ ] `POST /api/plugins/install` - 从Git安装插件
- [ ] `GET /api/plugins` - 列出所有插件
- [ ] `POST /api/plugins/{name}/start` - 启动插件
- [ ] `POST /api/plugins/{name}/stop` - 停止插件

### 4. 插件依赖隔离（如果需要）
- [ ] 为每个插件创建独立虚拟环境
- [ ] 修改启动逻辑使用插件自己的Python

---

## 📝 注意事项

1. **端口冲突**：
   - TTS插件：8100-8199
   - LLM插件：8200-8299
   - 确保端口不被占用

2. **环境变量**：
   - Genie-TTS需要 `GENIE_DATA_DIR`
   - 每次启动后端前需要设置

3. **首次加载慢**：
   - Genie-TTS首次加载ONNX模型需要30-60秒
   - 插件健康检查等待时间已设置为30秒

4. **依赖安装**：
   - 必须先安装 `httpx`
   - 插件依赖安装到项目 `.venv`

5. **保留现有功能**：
   - Edge-TTS仍然可用（`mode: "edge"`）
   - 原有 `app/tts/genie_tts/` 保留（未删除）

---

## ✨ 亮点

1. **职责清晰**：在线服务直接调用，本地模型用插件
2. **易于扩展**：新增插件只需添加目录
3. **统一依赖**：简化管理，减少磁盘占用
4. **透明切换**：API层无感知，通过配置切换引擎
5. **进程隔离**：插件崩溃不影响主进程

---

生成时间: 2026-07-19

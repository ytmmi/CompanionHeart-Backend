# AGENT_work

CompanionHeart 的独立工作 Agent sidecar。协议端点为 `health/info/run/abort`。

- 不导入生活记忆或陪伴会话代码；
- 生产默认不注册任何任务工具；
- 插件工具白名单与每个 `WorkCommand.allowed_capabilities` 取交集；
- `WORK_AGENT_ENABLE_TEST_TOOLS=1` 只用于开启无副作用的 `test.echo` 协议测试工具；
- 请求正文和开发密钥不写日志。

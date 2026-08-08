# MEMORY_omni

`MEMORY_omni` 是 `OmniMemoryOrchestrator` 在 CompanionHeart 后端中的插件化移植。
它以独立 HTTP 进程运行，但使用后端当前 Python 解释器和项目环境。

当前实现为文本长期记忆基线：

- `add_text` 将对话文本规范化、拆分为原子记忆单元并持久化；
- `query` 在当前角色/用户 namespace 内进行词法相关性检索；
- 对可识别的偏好事实保存 `fact_key/fact_value`，并输出 `[现在事实]`、`[过去事实]`、`[待确认事实]`；高置信冲突会生成版本链，低置信冲突不会覆盖当前事实；
- 文本请求支持 `fact_states` 过滤和 `effective_at` 日期；修订请求支持幂等键；
- `delete` 和 `delete_scope` 提供基础治理能力；
- 记录采用 `companionheart.memory.mau.v1` JSONL 标准文本文件，位于后端注入的
  `app/memory/data_memory/<role_name_en>/life/<user_namespace>/text/`；
- 插件启动时从标准文件恢复索引，不在 `app/memory/` 内实现记忆分类、抽取或检索。

后续可在不改变 HTTP 契约的前提下替换为上游 Omni-SimpleMem 的向量、BM25、事件和
多模态处理器。工作记忆不进入此插件。

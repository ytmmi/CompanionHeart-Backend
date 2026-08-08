# 角色配置

每个陪伴角色使用一个独立 YAML，文件名必须与 `name_en` 一致，例如
`akari.yaml`。`name_en` 同时是该角色在
`app/memory/data_memory/<name_en>/` 下的记忆目录名。

必须遵守：

- `name_en` 以 ASCII 字母开头，只包含字母、数字、`_`、`-`；
- 英文名大小写不敏感唯一；
- 所有角色中最多一个 `default: true`；
- 同一角色可以配置多个 Live2D 模型，但最多一个默认模型；
- TTS 配置只引用引擎和音色，不在角色文件保存 API Key；
- `.example.yaml` 仅作模板，不会被角色扫描器加载。

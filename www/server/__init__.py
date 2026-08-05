"""
CompanionHeart 设置服务（端口 17999）

按职责拆分的模块：

  paths            路径 / 端口段 / 日志等全局常量
  yaml_patch       保留注释的 YAML 行级标量写入器
  yaml_io          YAML 读取与扁平化、类型归一化
  descriptions     配置项中文描述表
  backups          备份 / 恢复 / 重置为 example
  ports            端口探测与端口段校验
  http_client      轻量 HTTP 请求封装
  config_io        扁平 key 的批量读写、插件端口同步
  schema           「简单视图」分组表单构造
  voices           角色 / 微软语音库 / 模型列表
  preview          TTS 试听合成
  diagnostics      服务状态灯与连接测试
  jobs             后台任务（安装 / 启动）的流式日志
  process_utils    按端口反查 PID / 结束进程
  plugins_registry 插件扫描、状态汇总、日志读取
  plugins_install  从 Git / 本地目录安装插件
  plugins_runtime  插件启动 / 停止 / 卸载
  http_api         HTTP 路由与请求处理
  main             服务入口
"""

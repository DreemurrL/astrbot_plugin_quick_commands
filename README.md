# AstrBot 快捷指令管理 · v1.0.2

适用：AstrBot v4.29.0+，包括 v4.29.1；在 QQ 官方机器人 qq_official 和 OneBot 中使用（其他 AstrBot 平台通常也可收到普通文字）。

## v1.0.2 新增：每条规则可选免斜杠触发

在「扩展功能 → 快捷指令管理 → 编辑快捷指令」勾选 **允许省略 / 直接触发**。
例如新建主指令 `kfc`，回复 `疯狂星期四 v我50`：

- `/kfc` → `疯狂星期四 v我50`
- `kfc` → `疯狂星期四 v我50`（仅勾选此开关时）
- `今天想吃kfc` 不匹配：采用精确关键词规则
- 默认不勾选，**老数据保持仅 `/` 触发**；别名享有同一开关
- 如果勾选「允许附带参数」，`kfc abc` 才能触发，并可使用 `{args}`。

关键改进：增加 AstrBot 原生 `CustomFilter` 唤醒过滤器，在 waking check 阶段匹配当前动态规则；
只匹配已启用且权限、参数均满足的指令，不匹配的群聊消息不会因为这个插件而唤醒 AI。
继续从 `event.get_messages()` 中读取 Plain 原始消息文本，兼容 v4.29.1 对唤醒前缀的处理。

## 升级说明

从 v1.0.1 安装同名插件的更新包，**不要删除** `data/plugin_data/astrbot_plugin_quick_commands/shortcuts.json`。
既有规则保留；`allow_no_slash` 的默认值为 `false`。建议升级前备份数据。


## 安装

1. AstrBot WebUI → 插件 → 已安装 → 安装插件 (+) → 从文件安装，上传 ZIP。
2. 若 WebUI 未立即显示侧栏，刷新整个页面，或在插件卡片详情里打开「快捷指令管理」视图。
3. 左栏 **扩展功能 → 快捷指令管理**，点击 **新建指令**。
4. 「主指令」输入 `插件`，「别名」输入 `功能`；回复内容填写固定文本，或导入 UTF-8 TXT 文件；保存即可。
5. 在 QQ 发送 `/插件` 或 `/功能`，获得相同回复。

## 功能

- 指令可视化添加、编辑、删除、启用、停用；支持每条最多 12 个别名。
- 选择固定文本或导入 UTF-8 的 `.txt` 文件作为回复；内容保存在 AstrBot plugin_data 的 `shortcuts.json`，不是对原 TXT 路径建立实时引用。
- 可设置仅 AstrBot 管理员使用，或允许额外参数，回复中用 `{args}` 占位。
- 每条快捷指令可独立开启「允许省略 /」，包括该指令的别名。默认关闭；关键词必须在整条消息中精确匹配。
- 管理页面使用 AstrBot 官方 Plugin View bridge，**不单独开放监听端口**。
- 保存即生效，无需重载插件；回复大于 1500 字将分段发送。
- 数据保存在 `data/plugin_data/astrbot_plugin_quick_commands/shortcuts.json`，升级插件不会覆盖它。建议手动备份。

## 限制和注意事项

- 动态快捷词通过消息监听实现，**不是**调用 AstrBot 注册 API 动态生成的 `@filter.command`，所以它们不会逐条出现在「插件 → 管理行为 → 指令」，也不自动出现在 `/help` 里。
- 不能拿它当作“调用另一个插件命令”的转发器；本版本仅回复自定义文本（可由 TXT 导入）。例如 `/功能` 和 `/插件` 可以共享同一份列表，但不是让 `/功能` 调用另一个插件的 `/插件` 函数。
- 为保护核心指令，屏蔽了 `/help`、`/plugin` 等保留名字，**但无法自动发现全部第三方插件指令**。不要与现有指令同名，否则依事件顺序可能冲突。若之前安装了 `astrbot_plugin_fixed_list`，建议先停用该旧插件再把 `/功能`、`/插件` 交给此插件。
- `/` 或 `／` 始终可用；去掉 `/` 只针对显式开启开关的规则。必须是纯关键词文本，严格匹配。不开启「允许参数」时，`/插件 任意内容` 和 `插件 任意内容` 均不匹配。
- 请避免把 `你好`、`谢谢` 等日常词语配置为免斜杠指令，否则群里有人正常说出该词时也会触发。
- 不执行代码、不运行 Shell、不读取用户指定的服务器路径、不转发高权限指令。
- QQ 官方机器人有消息长度、频率限制，超长文本分段可能受平台限流。建议内容尽量精简。
- 本插件通过自定义过滤器只唤醒命中的快捷指令，不改动 AstrBot 全局唤醒前缀；QQ 官方机器人仍受平台自身的消息触发、意图/权限等限制。

## 文件树

```
astrbot_plugin_quick_commands/
├── main.py
├── metadata.yaml
├── .astrbot-plugin/i18n/{zh-CN,en-US}.json
└── views/manager/{index.html,app.js,style.css}
```

官方接口文档：
- https://docs.astrbot.app/dev/star/guides/plugin-pages.html
- https://docs.astrbot.app/dev/star/guides/listen-message-event.html
- https://docs.astrbot.app/dev/star/plugin-new.html

## 验证范围

已做 Python 语法、前端 JS 语法及离线模拟测试（包括新旧规则、唤醒过滤、别名、权限、参数、启停、升级兼容），**未在你的云服务器 AstrBot 4.29.1 / QQ 官方机器人现场执行**。

# 给 Agent 的配置提示词

将下面整段发给电脑上的 Coding Agent。它需要有读取本机配置与运行终端命令的能力；如果它没有这些权限，应指导你完成必要操作，而不是声称已经配置好。

```text
请使用 https://github.com/Kys75/redock-codex-setup 帮我配置手机 Redock 与电脑 Codex 接续。

先读取仓库 README.md、AGENTS.md 和完整教程。我的首要目标是继续真实旧对话，保留原 ID、历史、项目目录和正在执行的任务；新建测试对话不算完成。

先只读检查我的操作系统、真实 Codex 启动方式、CODEX_HOME、Herdr/redock-hook 版本，以及 SSH 和网络条件。不要假定我有特殊配置目录；普通默认 ~/.codex 就应可用。不要把作者的目录、账号、代理或模型服务商配置复制到我这里。

优先使用 Redock + SSH + Herdr + 原有共享 Codex 后台。外网需要时配置 Tailscale，SSH 正常后再判断是否需要 Mosh。不要为了接续统一加入 --no-daemon，不删除锁，不 fork 冒充原对话，不关闭所有 Codex。

你可以在我的本机准备并执行与此目标有关、可回滚的配置；先展示涉及哪些文件和备份位置。需要中断已有任务、改变系统安全设置或处理账号登录时，说明影响并让我操作。Hook 信任通过正常 /hooks 审核，不绕过。官方集成已正常就不额外装兼容补丁。

若已有旧对话隔夜消失，按 docs/session-restore.zh-CN.md 先只读核验；若需要 Mac 文件鼠标菜单或图片粘贴，按 docs/desktop-client.zh-CN.md 使用固定版本的独立显示端，不替换正在运行的后台。客户端和通知需求按 docs/connections-notifications.zh-CN.md 区分通用配置与设备专用策略。

Tailscale 控制面超时时先按 docs/network-troubleshooting.zh-CN.md 检查实际网络，不默认清除身份、安装代理或修改 TLS。

必须保留我已有的其他 Hooks、MCP、插件和权限习惯。不要默认开启 YOLO。我的私钥、API Key、Tailscale Auth Key、配置内容、会话正文、主机信息和截图都不要上传 GitHub。

完成后先告诉我：我那段旧对话在 Redock 的哪个工作区和标签页。然后给我日常切换、离开、重连、继续另一段旧对话的步骤。分别核实终端输入、气泡输入、每轮完成状态、两个对话不串窗、锁屏重连、蜂窝连接；明确哪些需要我在手机测试，不能用接口测试代替。
```

如果只要求终端接续，可以把最后一段中的气泡验收删去。若已提供系统、手机和旧对话信息，Agent 应先利用现有信息，不重复询问。

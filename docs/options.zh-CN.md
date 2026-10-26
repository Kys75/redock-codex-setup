# Redock 自带的几类方式，分别解决什么

你要让手机继续电脑任务，先要能到达电脑，再要登录和传输输入，还要在断线时保留工作现场。这三个问题分别有自己的选项；不能把 Tailscale、Mosh 和 Herdr 当作同一层的三个互斥产品。

## 先决定怎样到达电脑

| 方式 | 适合什么 | 实际边界 |
|---|---|---|
| 同一 Wi-Fi 的局域网地址 | 首次配置、家中使用 | 离开这个网络后通常不能直接用原地址 |
| 独立 Tailscale App | 长期跨网络连接，设备加入同一 Tailnet | 手机系统 VPN 可能与其他 VPN 冲突；直连/中继影响延迟 |
| Redock 内置 Tailscale | 希望手机只开 Redock，或需要保留系统 VPN 通道 | Mac 仍需要 Tailscale；代理也可能影响其控制面，不能承诺所有组合无冲突 |
| ngrok SSH 转发 | 临时入口、无法使用私有网络的环境 | 留意地址、认证和套餐；普通 TCP 隧道不能替代 Mosh 所需 UDP |
| 已有公网 SSH 或自己的 VPN | 已有可靠网络和管理经验 | 由原网络方案负责访问控制；本教程不默认新开公网端口 |

第一次先局域网 SSH，之后需要外网再加 Tailscale，是容易逐层验证的路径。

## 再决定终端怎样传输

| Redock Connection Mode | 工作方式 | 建议 |
|---|---|---|
| SSH | 加密登录并传输终端交互 | 默认起点，排错最直接 |
| Mosh | SSH 完成引导，终端交互随后走 UDP | SSH 已正常、移动网络易断时再考虑；保留 SSH 用于其他功能 |

Mosh 不是“把所有 Redock 功能都换成 UDP”，也不会消除跨洲中继或手机渲染的全部延迟。`Mosh fallbacked` 需检查服务端与 UDP，不代表任务已经消失。

## 最后决定谁保存工作现场

| Session Persistence | 适用环境与能力 | 日常选择 |
|---|---|---|
| Herdr | macOS/Linux/WSL，工作区、标签、窗格、Agent 状态与支持的原生恢复 | 多 Codex 对话、手机触控组织的推荐主线 |
| tmux | macOS/Linux/WSL，成熟通用的会话/窗口/窗格管理 | 已有 tmux 用户可以继续用，无需为手机接入强制迁移 |
| psmux | Windows 原生 PowerShell；Redock 标为有限兼容 | 与 WSL 的 tmux/Herdr 是不同环境，按官方 Windows 路线检查 |
| 不启用保持 | 普通远程 Shell | 适合短命令；不要据此保证断线后前台任务继续 |

Herdr 与 tmux 是此处的替代后端，通常选一个即可，不必叠套。Windows 原生 psmux 连接成功，也不代表 Agent Chat View 已支持；Redock 当前 Agent 配置指南要求 Windows 使用 WSL2，连接同一发行版的 SSH。

### 保留 tmux 的简短路线

已安装 tmux 后，在电脑 Shell 运行：

```bash
tmux new-session -A -s mobile-work
```

在其中启动或恢复 Codex。手机 Host 的 Session Persistence 选 tmux，进入同一个 `mobile-work`。`Ctrl+b` 后 `c` 新建窗口，`n/p` 切换，`w` 列窗口，`d` 分离。这里的窗口相当于 tmux 的组织单位，不是另一个系统终端 App。

共享 Codex 与 tmux 的 Hook 关联也需验证；本仓库的共享窗格适配器专门针对 Herdr，不声称自动解决所有共享 tmux 绑定。

## Redock 的其他入口

| 功能 | 用来做什么 |
|---|---|
| Host | 保存一台主机的地址、认证与连接方式 |
| Project | 收纳一个项目相关的工作入口 |
| Action | 保存启动、测试、构建等操作 |
| Snippet | 保存或提供常用命令；命令文本不等于特殊按键 |
| Agent Chat View | 按对话内容呈现聊天气泡，另有识别、读取、输入与状态链路 |
| 语音输入 | 把口述变成可编辑文字，不改变任务实际运行位置 |

先把一个真实旧对话接续成功，再整理这些快捷入口，避免同时引入太多变量。

## 官方参考

- [Redock 指南总览](https://redock.dev/zh/guide/overview)
- [Herdr](https://redock.dev/zh/guide/herdr)、[tmux](https://redock.dev/zh/guide/tmux)、[psmux](https://redock.dev/zh/guide/psmux)
- [Tailscale](https://redock.dev/zh/guide/tailscale)、[内置 Tailscale](https://redock.dev/zh/guide/embedded-tailscale)、[ngrok](https://redock.dev/zh/guide/ngrok-ssh)
- [Mosh](https://redock.dev/zh/guide/mosh)、[Agent 集成](https://redock.dev/zh/guide/agents)、[最佳实践](https://redock.dev/zh/guide/redock-best-practices)

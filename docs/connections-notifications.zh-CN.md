# 客户端数量、提示音与文字通知

一个 Herdr 后台可以有多个显示客户端。电脑一个窗口、手机一个入口显示“两个客户端”通常正常；这不等于启动了两份 Codex 对话，也不等于模型会话计费翻倍。

## 为什么返回手机入口后数量变多

Redock 保存的 Host/终端入口与底层 SSH/Mosh 连接是两层对象。返回同一个入口也可能建立新 Mosh；旧 mosh-server 仍等原客户端回来。是否由锁屏回收、App 重连或协议回退引起，需要手机日志判断，不能只凭主机进程认定用户退出方式错误。

日常回到同一 Herdr Session、工作区和标签页；离开时用正常 Detach/断开。不要为了消除计数关闭 Herdr server 或批量终止 Codex。多余显示连接可能增加画面同步、CPU/内存与声音重复；需要清理时先确认哪些是显示客户端，哪些是后台/任务。

## 需要自动单连接接管时交给 Agent 核实

参考环境实现过“新手机显示连接稳定后替代旧连接”。这是设备专用的可选策略，**本仓库不安装自动终止连接的守护程序**；多人或多设备同时使用时不应强行只保留一条。个人 runtime ID、手机地址、进程白名单和 LaunchAgent 不应从别人机器复制。

如用户明确需要此行为，Agent 应先只读预览并满足以下边界：

- 识别 Redock 环境标记、指定手机/入口、真实 SSH/Mosh 父进程与显示命令；本机客户端、Herdr server、Codex 和其他用户排除。
- 只管理明确允许的 Session，先定义是按设备、入口还是整个后台保留一条；不得擅自关闭其他 tmux 入口。
- 新显示客户端稳定后才替代旧显示 PID，发送信号前重新核对 PID 创建时间、父进程、命令与最新保留对象，避免 PID 复用与竞态。
- 不能向进程组发送信号，不能批量 `pkill codex`、`pkill herdr` 或 `pkill mosh-server`。
- 保存本机预览、接管事件与停用方式；先验收正常返回，再单独验收锁屏、网络切换与 SSH 回退。单有进程存在不等于手机在线。

参考环境已验证正常进出后收敛为电脑/手机各一个；这个结果不等于所有客户端组合都已验证。

## 三种通知分开设置

| 提醒 | 发生位置 | 注意 |
|---|---|---|
| Herdr 内文字提示 | 当前 Herdr 界面 | 提示出现时前缀 Control+b 后按 o 可跳到相关窗格；不等于通知历史 |
| Herdr 声音 | 运行显示客户端的主机 | 手机 SSH/Mosh 中的 Herdr 也运行在 Mac，可能让 Mac 重复响 |
| Redock 手机推送 | iPhone 通知中心 | 由 Redock、Hook 和手机通知权限控制，独立于 Mac 提示音 |

Herdr 0.9.5 可按需合并以下设置到自己的配置；已有表只添加字段，不重复创建整表：

```toml
[ui.toast]
delivery = "herdr"
delay_seconds = 1

[ui.sound]
enabled = true
done_path = "sounds/done.mp3"
request_path = "sounds/request.mp3"
```

先把自己有权使用的 MP3 放到配置目录的 `sounds/`。`done_path` 是一轮完成，`request_path` 是需要处理；不设置文件时可沿用内置声音。`delay_seconds` 是状态确认延迟，不是提示持续时间。当前正在看的标签通常有提示抑制，测试时同时检查其他标签。

运行 `herdr config check` 后再 `herdr server reload-config`。需要对手机客户端的 Mac 发声静音，可仅在已核实的远程 Herdr 启动环境设置 `HERDR_DISABLE_SOUND=1`；不要全局影响电脑入口或把它理解成关闭 iPhone 推送。

## Mac 系统通知与前台抑制

Herdr 0.9.5 的原生 toast delivery 选择单个通道。参考环境另用了按前台窗口判断的私人插件，在保留 Herdr 内提示时，离开 Herdr 才发送无声 Mac 系统通知；该实现绑定具体终端 bundle ID、窗口标题和 macOS 权限，未作为通用插件自动发布。

若要配置类似体验，Agent 先核实实际终端和权限，再按状态事件去重、延迟复核，无法识别前台时不猜测；只激活终端不等于精确跳转 Herdr 子窗格。自定义音频、系统通知、旧 Hook 去重与手机推送分别验收和回滚。

# Herdr：打开文件与在 Finder 中显示

这是可选的 macOS 插件，补充 Herdr 0.9.5 的本地文件操作。Herdr 原生的裸文本链接识别只处理 HTTP(S)；Codex 的可见相对路径不能直接当成网页链接处理。

需要悬停、右键菜单而不想复制路径时，可在本插件之上安装[可选显示端补丁](../../docs/desktop-client.zh-CN.md)。

## 使用

点击包含路径的窗格，选中完整路径并按 `⌘C` 复制，然后：

| 按键 | 操作 |
|---|---|
| `Control+b`，松开，再按 `f` | 用 Mac 的默认应用打开 |
| `Control+b`，松开，再按小写 `d` | 在 Finder 中选中文件 |
| `Control+b`，松开，再按小写 `u` | 重新加载配置 |

三个操作都不需要 Shift，原有 Shift 组合保留为别名。如果字母先留在客户端的输入栏或输入法组合区，它可能尚未送到终端；用户在当前入口通过小写 d 后按回车触发了 Finder 动作。Herdr 原生直接按键本身不要求额外回车，不应仅凭输入栏显示字母就判断绑定失效。

支持 `docs/说明.md`、`../README.md`、绝对路径、带空格的路径、Markdown 文件链接和 `:12` / `#L12` 行号后缀。行号只用于识别文件，打开后不保证跳到该行。Herdr 自己保留的可见选区优先；没有选区时读取 **Mac** 剪贴板。因此选中后复制是跨终端更可靠的操作，不要仅复制“说明”等短标签。

这是在运行 Herdr 后台的 Mac 上打开文件。手机剪贴板不会自动变成 Mac 剪贴板；这些操作也不会把文件下载到 iPhone。

## 安装

要求 Herdr 0.9.5+、macOS、Python 3.11+。先确认当前版本的插件命令和配置仍一致。不要升级或重启承载工作任务的 Herdr 来安装本插件。

把整个 `plugins/local-files/` 复制到自己稳定的本地目录，例如 `~/.local/share/herdr-local-files/`。在该目录建立 Python venv，然后安装 `requirements.txt`。将 `herdr-plugin.toml` 中两个动作的 `python3` 替换为该 venv 内 Python 的**绝对路径**；Herdr 插件从自己的目录运行，不能依赖交互 Shell 的 alias。

```bash
herdr plugin link "$HOME/.local/share/herdr-local-files"
herdr plugin config-dir local.file-actions
```

第二条命令打印私人配置目录。普通 Codex 默认 `~/.codex`，通常不用额外设置。若原本使用其他 `CODEX_HOME`，在打印出的目录中创建 `settings.json`，设置 `codex_home` 为**实际已有目录**。不要照抄作者的私人配置，也不要新建空历史目录。

合并到 `~/.config/herdr/config.toml`，先检查按键没有被已有配置占用：

```toml
[keys]
reload_config = ["prefix+shift+r", "prefix+u"]

[[keys.command]]
key = "prefix+f"
type = "plugin_action"
command = "local.file-actions.open"
description = "打开选中或已复制的文件路径"

[[keys.command]]
key = ["prefix+shift+f", "prefix+d"]
type = "plugin_action"
command = "local.file-actions.reveal"
description = "在 Finder 中显示选中或已复制的文件"
```

已有 `[keys]` 时把 `reload_config` 合并进原表，不重复建表。运行 `herdr config check`，再在普通 Shell 运行 `herdr server reload-config`。参考版本 0.9.5 已实测这会将配置同步给同一机器上的既有客户端，新的小写按键无需退出再进入即可使用；以后可按 `Control+b` 后小写 `u` 重载。远程客户端使用另一份本地配置时需要单独处理。

## 目录选择与边界

Codex 的共享后台可能切换对话目录，Shell 的启动目录不一定可靠。本插件通过当前窗格的 Codex 原生终端标题，唯一匹配已经加载的线程，再只读 `thread/read` 获取实时 cwd。不会发送模型消息、恢复另一段历史或改写 Codex 配置。

- 当前实现支持使用本机 managed socket 的共享 Codex；独立 `--no-daemon`、远端 `--remote`、未知/被覆盖的终端标题使用绝对路径。
- 找不到确定的目录时显示错误，不搜索全部项目，不自动改用 Git 根目录或 Shell 目录。改名、移动文件后的旧路径可能已失效。
- 普通 Shell 使用该窗格目录。其他 Agent 未接入专用会话目录查询，使用前确认它与窗格 cwd 一致。
- 选中的路径通过参数数组传给 `/usr/bin/open`，不作为 Shell 命令执行。
- 不更换默认文件应用；在 macOS 中更改文件关联即可改变打开行为。

## 通知

Herdr 的声音和文字提示是独立选项。需要在界面里看见完成/等待提示，可合并：

```toml
[ui.toast]
delivery = "herdr"
delay_seconds = 1
```

这不会替换默认声音。提示出现期间，`Control+b` 后 `o` 跳到对应窗格；当前正在看的标签通常不再弹完成提示。`delay_seconds` 是核实状态前的延迟，不是提示显示时长。文字提示位于 Herdr 内，不是 iPhone 锁屏推送；声音在运行 Herdr 客户端的机器上播放。

## 验证与撤销

测试：仓库根目录执行 `python3 -m unittest discover -s tests -v`。真实验收应同时检查打开和 Finder 选中、中文/空格、不同项目的同名文件、切换对话后的目录。自动化解析测试不能代替外层终端的鼠标复制与快捷键检查。

卸载：先从配置中删掉上面两条 `keys.command`，然后运行 `herdr plugin unlink local.file-actions` 并重载。小写 `u` 重载绑定可以独立保留。插件文件、私人 `settings.json` 和备份可留存；不要用旧整份配置覆盖后来新增的其他设置。通知可以独立保留，或将 `ui.toast.delivery` 改回原值。

参考：[Herdr 插件](https://herdr.dev/docs/plugins/)、[鼠标与快捷键](https://herdr.dev/docs/quick-start/)、[Codex App Server](https://learn.chatgpt.com/docs/app-server)。

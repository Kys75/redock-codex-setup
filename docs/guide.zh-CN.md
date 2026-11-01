# 从电脑到手机：用 Redock 与 Herdr 继续原来的 Codex 对话

这份教程的目标是：你在电脑上处理一个项目，离开桌面后，用手机继续同一段 Codex 对话；回到电脑时，仍能看到手机发过的消息和任务进度。项目文件与执行程序留在电脑上。

主线使用 Mac、iPhone、Redock、Herdr 和 Codex 命令行。Linux/WSL 可沿用结构，SSH 安装与系统设置按各自平台处理；Windows 原生路径见[方式比较](options.zh-CN.md)。本文核对的参考版本是 Codex 0.164.0、Herdr 0.9.5、redock-hook 1.1.6，实际命令以本机 `--help` 为准。

你不需要为了这件事建立特殊的 Codex 配置目录。**CLI 是 Command Line Interface（命令行界面）的缩写，不是必须创建的文件夹名称。** 普通 Codex 默认使用 `~/.codex`；`~` 指当前用户的主目录。只有你已经主动设置 `CODEX_HOME` 或启动包装器时，才需要处理不同的目录。

## 1. 我们实际在连接什么

假设你在 Mac 上用 Codex 修改 `~/projects/my-project`。Codex 是接收任务、调用工具和保存对话的程序。Herdr 为这个程序提供一个长期存在的终端位置：手机断开连接后，这个位置和里面的程序仍可留在 Mac 后台。

Redock 是手机上的终端客户端。它通过 SSH（Secure Shell，安全远程登录协议）登录 Mac，显示 Herdr 里的画面，把你的按键送给相应程序。SSH 负责加密连接和登录认证。需要在外面用蜂窝网络连接家里的 Mac 时，Tailscale 可以先让两台设备进入可互相访问的私有网络，这个设备网络称为 Tailnet；SSH 仍负责登录。

这里有两种“继续”：

- **回到仍运行的现场**：手机进入原 Herdr 工作区、原标签页，继续操作同一个 Codex 程序。
- **重新打开保存的历史**：Codex 已退出，或要从另一个界面打开旧对话，用 `codex resume` 选回原对话。

Herdr 不会把所有旧对话自动变成正在运行的任务，也不会把 Mac 上的模型程序搬到手机上。对于使用云端模型的 Codex，模型推理仍在原来的服务端，工具执行仍在 Mac。

## 2. 先确认电脑上的 Codex 本来就能工作

打开 Mac 的终端 App、iTerm、Warp 或你正在使用的终端。看到类似 `$` 或 `%` 的提示符时，当前接收输入的是 Shell，可以运行系统命令：

```bash
codex --version
```

如果已经能运行并有旧对话，保留现有安装、登录和模型配置，不重新建一套账号。没有安装时，按 [Codex 官方快速开始](https://learn.chatgpt.com/docs/quickstart) 安装 CLI 并登录，再发一条简单消息确认它可用。

查配置目录时，可以只在自己的电脑查看 `CODEX_HOME` 是否设置，并检查 `codex` 是程序、别名还是 Shell 函数。Shell 函数可能在调用时才指定目录，因此 Agent 不能仅凭当前环境变量下结论。不要把完整环境或配置粘贴到公开 Issue。

旧对话如果来自 Codex 桌面 App，先核实它与 CLI 是否使用相同账号、配置位置和历史格式。本文不把桌面 App 窗口的存在当作 CLI 一定能恢复它的证明。

## 3. 先在同一 Wi-Fi 下连接 Mac

### 3.1 Mac 开启远程登录

在 macOS 系统设置中搜索“远程登录”，开启 SSH 服务，并允许你的登录用户访问。常见路径是“通用 → 共享 → 远程登录”；不同系统版本的布局可能不同。

记下两项本机信息：Mac 在当前 Wi-Fi 下的 IP 地址，以及登录用户名。用户名可在 Mac Shell 运行 `id -un` 查看。它是系统登录名，不一定等于设置里显示的中文全名。

### 3.2 Redock 建立第一个 Host

在 iPhone 安装 Redock，添加 Host。Host 是一组保存的连接信息，填写：

| 字段 | 填什么 |
|---|---|
| 名称 | 自己容易辨认的名字，例如“开发电脑” |
| Host / 地址 | Mac 当前 Wi-Fi IP |
| Port | 默认 SSH 端口 `22`，除非你确实改过 |
| Username | Mac 的系统登录名 |
| Auth | 你的 SSH 密码或私钥认证 |
| Connection Mode | 先选 SSH |

首次连接时核对主机指纹。Mac 可查看 SSH 主机公钥的指纹，例如：

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

连接后应看到 Mac 的 Shell，运行 `pwd` 能显示 Mac 上的目录。这证明手机已经登录到电脑。若这里还不能连，先检查用户名、SSH 权限、地址和网络，不要继续叠加 Herdr 或 Hook 排查。

长期使用建议按 [Redock SSH Key 指南](https://redock.dev/zh/guide/ssh-keys) 配置密钥。公钥放到 Mac 的对应用户，私钥保存在你的客户端；不要把私钥提交到这个仓库。

## 4. 安装 Herdr，并把一段真正的旧对话接进去

### 4.1 安装与集成

在 Mac Shell 检查：

```bash
herdr --version
```

未安装时，按 [Herdr 官方安装方式](https://herdr.dev/docs/install/) 完成安装。官方 macOS/Linux 脚本入口为 `https://herdr.dev/install.sh`；可以先下载查看，再运行：

```bash
curl -fsSL https://herdr.dev/install.sh -o /tmp/herdr-install.sh
less /tmp/herdr-install.sh
sh /tmp/herdr-install.sh
```

`less` 中按 `q` 返回 Shell。安装后重新开一个普通终端，确认 `herdr --version` 可运行。然后检查并安装 Codex 集成：

```bash
herdr integration status
herdr integration install codex
```

如果你确实使用自定义 `CODEX_HOME`，必须让这两条集成命令使用同一个目录；不要把 Hook 装进另一个默认目录。集成修改后按 Codex 提示在 `/hooks` 中审核。

### 4.2 从新终端进入 Herdr

假设你的项目目录是 `~/projects/my-project`，把示例路径换成自己已有的项目目录，在普通 Shell 运行：

```bash
cd ~/projects/my-project
herdr
```

Herdr 会启动或连接默认后台会话。第一次进入可能有引导页面。你看到的主窗格起初通常仍是 Shell；进入 Herdr 不会自动恢复某段 Codex 对话。

如果你已经在 Herdr 窗格里，就不要再运行一层 `herdr`。直接使用当前工作区与标签页。

### 4.3 恢复旧对话

在 Herdr 窗格的 Shell 中运行：

```bash
codex resume --all
```

这是打开历史选择列表，`--all` 让列表包含其他目录下的历史。搜索原对话名称并选择后，核对最近消息和项目目录。知道准确 ID 时，也可运行 `codex resume <SESSION_ID>`，把占位符替换成真实 ID，不保留尖括号。

如果你原来习惯先 `codex` 再 `/resume`，仍可以这样用。原来明确选择 YOLO 权限的用户，也可以用 `codex resume --all --yolo`；YOLO 控制权限，与手机接续功能没有必然关系，本教程不默认开启它。

Codex 的终端画面是操作入口，后台服务负责执行任务、保存和加载对话。参考版本默认允许多个入口连接同一个共享后台。**对于已经加载在共享 Codex 后台里的对话，普通 CLI 可以接回同一个后台。** 不必先退出所有其他对话。此前强制 `--no-daemon` 会另开独立后台，可能与旧后台争用同一对话写锁；不要把这个参数当作 Herdr 的必需配置。写锁用于防止两个独立后台同时改写同一段历史。

如果原对话确实在另一个独立 Codex 实例里运行，需要定位那个实例并正常交接。不要删除锁文件，也不要按 `fork` 创建新分支后声称原对话已经迁移。

## 5. 在 Redock 中进入同一个工作区

编辑刚才已经连通的 Host，将 **Session Persistence（会话保持）** 设为 **herdr**，保存并新建连接。Redock 会显示已有工作区，并提供创建入口。

选择你刚才在 Mac 使用的工作区，再进入放着旧 Codex 的标签页。此时手机应显示同一段旧对话。你可以发送自己的下一条正常任务；Mac 上应出现同一条消息，继续原来的工作。

如果手机连接成功却看到空 Shell，先检查是否进入了另一个工作区或新标签页，不要立即再次 `resume` 同一个 ID。一个空窗格只代表那里没有运行 Codex。

## 6. 看懂 Session、Workspace、Tab、Pane 和 Agent

你进入 Herdr 后，可以按自己管理项目的方式组织它。

**Session（后台会话）** 对应一套长期运行的 Herdr 后台。一般人使用默认 Session 就够了；手机与电脑连接它，才能看见同一套工作区。命名 Session 是另一套命名空间，不能把它理解成一个普通标签。

**Workspace（工作区，也可能显示为 Space）** 用来收纳一个项目的工作位置，例如“网站项目”。它可以有多个标签页。创建时的目录提供初始位置，但目录不是隔离容器；两个工作区指向同一目录，仍然会修改同一批文件。

**Tab（标签页）** 用来区分任务，例如“修登录”“写文档”“普通终端”。标签页里面有一个或多个 Pane。

**Pane（窗格）** 是真正运行 Shell、Codex 或其他程序的终端。Herdr 把其中识别到的 Coding Agent 显示在 Agents 列表，并展示工作、等待或完成状态。

**Codex 对话** 则由 Codex 管理，拥有自己的 ID 和历史。一段常用对话可以一直放在一个窗格中；在同一个 Codex 里使用 `/new` 或 `/resume` 会切换里面的对话，但不会自动创建 Herdr 标签页。

适合手机的组织方式是：**一个项目一个工作区，一个常用任务一个标签页，一个标签页一个主窗格**。另留一个普通终端标签运行命令。需要并行修改同一代码库时，还要考虑 Git worktree 或任务分工；标签页本身不能防止文件冲突。

### 6.1 Herdr 目录和 Codex 目录有什么关系

项目目录保存要处理的源码或文档；Codex 配置目录保存配置、登录和历史；Herdr 工作区只是管理终端的入口。三者不是一层层包含的文件夹。

例如，你从项目 A 启动 Herdr，又在某个窗格用 `cd` 切到项目 B，然后启动 Codex，新的 Codex 会从项目 B 开始工作。同一个 `CODEX_HOME` 仍可记录 A、B 的对话。用 `resume` 恢复旧历史时，还要核对 Codex 显示的工作目录，不能只凭 Herdr 标签名称判断。

### 6.2 增加第二段对话，或另一个项目

同一项目需要第二段对话时，在 Herdr 按 `Ctrl+b`，松开，再按 `c`，新建一个标签页。新窗格出现 Shell 后，切到实际项目目录，运行 `codex` 开新对话，或者 `codex resume --all` 选择另一段旧历史。第一段仍在原标签页中。只想在同一个 Codex 里换话题，则用 `/new` 或 `/resume`，无需另建标签。

另一个项目需要独立分组时，用工作区菜单新建 Workspace，或按 `Ctrl+b` 后 `Shift+n`。也可在普通 Shell 中运行以下示例，先替换为存在的目录：

```bash
herdr workspace create --cwd "$HOME/projects/another-project" --label "另一个项目" --focus
```

`--cwd` 指定初始目录，`--label` 指定显示名称，`--focus` 请求切到新工作区。工作区创建完成后，仍需在其中启动或恢复 Codex。手机的 Space / Tab / Pane 管理入口分别对应工作区、标签页、窗格；增加一个手机连接则是增加显示客户端，不会自动代表增加一个 Codex 对话。

## 7. 日常切换与离开

Herdr 支持点击侧栏、标签页和右键菜单；手机可按 Redock 官方说明双击打开 Herdr 上下文菜单，双指缩放调整字体。Snippet 里的命令文本不是键盘快捷键，不能把文字 `tmux new-window` 当成按键发送。

电脑端默认前缀是 **Control+b**，按完松开，再单独按第二个键。Control 是 `⌃`，不是 Command `⌘`。

| 操作 | Herdr 默认按键 |
|---|---|
| 新建标签页 | `Ctrl+b`，然后 `c` |
| 下一个 / 上一个标签页 | `Ctrl+b`，然后 `n` / `p` |
| 进入工作区导航 | `Ctrl+b`，然后 `w` |
| 查找 Agent 或终端 | `Ctrl+b`，然后 `g` |
| 改当前标签页名称 | `Ctrl+b`，然后 `Shift+t` |
| 改当前工作区名称 | `Ctrl+b`，然后 `Shift+w` |
| 分离当前客户端，保留后台现场 | `Ctrl+b`，然后 `q` |
| 查看当前有效键位 | `Ctrl+b`，然后 `?` |

如果键位被终端 App 拦截，先点击主窗格，再查看 Herdr 帮助或用菜单操作。tmux 默认分离键是 `Ctrl+b` 后 `d`，与 Herdr 的 `q` 不同。

手机显示标签或管理列表时，直接点目标 Tab；多窗格标签还要点目标 Pane。`Ctrl+b` 后 `g` 打开的 Go To 列表可以用 `/` 搜索名称，再点选结果。给标签取“修登录”“写说明”这样的短名，通常比逐个翻手机连接更快。改 Herdr 标签名只改入口名称；要改保存的 Codex 对话名，在 Codex 中使用 `/rename`。更多键位见 [Herdr 键盘指南](https://herdr.dev/docs/keyboard/)。

Attach（附着）是连接到现有后台现场；Detach（分离）是当前客户端离开。切换标签页、手机暂时断线或 Herdr 分离，一般不会停止后台任务。关闭窗格、标签页、工作区或整个服务器则可能结束里面的程序，不是同一种操作。

不需要常用的对话，等任务结束后在 Codex 中 `/quit`，再整理空标签。共享后台的内存释放取决于它何时卸载对话，不能只凭“窗口关了”判断后台已经退出。历史以后仍可通过 `/resume` 找回，无须删除。

## 8. 离开 Wi-Fi：加入 Tailscale

局域网 IP 只适合相应网络。在外面继续连接，推荐先按 [Tailscale 指南](https://redock.dev/zh/guide/tailscale)让 Mac 加入自己的 Tailnet，再选择手机端方式。

- **独立 Tailscale App**：Mac 和 iPhone 登录同一个 Tailnet，Redock Host 改填 Mac 的 Tailscale IP 或 MagicDNS 名称。
- **Redock 内置 Tailscale**：Mac 仍需安装并登录 Tailscale；手机在 Host 中启用内置方式，按 App 引导注册，不必另开手机 Tailscale App。

内置方式不占用手机系统 VPN 通道，但其他代理或 VPN 仍可能影响注册和网络流量。首次注册失败时可临时关闭冲突软件做对照。不要因为卡顿就同时修改两端所有代理设置。

同一 Tailnet 不只是“邮箱看起来相同”，还要确认设备加入的是同一个个人或组织网络，并已获允许。SSH 的用户名、密钥认证仍需正确。Tailscale 的直连通常比绕远的中继更流畅；具体结果以真实手机连接为准。

连接正常后再关闭手机 Wi-Fi，用蜂窝网络回到同一个工作区，发送一条消息。Mac 必须保持开机、联网，并按需求设置供电和睡眠策略；锁屏与整机睡眠不同，Mac 睡眠时不能保证远程可用。

### 8.1 控制面超时并不等于软件配置错误

`Running` 不一定代表 Tailscale 在线；控制面不可达时先检查 `Self.Online` 和 `Health`。网络故障也可能伴随“退登”或“注册状态未更改”，这时不要先清身份或重建 Host。已有案例最终确认是办公室网络问题，兼容设置/代理只用于绕行。按[网络排障](network-troubleshooting.zh-CN.md)做单变量对照。

## 9. 弱网时可选 Mosh

Mosh（Mobile Shell）会先用 SSH 登录，然后让终端交互走 UDP（User Datagram Protocol，用户数据报协议），适合 Wi-Fi/蜂窝切换和不稳定网络。它改善的是连接体验；Herdr 仍负责保留工作现场。

先确保同一个 Host 的 SSH 已可用。在 Mac 安装 `mosh`，例如已有 Homebrew 时：

```bash
brew install mosh
command -v mosh-server
```

然后在 Redock Host 把 Connection Mode 改成 Mosh，新建连接，Session Persistence 继续选 Herdr。默认需要 UDP 60000–61000 可达；按实际私有网络和防火墙规则放行，不必把整个端口范围盲目暴露到公网。

出现 `Mosh fallbacked` 表示 Mosh 没有成功使用，App 可能退回 SSH。要查服务端 PATH、UDP 路径与防火墙。普通 ngrok TCP 隧道通常不能承载 Mosh 的 UDP。

Mosh 终端与气泡视图读取通道不是同一条链路。终端还活着，不代表气泡后台的 SSH 通道也无需重连。频繁新建连接可能残留多个客户端；日常优先回原连接，退出时正常分离并使用 App 的断开操作。

## 10. 开启聊天气泡视图

终端模式直接显示 Shell、Herdr 和 Codex 的画面；Chat View 把识别到的 Agent 历史整理成手机聊天界面，适合阅读长回复。打开气泡不会自动创建第二段 AI 对话，但会有额外读取、同步和手机渲染开销。

为了知道哪段对话正在工作、何时结束，Redock 安装的 `redock-hook` 会接收 Codex 的 Hook 事件。Hook 是程序在开始、提交消息、完成等时刻调用的脚本入口；它负责报告身份与状态，手机再通过主机上的读取服务取得历史。因此终端能显示，不一定代表这条附加链路也配置好了。

按 [Redock Agent 指南](https://redock.dev/zh/guide/agents)，先确认 SSH 能连：

1. 在 Redock“我的 → Agent 设置”中进入“安装与配对”。
2. 选择已保存的 Host，让 App 安装 `redock-hook`、检测 Agent 并配对。
3. Agent 与 `redock-hook` 使用同一个系统用户。Codex 有审核提示时，在 Codex 输入 `/hooks` 查看并信任对应定义。
4. 回到已经接续的旧 Codex 终端，使用待输入区旁的切换入口打开对话视图；具体图标位置以当前 App 为准。
5. 核对标题和最新消息，再从气泡发送一条指令，确认它进入同一段原对话。

官方指南以 Pro 为前提；部分 App 版本提供每日免费试用。额度与计数规则以你的 App 为准，不能把套餐限制误诊成连接故障。无需为测试先承诺购买 Pro。

如果终端正常但气泡找不到对话，先核实实际 CODEX_HOME 和 Hook 安装位置。共享 Codex 后台可能缺少当前 Herdr pane 的环境变量；这是[可选兼容工具](troubleshooting.zh-CN.md#可选兼容工具)针对的情况。

刚 `/new` 或 `/resume` 后，身份更新可能晚于终端画面。先在终端确认目标对话并发正常下一条消息，再重新打开气泡，确认最新内容。不要在尚未核对的旧气泡中继续输入。

## 11. 排队、插入和键盘操作

在 Codex 终端工作中，Enter 可把消息加入当前任务，Tab 可把消息排到后续轮次。这里的 Tab 是键盘按键，不是 Herdr 标签页，也不需要加 `Ctrl+b` 前缀。

手机上必须让文字进入 Codex 的实际输入框，再发送真实 Tab。Redock 草稿栏或气泡的发送按钮不应默认等同于 Tab。以 Codex 显示队列结果为准，参见 [Codex 官方说明](https://learn.chatgpt.com/docs/prompting#steering-and-queuing)。

如果需要操作审批、选择菜单或特殊组合键，回终端模式通常更直接。Shell 命令也要在 Shell 输入；把 `herdr tab create` 发进 Codex 聊天框，会成为给 Agent 的消息。

## 12. 怎样判断已经配置完成

用真实旧对话验证，不必另外占用大量试用额度：

| 验收动作 | 通过时应该看到 |
|---|---|
| Mac 与手机打开目标标签 | 相同原对话 ID、标题和最近历史 |
| 手机终端发送正常消息 | 原对话收到并回复，Mac 同步可见 |
| 气泡发送另一条消息 | 仍进入同一原对话，未串到别的标签 |
| 连续两轮 | 新轮重新开始计时，结束后停止工作状态 |
| 两个不同对话之间切换 | 各自内容与输入归属正确 |
| 分离并重新连接 | 原程序或任务现场保留 |
| 手机锁屏后回来、切蜂窝 | 可以重连回原现场；分别记录体验 |

主机上的 Redock 读取服务（Gateway）返回历史只证明读取链路；Herdr 能显示工作状态也不等于气泡能发消息。服务重启后能恢复历史，仍不等于原进程和任意任务无损续跑。

Herdr 本身是较轻的管理层，但终端缓冲、多个客户端和持续输出也会消耗资源。更需要控制的是 Codex 正在执行的浏览器、构建、MCP 等任务。可以先保留 3–5 段常用对话、同时执行 2–3 段，重任务再少一些，根据本机内存压力调整；这只是起点，不是软件硬上限。

## 13. 以后每天怎样用

电脑：打开终端运行 `herdr`，点击要继续的工作区和标签页。手机：打开原 Host，进入同一位置。仍在运行就直接输入；需要另一段历史时，在空闲标签的 Shell 中 `codex resume --all`。

临时离开用分离；真正结束任务才退出 Codex。保留清楚的项目与任务名称，比常驻打开全部历史更容易在手机上管理。

相关入口：[方式比较](options.zh-CN.md)、[排查与卸载](troubleshooting.zh-CN.md)、[Agent 配置提示词](../prompts/setup.zh-CN.md)。


## 14. 按需增加便利功能

- 旧对话隔夜消失，终端发消息后才回来：先核实原窗格和登记，按[旧对话恢复](session-restore.zh-CN.md)预览、备份后应用。
- Mac 打开文件或在 Finder 中显示：[文件操作插件](../plugins/local-files/README.md)。想直接用鼠标或 Command+V 粘贴图片，再配置[固定版本显示端补丁](desktop-client.zh-CN.md)。
- 客户端积累、重复提示音、自定义声音：[连接与通知管理](connections-notifications.zh-CN.md)。个人单连接管理和前台通知策略需按实际设备配置，不是通用默认值。

这些扩展均不是手机继续旧对话的前置条件；已有官方功能正常时直接使用即可。配置目录、隐私、版本和真实手机验收仍沿用前文要求。

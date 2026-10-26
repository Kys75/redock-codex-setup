# 排查、可选兼容工具与撤销

先判断坏在哪一层。SSH 不能连就处理登录和网络；终端能工作但气泡异常，再查 Agent 集成、读取目录和窗格关联。

## 旧对话显示被另一个 App 占用

核实当前启动是否加了 `--no-daemon`，以及原对话是否由共享后台持有。这个参数会绕过共享后台，不能用来解决已经加载的旧对话接续。

如果只是一个尚未取得写锁的独立界面，按其锁定提示退出，回到 Shell，再用正常 `codex resume --all`。Shell 函数里曾加过该参数时，需要小范围修正函数并在空闲 Shell 重新加载；不要在正在工作的 Codex 输入框里输入 `source`。

如果另一套独立进程确实拥有该对话，要先确认其任务与所有者，再正常交接。锁文件存在与锁正在持有是不同事实；不能删除文件来绕过。`--yolo` 不会覆盖写锁，`fork` 会换成另一段对话。

## /resume 列表没有旧对话

先尝试 `codex resume --all` 去掉 cwd 过滤，再核实实际配置目录、账号与运行用户。CLI 默认 `~/.codex`，显式 `CODEX_HOME` 或 Shell 函数可能改变它。不要通过新建一个空目录来“修复”历史缺失。

桌面 App 历史、另一台主机的历史、不同配置目录里的历史不一定由当前 CLI 列出。需要迁移时另做备份与格式核验，不能直接合并数据库。

## 终端正常，气泡找不到或读错对话

逐项核实：

1. Redock 配对和 Agent 在同一个系统用户下；`redock-hook` 已安装。
2. Redock Hook 安装在当前 CLI 的真实配置层，并通过 `/hooks` 审核。
3. Herdr integration 安装在同一配置目录，Python 能正常运行。
4. 共享后台发出的事件是否缺少当前 Herdr pane 信息。
5. Gateway 使用的 Codex 读取入口是否知道同一个 CODEX_HOME。

`/new` 或 `/resume` 后先核对终端，再用正常消息触发更新。气泡仍指向旧内容时，不要继续在那个未确认的输入框发任务。

## 可选兼容工具

工具用途是给现有官方 Redock Hook 补充正确的 Herdr 窗格信息，以及固定正确的历史读取目录。它不安装官方产品，不创建 SSH 账号，不替用户登录，不管理代理，也不改 Codex 权限。

### 预览与安装

要求 Python 3.11+。先确认官方 Redock 已经配置了当前 Codex 的 Hooks，再在仓库目录运行：

```bash
python3 scripts/redock_codex.py doctor
python3 scripts/redock_codex.py install
```

`doctor` 默认只打印版本、存在性和目录选择来源，不输出用户名、完整路径、会话标题或正文。它不能识别未导出的 Shell 函数，Agent 还需要在本地检查真实启动方式。

`install` 不带 `--apply` 时只预览，不写文件。默认目录选择顺序是：显式 `--codex-home` → 当前 `CODEX_HOME` → `~/.codex`。普通安装使用默认即可；已有自定义目录时，例如：

```bash
python3 scripts/redock_codex.py install --codex-home "$HOME/.codex-work"
```

这里 `.codex-work` 只是说明参数的例子，不是要求创建的新目录。预览无误后，在同一条命令末尾加 `--apply`。

可用 `--codex-bin` 与 `--redock-hook` 显式选择真实可执行文件。PATH 中已有自定义 Codex 包装器时，Agent 必须先检查它，不要把再次改写 CODEX_HOME 的包装器当作原始程序。

安装只修改能精确识别的官方 `redock-hook agent-event --agent codex --stdin` 命令，保留其他事件、匹配器、超时和插件。已有自定义包装器或 inline Hook 定义时停止，留给 Agent 检查，避免重复安装。安装后通过 Codex `/hooks` 正常审核变更。

### 文件放在哪里

默认安装到本机 `$XDG_DATA_HOME/redock-codex-setup/<目录摘要>`；没设置 XDG_DATA_HOME 时使用 `~/.local/share`。摘要用于区分配置目录，不保存对话正文。

| 本地文件 | 作用 |
|---|---|
| adapter.py | 已安装的本地事件包装器 |
| settings.json | 本机路径与目标 Herdr socket，权限 600 |
| bin/codex | 固定实际 CODEX_HOME 的读取入口，仅加入该 Hook 子进程的 PATH |
| manifest.json | 记录哪些命令被替换，供撤销使用 |
| backups/ | 原始 Hooks 和撤销前备份，留在本机 |

这些文件不是公开仓库素材。`--install-dir` 可另选私人安装目录，必须放在 Git 仓库之外。

### 已打开的旧对话需要立即补关联

新消息通常会触发真实 Hook 更新。如果旧对话已经打开，只想先让气泡找到它，可以由 Agent 核实原 ID 与当前 pane，再预览绑定：

```bash
python3 scripts/redock_codex.py bind --session-id <SESSION_ID> --pane-id <PANE_ID>
```

替换两个占位符后执行。只有实时终端标题与前台共享 Codex 唯一匹配、且找到同 ID 的历史文件时才允许绑定；加 `--apply` 才登记。它不会给模型发消息，也不会 fork。

这个入口仅支持传统 JSONL rollout 的身份核验，新存储格式会停止。补登记解决历史定位，不证明工作状态与计时已经自动恢复；下一条正常消息仍须检查 UserPromptSubmit/Stop 的实际效果。

### 卸载

```bash
python3 scripts/redock_codex.py uninstall
python3 scripts/redock_codex.py uninstall --apply
```

自定义目录时继续带原来的 `--codex-home`、`--install-dir`。卸载只还原仍与本工具匹配的命令，保留后来新增的其他 Hook 和改过的超时；已被手动替换的命令不会覆盖，没有可识别条目时停止，不直接用整份旧备份覆盖现状。私人安装文件与备份保留，审核恢复后的 Hook。

### 支持边界

- 默认 Herdr socket 是 `~/.config/herdr/herdr.sock`。命名会话或自定义位置需同时给正确 `--herdr-socket` 与 `--herdr-session`，且手机必须进入同一命名空间。默认会话是主要验证路径。
- 依赖 Codex 原生终端标题中至少 24 字符的 UUID 前缀，以及 Herdr 的 pane API。版本改变、标题被覆盖时不猜测目标。
- 同一段对话出现在多个匹配的 Herdr pane 时，不自动选择其中一个。优先让电脑与手机附着同一个 pane。
- 适配器主要处理共享后台的 Herdr 路径；`--no-daemon` 的独立锁定界面不会被当作共享目标。原生 tmux 环境只透传，不提供通用共享 tmux 发现。
- `source=herdr:codex` 的身份上报行为在参考版本上验证过，不等于上游承诺永久兼容。升级后重复验收。
- 本工具不修改 Hook 信任。旧后台是否重新加载 Hook 定义，以当前 CLI 的实际提示与下一条真实消息为准；不能承诺安装后所有已运行对话立刻更新。

## 卡顿、睡眠和很多客户端

终端输入回显慢，先查网络 RTT、直连/中继、代理和前后台状态；气泡本地滚动慢，还要看手机渲染与历史大小。只看 Mac 到 iPhone 的一次 ping 不能代表完整业务体验。

Herdr 后台、每个显示客户端和每个 Codex 任务是不同对象。多个 Mosh/Herdr 客户端可以同时显示一个任务，不等于创建多个模型对话；但会增加连接和画面同步开销。先列出来源并确认哪些已不用，再定向清理，不使用 `pkill codex` 或批量杀所有 mosh-server。

Mac 睡眠、重启、Herdr 服务器停止会改变可用性。分离保留进程；服务重启后的布局恢复与 Codex 历史恢复不是原进程无损存活。保留重要结果，升级与重启安排在任务适合暂停时。

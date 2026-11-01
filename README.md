# Redock + Herdr + Codex：电脑与手机接续指南

在电脑上启动 Codex，用 iPhone 上的 Redock 继续同一段对话。电脑保留文件和任务，Herdr 保留终端工作区，手机负责连接与操作。

这是社区教程与可选兼容工具，不是 Redock、Herdr 或 OpenAI 的官方项目。默认面向普通 Codex 命令行安装，使用 `~/.codex`；不要求建立额外的配置目录，也不更换模型服务商。

## 从哪里开始

- **自己配置**：阅读[完整教程](docs/guide.zh-CN.md)，从 Mac 开启远程登录、手机连接，到恢复真正的旧对话。
- **交给 Agent 配置**：复制[接手提示词](prompts/setup.zh-CN.md)，让 Agent 先读本仓库的 [AGENTS.md](AGENTS.md)。
- **比较 Redock 内置方式**：看[连接方式与会话后端](docs/options.zh-CN.md)。SSH/Mosh、Tailscale、Herdr/tmux 分属不同层，可以组合。
- **已经能连，但旧对话锁定、气泡读错或不更新**：看[排查与兼容工具](docs/troubleshooting.zh-CN.md)。
- **后台自动升级后，原对话要发消息才重新出现**：看[旧对话登记自动恢复](docs/session-restore.zh-CN.md)，只修复经过实时核验的已有登记。
- **Mac 文件路径打开／Finder、鼠标菜单和图片粘贴**：先配置[文件操作插件](plugins/local-files/README.md)，需要鼠标菜单或 Command+V 图片粘贴时，再看[可复现的 Herdr 显示端补丁](docs/desktop-client.zh-CN.md)。
- **重复客户端、提示音和通知**：看[连接与通知管理](docs/connections-notifications.zh-CN.md)，按自己的设备决定保留策略。
- **Tailscale 控制面不可达**：先按[网络排障](docs/network-troubleshooting.zh-CN.md)区分网络、身份与 SSH，避免无故重装。

推荐起点：**Redock + SSH + Herdr + 原有 Codex 共享后台**。需要外网访问时加 Tailscale；SSH 跑通后，再根据移动网络体验决定是否用 Mosh。

## 最短日常路径

前提是 SSH 和 Herdr 已按教程配置。电脑新开一个普通终端：

```bash
cd ~/projects/my-project
herdr
```

进入 Herdr 的 Shell 后，恢复旧对话：

```bash
codex resume --all
```

手机打开同一个 Redock Host，`Session Persistence` 选择 `herdr`，进入同一工作区和标签页即可。后续手机重连直接回原标签，无需每次再启动一个 Codex。

**已经由共享后台持有的旧对话，应接回同一个后台。不要为手机接续统一加 `--no-daemon`。** 单独开启另一个后台可能与原对话争用写锁。也不要删锁、清历史或强杀所有 Codex。

## 可选工具

优先完成官方集成。只有确实遇到共享 Codex 缺少 Herdr 窗格信息、或者 Redock 读错配置目录时，才使用这个工具。

基础 Hook 适配器要求 Python 3.11+，无第三方 Python 依赖；旧对话恢复和文件插件另有 websockets 依赖，见各自说明：

```bash
git clone https://github.com/Kys75/redock-codex-setup.git
cd redock-codex-setup
python3 scripts/redock_codex.py doctor
python3 scripts/redock_codex.py install
```

`doctor` 只读；`install` 默认只预览。确认目标配置正确后，加 `--apply` 才写入：

```bash
python3 scripts/redock_codex.py install --apply
```

它只包装 `hooks.json` 中可识别的官方 Redock Codex 命令，保存本地备份和撤销信息；不改 `.zshrc`、认证信息、权限模式或 Hook 信任。修改后在 Codex `/hooks` 中审核。已有自定义包装器时会停止，交给 Agent 检查，不盲目覆盖。

自定义配置目录通过 `--codex-home` 或已有 `CODEX_HOME` 指定；默认无需设置它们。完整用法和卸载见[排查指南](docs/troubleshooting.zh-CN.md#可选兼容工具)。

## 当前验证范围

| 项目 | 证据范围 |
|---|---|
| macOS、Codex 0.164.0、Herdr 0.9.5、redock-hook 1.1.6 | 已在真实环境接续旧对话，保留原 ID 与正在执行的任务；Redock 后台可读取对应历史 |
| 共享后台的事件关联思路 | 已观察真实后续消息自动关联到正确 Herdr 窗格 |
| 本仓库通用工具 | 临时目录测试覆盖默认/自定义目录、安装与撤销、Hook 保留、消息不串窗；未覆盖所有用户机器 |
| Herdr 本地显示端补丁 | 固定 0.9.5 基线、Mac 真实鼠标打开/Finder 和图片附件；发布时复验完整补丁构建，其他平台不作承诺 |
| 旧对话登记恢复 | 临时目录锁协议、并发写入、正文和计时保留；使用私有登记格式，升级必须重验 |
| 手机气泡收发、完成计时、锁屏和蜂窝重连 | 必须在用户自己的手机分别验收，不能以本机接口成功替代 |
| Linux / WSL | 设计使用标准 POSIX 工具；自动测试不等于手机端完整实测 |
| Windows 原生 PowerShell | 提供 Redock psmux 路线说明；不支持安装这个 Python 兼容适配器 |

没有固定的“开几段必然稳定”上限。浏览器、MCP 服务、构建等任务的资源消耗通常比 Herdr 管理层更值得关注。

## 开发与隐私

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-restore.txt -r plugins/local-files/requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

原生 redock-hook 锁协议测试需额外设置 `REDOCK_TEST_BINARY` 为本机二进制绝对路径；否则明确跳过。GitHub Actions 测试 Python 工具；Herdr Rust 补丁的构建与平台边界见补丁文档。

仓库只存通用代码、虚构测试数据和说明。安装产生的配置、备份在用户本地数据目录，不应提交。请勿在 Issue 中上传 API Key、SSH 私钥、Tailscale Auth Key、完整配置、对话正文或本机截图；提交前先脱敏。

本仓库自有工具与教程为 MIT 许可；`patches/herdr-0.9.5/desktop-client.patch` 及其上游衍生代码为 Apache-2.0，许可与修改说明随包提供。第三方产品的商标、客户端、服务与订阅按各自条款使用。

版本变更见 [CHANGELOG.md](CHANGELOG.md)。

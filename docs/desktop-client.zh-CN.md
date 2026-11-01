# Mac 鼠标文件菜单与 Command+V 图片粘贴

这是针对官方 **Herdr 0.9.5** 的可选社区显示端补丁，不是 Redock 手机客户端更新。先完成原有旧对话接续；只有确实需要以下能力，再安装：

- 在可见文件路径上悬停、右键，用 Mac 默认应用打开或在 Finder 中显示。
- 识别中文、带引号的空格路径、文件名内部括号，以及满足条件的完整跨行路径。
- 本地 Codex 输入区中，将终端发送的“空粘贴”在剪贴板有图片时转换为 Control+V，从而支持已验证终端的 Command+V 图片粘贴。

文件操作依赖[文件操作插件](../plugins/local-files/README.md)。它核实当前对话目录；鼠标菜单在此基础上提供入口。只在本机 Mac 操作文件，不把文件发送到手机。

## 支持范围

| 项目 | 范围 |
|---|---|
| 上游基线 | Herdr v0.9.5，提交 `2ecf19a92fc3a7fff75b6ce3655ef04f4625ec01` |
| 当前验证 | Apple Silicon macOS、本地默认 Session、官方 0.9.5 后台 |
| 保持不变 | 官方 Herdr 可执行文件、后台协议、Codex 任务和手机入口 |
| 尚未验证 | Intel Mac 构建、其他 Herdr 版本、命名 Session、远端客户端 |

补丁仅修改显示端；不能认为任意新版后台都与此版本兼容。官方升级后应先重新验证，不能直接覆盖新源码或替换正在运行的后台。

## 从源码构建

需要 Git、Rust 1.96.1、Zig 0.16.0 和可用的 Apple Command Line Tools。先运行 `git --version`、`cargo --version`、`zig version`、`xcrun --show-sdk-path` 确认工具可用。Rust 版本由源码 `rust-toolchain.toml` 固定；可以用 rustup 安装该版本，不需要改变全局默认版本。

在本仓库根目录运行；示例构建目录必须尚不存在，已有目录时改用新的空目录：

```bash
setup_repo="$PWD"
herdr_source="$HOME/projects/herdr-redock-0.9.5"
git clone https://github.com/herdrdev/herdr.git "$herdr_source"
cd "$herdr_source"
git checkout --detach 2ecf19a92fc3a7fff75b6ce3655ef04f4625ec01
git apply --check "$setup_repo/patches/herdr-0.9.5/desktop-client.patch"
git apply "$setup_repo/patches/herdr-0.9.5/desktop-client.patch"
cargo build --release --locked -j 2
```

Zig 不在 PATH 时，可仅对构建命令设置 `ZIG=/实际路径/zig`。Mac 上若 Xcode 尚未初始化，但独立 Command Line Tools 已可用，可仅在当前 Shell 设置：

```bash
export DEVELOPER_DIR=/Library/Developer/CommandLineTools
export SDKROOT="$DEVELOPER_DIR/SDKs/MacOSX.sdk"
```

不要为了本补丁改全局 xcode-select、接受未知系统提示或覆盖其他项目工具链。构建依赖及上游许可保留在 Herdr 源码中。本仓库提供源码补丁，不附带机器专用二进制。

## 安装与启用

1. 按[插件说明](../plugins/local-files/README.md)安装 `local.file-actions`，合并 `prefix+f` / `prefix+d` 两个命令并验证快捷键可以打开、定位文件。鼠标菜单依赖这些命令映射。
2. 将刚构建的显示端与独立启动器安装到用户目录；若目标已有同名文件，先将旧文件复制到仓库外作为备份，不覆盖正在使用的版本。

   ```bash
   mkdir -p "$HOME/.local/share/herdr-local/0.9.5-redock-v0.2.0" "$HOME/.local/bin"
   install -m 755 "$herdr_source/target/release/herdr" "$HOME/.local/share/herdr-local/0.9.5-redock-v0.2.0/herdr"
   install -m 755 "$setup_repo/patches/herdr-0.9.5/herdr-mouse" "$HOME/.local/bin/herdr-mouse"
   ```

3. 官方 Herdr 默认后台需要已经在运行。还未启动时先用原来的 `herdr` 进入并正常 Detach。
4. 在旧显示界面选择 **menu → Detach**，回到 Mac 普通终端，运行 `~/.local/bin/herdr-mouse`。只重载配置不能更新原生显示程序；需要分离后重新连接。

启动器只连接已有默认后台，不自动启动或更换后台；官方 `herdr` 保留原样。如果你已有不同路径的私人启动器，可保留它，只参考本仓库的独立入口方式。

## 日常操作

- 文件路径悬停后出现下划线；右键选择“打开文件”或“在 Finder 中显示”。左键拖动仍用于选择文字。
- 若外层终端拦截右键，先让右键事件发往 Herdr。若启用了 Send right-clicks to pane，可在窗格边框菜单改回 Use Herdr right-click menu。
- 中文、空格、括号路径支持引号或完整括号界定；跨行重建只针对同样式、完整括号包围、唯一候选、不超过八个可见行的路径。
- 隐藏目标的短标签、裁剪掉的文件名、丢失真实空格的排版不保证可识别。可加宽窗口或让 Agent 输出完整单行路径；不会猜测其他目录里的同名文件。
- 行号后缀用于识别文件，不保证默认编辑器跳到该行。
- 图片：在 Mac 复制图片后点击 Codex 输入区，按 Command+V；发送前确认附件标记。Control+V 仍可用。补丁只处理终端实际发来的空 bracketed paste，不能把所有外层终端的 Command+V 都变成通用图片粘贴。
- 图片适配通过 `HERDR_LOCAL_IMAGE_PASTE=1` 显式启用，仅限本地端点、真实前台 Codex 和有图片的本地剪贴板；SSH/Mosh 环境排除在外。手机继续用 Redock 自己的附件入口。

## 验证与回退

用两个不同项目的同名文件验证打开位置，测试中文空格、括号和跨行路径；先选中另一个窗格再点击目标路径，确认没有串目录。图片要看真实附件标记，不能仅凭按键日志认定成功。

本补丁形成时已完成真实鼠标打开/Finder、原有后台附着及图片附件验收。v0.2.0 发布时再次从固定基线应用补丁：格式、Clippy、release 构建通过，`cargo nextest run --locked --bin herdr` 的 3,651 项测试通过、11 项跳过。使用 nextest 隔离进程，避免单进程全套 `cargo test` 中的上游信号测试互相影响。

完整集成套件未通过：`api_ping::pane_info_and_subscriptions_expose_done_agent_status` 等待模拟 Pi Agent 的完成事件超时；在同一 Mac 的官方 0.9.5 二进制上重放相同 API 流程，也出现超时和 `idle` 状态。此补丁未修改服务端或 Agent 检测，发布保留该已知验证限制，不宣称上游全部测试通过。以上也不代替新机器的真实终端验收。

回退：新界面 Detach，在普通终端运行原来的 `herdr`。不需要停止 Codex 或 Herdr server。插件及其快捷键可以独立保留或按插件说明撤销。

## 许可

补丁包含对 Apache-2.0 许可的 [Herdr](https://github.com/herdrdev/herdr) 源码的修改，保留上游版权及许可；随包附有 [Apache-2.0 许可](../patches/herdr-0.9.5/LICENSE.Apache-2.0)和[修改说明](../patches/herdr-0.9.5/NOTICE.md)。补丁摘要和确切文件列表见 [source.json](../patches/herdr-0.9.5/source.json)。

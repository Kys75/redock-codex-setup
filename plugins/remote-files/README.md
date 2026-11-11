# 在 Mac 上查看远端 Herdr 文件

在 Mac 的增强版 Herdr 中切到已登记的 SSH 机器，右键完整路径，选择 **下载副本并打开** 或 **在 Finder 中显示副本**。文件从对应机器获取到当前 Mac；原文件和任务仍属于远端机器。

支持 Herdr 0.9.5、Mac 显示端，以及 macOS／Linux 远端。文件路径可以是绝对路径，也可以相对于该窗格当前项目的路径。Codex 共享后台的目录通过实际运行的对话读取。带中文、空格、括号的完整路径及符合显示端识别条件的跨行路径均可使用。

## 安装读取组件

先安装 [Herdr 增强显示端](../../docs/desktop-client.zh-CN.md)，并在其统一侧栏中登记需要访问的 SSH 机器。普通 SSH 应当已经可登录；读取组件沿用该 SSH 身份与主机密钥校验。

在本仓库根目录，为当前 Mac 安装文件获取程序。`python3` 应指向已能正常运行的 Python 3.10 或更新版本：

```sh
access_dir="$HOME/.local/share/herdr-file-access"
mkdir -p "$access_dir"
cp plugins/local-files/file_actions.py plugins/remote-files/remote_files.py "$access_dir/"
python3 -m venv "$access_dir/venv"
```

在每个远端用户下，安装同样的两个文件和一个独立 Python 环境。例如已有 SSH 别名为 `workstation`：

```sh
remote_target=workstation
ssh "$remote_target" 'mkdir -p "$HOME/.local/share/herdr-file-access"'
scp plugins/local-files/file_actions.py plugins/remote-files/remote_files.py \
  "$remote_target:.local/share/herdr-file-access/"
ssh "$remote_target" 'python3 -m venv "$HOME/.local/share/herdr-file-access/venv"'
ssh "$remote_target" '"$HOME/.local/share/herdr-file-access/venv/bin/python" -m pip install "websockets>=14,<16"'
```

只需在远端安装 WebSocket 依赖，用于读取共享 Codex 的实际项目目录。它没有新增网络监听端口，文件读取通过已有 SSH 连接运行。多位用户分别在自己的主目录安装，权限沿用各自 SSH 账号。

普通 Codex 默认使用 `~/.codex`。如果远端实际使用自定义 Codex 目录，在**远端**的 `~/.local/share/herdr-file-access/settings.json` 写入：

```json
{"codex_home": "/absolute/path/to/actual-codex-home"}
```

应从用户真实启动方式确认这个目录；程序目录、项目目录和 Codex 配置目录是三个不同位置。

新版 `herdr-mouse` 启动器会使用上述本机目录中的读取程序和 Python。手动启动增强版时，设置 `HERDR_REMOTE_FILE_HELPER` 为本机 `remote_files.py` 的绝对路径，`HERDR_REMOTE_FILE_PYTHON` 为本机专用环境的 Python 路径。分离旧显示端后重新进入即可加载。

## 下载副本怎样使用

副本保存在当前 Mac 的 `~/Library/Caches/HerdrRemoteFiles/`，按机器、原路径与内容版本分开。相邻的 `source.json` 记录来源机器、原路径、时间与摘要。Finder 中显示的是这份本地副本。

修改副本后可以自行另存或传回远端。再次获取同一文件时，程序会保留已修改的副本，为新下载使用独立位置。远端内容变化也会形成另一个版本。

每个普通文件最大 64 MiB，获取超时为 30 秒，每个显示端最多同时处理两个文件操作。下载失败或内容变化时会提示错误；获取期间可以继续切换工作区和机器。终端配置、安装包等可能触发执行的类型，应通过 Finder 入口检查后自行处理。下载文件带 macOS 隔离标记。

已提交的文件操作可以在显示端分离后继续完成。大文件、文件夹浏览和编辑后自动回写适合使用专门的文件工具。

## 排查与回退

- 出现“后台已变化”：重新连接机器，再在当前路径上右键。
- 相对路径解析失败：确认远端的 `codex_home` 与实际运行对话一致；也可以先使用完整绝对路径。
- SSH 失败：先验证原 SSH 别名可登录，再重试文件操作。
- 找不到读取组件：核对当前 Mac 和远端的上述安装目录，以及启动器选择的 Python。

回退到旧 `herdr-mouse` 启动器或官方显示端即可停止使用此鼠标功能。两个读取程序和独立 Python 环境可以单独移除；它们没有接管远端后台服务。

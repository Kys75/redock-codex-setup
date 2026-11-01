# Codex 后台升级后，旧对话从 Redock 气泡列表消失

有一种状态不一致：Herdr 窗格中仍是原来的 Codex，对话已在共享后台恢复，但 Redock 的登记仍是 `ended`。终端发送一条消息会重新登记；只想阅读历史时，不应该每天为此发送测试消息。

可选脚本 [redock_reconcile.py](../scripts/redock_reconcile.py) 修复的是**同一个 Herdr 窗格里、已经有 Redock 登记的旧对话**。它核对真实运行状态后，仅把对应登记的 `session_state` 从 `ended` 改为 `active`。原轮次 ID、完成状态、计时、历史路径和其他字段保留；不调用模型，不发送通知，不启动或重启 Codex。

## 使用前先确认问题一致

让 Agent 对照当前 Herdr 窗格、Codex 原生标题、实际共享后台与 Redock 登记。只有以下条件全部成立才自动恢复：

- 原生标题中的对话 ID 唯一匹配，仍是登记里的同一个窗格。
- 前台进程是共享 Codex，排除 Shell、独立 `--no-daemon` 和显式远程入口。
- 对话确实在选定 Codex 后台的 loaded 列表中，运行状态是 idle 或 active。
- 后台返回的历史路径、项目目录与原登记一致，且历史文件首条身份正确。
- 核验后窗格与进程仍未切换；提交写入时原登记也未被真实 Hook 更新。

不存在的登记、换了窗格的历史、同一对话同时出现在多个窗格等情况会跳过，不据此创建第二份对话。首次配置或新入口缺少关联，仍按[旧对话绑定说明](troubleshooting.zh-CN.md#已打开的旧对话需要立即补关联)处理。

## 兼容性与安装

已验证组合为 macOS、Herdr 0.9.5、Codex 共享后台 0.165.0、redock-hook 1.1.6。此脚本使用 Redock 私有登记格式，不属于官方稳定 API；因此要求 `schema=1`，并检查已验收 redock-hook 的二进制 SHA-256。**升级后不要直接改摘要绕过检查**，必须先重新核实格式与锁协议。

要求 Python 3.11+，以及 [requirements-restore.txt](../scripts/requirements-restore.txt) 中的 websockets 15.x。可使用已有合适环境，也可建立独立虚拟环境。它与原事件适配器相互独立，不需要替换 `hooks.json` 或已有通知配置。

Agent 安装顺序：

1. 确认真实 `CODEX_HOME`。普通用户默认 `~/.codex`；不要复制他人的自定义目录。核对 Herdr socket、Session、Redock 状态目录与真实 `redock-hook` 可执行文件。
2. 在仓库运行测试，包括与本机官方二进制配合的隔离测试：

   ```bash
   REDOCK_TEST_BINARY="$(command -v redock-hook)" python3 -m unittest discover -s tests -v
   ```

   原生测试使用临时 XDG 状态目录与 `--chat-only`，验证目录锁和并发写入，不操作生产登记或发送通知。未设置 `REDOCK_TEST_BINARY` 时，该项明确跳过，不能视为已验收本机二进制。
3. 将脚本复制到仓库外的私人安装目录，例如 `~/.local/lib/redock-codex-restore/reconcile.py`。按下表生成 `settings.json`，所有路径使用核实后的绝对路径，配置权限 600。
4. 先运行不带 `--apply` 的预览，核对 `verified` 中确实是应该恢复的旧对话。保存本地备份后再应用。
5. macOS 可由 Agent 建立独立用户 LaunchAgent，每 30 秒运行一次 `--apply`，退出后不常驻。使用所选 Python 解释器的绝对路径，不依赖交互式 Shell；部署后核对实际运行、退出码与重复执行不改登记。Linux/WSL 的定时服务需另行验收。

| 配置字段 | 值的来源 |
|---|---|
| `codex_home` | 真实 Codex 配置目录，默认 `~/.codex`，展开为绝对路径 |
| `herdr_socket` | 实际 Herdr API socket，默认 `~/.config/herdr/herdr.sock` |
| `herdr_session` | 手机正在连接的 Session，通常为 `default` |
| `registry_path` | 实际 Redock 登记，通常为 `~/.local/state/redock-hook/chat/sessions.json`；尊重已有 XDG 配置 |
| `redock_hook` | 当前真实 redock-hook 二进制路径 |
| `verified_redock_sha256` | 完成上述锁协议测试和版本审查后记录的二进制摘要 |
| `state_dir` | 私人状态目录，例如 `~/.local/state/redock-chat-restore` |

以已安装的路径为例，在普通 Shell 使用所选解释器运行：

```bash
python3 ~/.local/lib/redock-codex-restore/reconcile.py \
  --settings ~/.local/lib/redock-codex-restore/settings.json
```

加 `--apply` 才写入登记与本地状态记录。脚本使用与 redock-hook 1.1.6 一致的 `.registry.lock` 独占目录锁；锁被占用时跳过，不删除别人的锁。持锁后重新比对整条记录，避免覆盖扫描期间到达的真实任务事件，并以权限 600 原子替换文件。

## 如何验收与停用

选择一段实际不可见的旧对话，恢复后不发消息，返回 Redock 终端并重新打开气泡。应直接看到原历史，任务计时不重新开始，也不响起新通知。还应检查已退出的 Agent 没有被恢复，以及多窗格内容不串。

`state_dir/status.json` 记录最近检查；`events.jsonl` 只记录恢复与错误状态变化，不保存对话正文。`restored=[]` 且 `status=ok` 表示本轮不需要修复。`redock_binary_changed_revalidate_required` 表示 Redock 升级后需重新验收；后台不可达时会跳过，后续周期再检查。

停用时停止并卸载本次单独创建的定时任务即可。已经恢复的对话仍交由真实 Hook 管理。**不要用旧的整份 sessions.json 覆盖当前文件**，否则会丢掉安装后正常产生的登记变化。

这是一处有版本边界的兼容修复，不保证所有升级、存储格式或终端布局都自动兼容。长期优先采用上游提供的原生恢复方案。

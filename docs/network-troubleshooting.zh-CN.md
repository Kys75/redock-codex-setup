# Tailscale 控制面不可达：先分清网络与配置

“目标 Host 不可达”是连接失败的总提示。列出的 MagicDNS、IP、在线状态、SSH 和 ACL 是检查方向，不表示这些配置都错了。先检查失败的层次，不重装软件或反复创建新 Host。

## 三个状态分别验证

1. **网络控制连接**：Mac 运行 `tailscale status --json`，检查 `Self.Online` 和 `Health`。`BackendState=Running` 只表示后台在运行；`Out Of Sync`、`Network Map Response Timeout` 表示协调信息未及时同步。
2. **SSH 登录**：网络可达后，检查原 Host 的地址、22 端口和认证。对本机回环/本机 Tailscale IP 的端口检查只证明本机服务监听，不能代替手机真实连接。
3. **Herdr / Agent 对话**：SSH 成功后才检查旧对话的工作区、窗格和气泡映射。手机能显示对话列表可能来自缓存；仍显示 ESTABLISHED 的旧 TCP 也不能单独证明链路畅通。

## “退登”或“注册可能失效”不一定是身份问题

`fetch control key ... /key?v=... context deadline exceeded` 表示获取控制服务公钥超时；错误中的版本号会变化。它可能伴随 logged out 提示，但不能仅由此认定账号过期。

Redock 若显示“无法连接 Tailscale 控制面，注册状态未更改”，先保留身份。核对服务器上的设备登记、节点密钥到期日，再判断是否需要重新认证。Auth Key 用于首次注册，它的期限与已注册节点密钥的期限不是同一个概念。只有确有身份被删除或过期等证据，才走重新注册流程。

## 一次只改变一个网络条件

- 保持手机在前台，记录 Wi-Fi/蜂窝、代理开关和使用内置还是独立 Tailscale。
- Mac 与手机的状态分开检查；Mac 恢复不表示手机控制连接也恢复。
- 对照 Wi-Fi 与蜂窝或其他可信网络。如果某个办公室/实验室网络失败而其他路径成功，优先检查该网络出口。
- 如需比较内置与独立 Tailscale，切换 Redock Host 对应开关，并确认进入同一个 Tailnet。独立 iOS Tailscale 与另一个系统 VPN 通常不能同时工作。
- 使用 Redock 内置 Tailscale 时，可比较代理开/关。代理可能造成干扰，也可能绕过失败的直连路径，不能固定认定“必须开”或“必须关”。若临时全局代理恢复，进一步按代理日志配置针对控制服务的规则；这不等于所有业务数据都必须经过代理。
- `curl` 能打开控制服务不等于客户端握手正常，二者 TLS 实现可能不同。Mac/Linux 可用 `tailscale debug ts2021 --verbose` 诊断实际控制协议；日志只保存在本机，公开前脱敏。

## 已遇到的网络案例

一次办公室网络故障中，SSH 本机监听正常，但 Mac 和 iOS 都无法获取 Tailscale 控制公钥。Mac 默认 TLS 诊断超时，单独设置 `GODEBUG=tlsmlkem=0` 后成功；手机经可用代理的 Redock 内置连接也恢复。后来确认根因在当地网络，并非软件配置错误。

`tlsmlkem=0` 会关闭 TLS 的 ML-KEM 后量子混合密钥交换，保留传统 TLS 加密和证书验证。它在该案例中用于绕过网络兼容问题，**不是本仓库的默认安装项**，也不能据此推断所有同类超时都由 ML-KEM 导致。持久配置、系统权限和回滚需按具体平台验证；不要照抄别人的系统配置。网络修复后再验证默认握手，决定是否撤销临时绕行。

这里不提供个人网络地址、私有代理配置或密钥。上游同类报告只能作线索，不能代替本机对照；本仓库不自动改 ACL、DNS、代理或 Tailscale 加密配置。

参考：[Redock 内置 Tailscale](https://redock.dev/zh/guide/embedded-tailscale)、[Tailscale 防火墙端口](https://tailscale.com/kb/1082/firewall-ports)、[Go GODEBUG](https://go.dev/doc/godebug)、[同类上游报告](https://github.com/tailscale/tailscale/issues/20777)。

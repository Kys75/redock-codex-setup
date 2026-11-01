#!/usr/bin/env python3
"""Open one selected/copied local path using its Herdr pane's context (macOS)."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
from urllib.parse import unquote, urlsplit


class ActionError(ValueError):
    pass


def reference_text(text):
    text = text.strip()
    if not text or len(text) > 8192 or any(ord(c) < 32 for c in text):
        raise ActionError("请选中并复制一条完整文件路径；不要包含多行文字。")
    markdown = re.fullmatch(r"\[[^\n]*\]\((.*)\)", text)
    if markdown:
        text = markdown[1]
    if len(text) >= 2 and (text[0], text[-1]) in (("`", "`"), ('"', '"'), ("'", "'"), ("<", ">")):
        text = text[1:-1]
    if text.startswith("file://"):
        url = urlsplit(text)
        if url.netloc not in ("", "localhost") or url.query:
            raise ActionError("仅支持这台 Mac 上的本地文件。")
        text = unquote(url.path) + ("#" + url.fragment if url.fragment else "")
    elif re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        raise ActionError("这是网页地址；此快捷键用于本地文件。")
    if not text or any(ord(c) < 32 for c in text):
        raise ActionError("文件路径为空或包含控制字符。")
    return text


def resolve_reference(text, cwd):
    text = reference_text(text)
    path = Path(text).expanduser()
    if not path.is_absolute():
        if not cwd or not Path(cwd).is_absolute():
            raise ActionError("无法确认当前对话的项目目录，请使用绝对路径。")
        path = Path(cwd) / path
    # A literal filename containing : or # takes precedence over line markers.
    if not path.exists():
        path = Path(re.sub(r"(?::\d+(?::\d+)?|#L\d+(?:C\d+)?(?:-L?\d+)?)$", "", str(path)))
    if not path.exists():
        raise ActionError(f"当前对话目录下没有这个文件：{text}")
    if not (path.is_file() or path.is_dir()):
        raise ActionError("此目标不是普通文件或文件夹。")
    # Normalize . and .. without changing the file the user selected via a symlink.
    return Path(os.path.abspath(path))


def session_prefix(title):
    match = re.search(r"(?:^| \| )([0-9a-f-]{29}|[0-9a-f-]{36})(?:\.\.\.|…)? \| codex(?: |$)", title or "")
    if not match:
        raise ActionError("无法确认当前 Codex 对话，请复制绝对路径。")
    prefix = match[1]
    if any((c != "-" if i in (8, 13, 18, 23) else c not in "0123456789abcdef") for i, c in enumerate(prefix)):
        raise ActionError("Codex 对话标识无效。")
    return prefix


def herdr_rpc(method, params):
    endpoint = os.environ.get("HERDR_SOCKET_PATH")
    if not endpoint:
        raise ActionError("请从 Herdr 的文件快捷键调用此操作。")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(endpoint)
        client.sendall((json.dumps({"id": "local-files", "method": method, "params": params}) + "\n").encode())
        with client.makefile("rb") as stream:
            reply = json.loads(stream.readline(2 * 1024 * 1024))
    if "error" in reply:
        raise ActionError("Herdr 无法确认当前窗格；请重试。")
    return reply["result"]


async def read_codex_cwd(endpoint, prefix):
    from websockets.asyncio.client import unix_connect

    async with unix_connect(path=str(endpoint), uri="ws://localhost/", open_timeout=2, close_timeout=1, max_size=2 * 1024 * 1024) as ws:
        async def rpc(i, method, params):
            await ws.send(json.dumps({"id": i, "method": method, "params": params}))
            for _ in range(64):
                reply = json.loads(await ws.recv())
                if reply.get("id") == i:
                    if "error" in reply:
                        raise ActionError("Codex 无法提供当前对话目录。")
                    return reply["result"]
            raise ActionError("Codex 没有返回对话目录。")

        await rpc(1, "initialize", {"clientInfo": {"name": "herdr-local-files", "version": "0.1.0"}, "capabilities": {}})
        await ws.send(json.dumps({"method": "initialized"}))
        loaded = await rpc(2, "thread/loaded/list", {"limit": 128})
        matches = [t for t in loaded["data"] if t.startswith(prefix)]
        if loaded.get("nextCursor") or len(matches) != 1:
            raise ActionError("当前 Codex 对话未唯一匹配；请使用绝对路径。")
        result = await rpc(3, "thread/read", {"threadId": matches[0], "includeTurns": False})
        thread = result["thread"]
        if thread["id"] != matches[0] or thread.get("status", {}).get("type") not in ("active", "idle"):
            raise ActionError("Codex 对话已退出或切换，请重新选择路径。")
        cwd = Path(thread["cwd"])
        if not cwd.is_absolute() or not cwd.is_dir():
            raise ActionError("Codex 返回的项目目录不可用。")
        return str(cwd)


def codex_cwd(prefix):
    config_dir = Path(os.environ["HERDR_PLUGIN_CONFIG_DIR"])
    settings_file = config_dir / "settings.json"
    settings = json.loads(settings_file.read_text()) if settings_file.exists() else {}
    codex_home = Path(settings.get("codex_home") or os.environ.get("CODEX_HOME") or "~/.codex").expanduser()
    endpoint = codex_home / "app-server-control" / "app-server-control.sock"
    if not endpoint.exists():
        raise ActionError("找不到 Codex 共享后台；请核实插件的 codex_home，或复制绝对路径。")

    async def bounded_read():
        return await asyncio.wait_for(read_codex_cwd(endpoint, prefix), timeout=4)

    return asyncio.run(bounded_read())


def pane_identity(pane):
    return (pane["terminal_id"], pane.get("agent"), session_prefix(pane.get("terminal_title")) if pane.get("agent") == "codex" else pane.get("cwd"))


def target_for_context(context, text, rpc=herdr_rpc, get_codex_cwd=codex_cwd):
    pane_id = context.get("focused_pane_id")
    if not pane_id:
        raise ActionError("没有目标窗格；请先点击显示文件路径的窗格。")
    pane = rpc("pane.get", {"pane_id": pane_id})["pane"]
    text = reference_text(text)
    absolute = Path(text).expanduser().is_absolute()
    if pane.get("agent") == "codex" and not absolute:
        identity = pane_identity(pane)
        info = rpc("pane.process_info", {"pane_id": pane_id})["process_info"]
        processes = [p for p in info.get("foreground_processes", []) if p["name"] == "codex"]
        if len(processes) != 1 or any(a in ("--remote", "--no-daemon") or a.startswith("--remote=") for a in (processes[0].get("argv") or [])):
            raise ActionError("当前窗格不是可确认的本地共享 Codex；请使用绝对路径。")
        cwd = get_codex_cwd(identity[2])
        current = rpc("pane.get", {"pane_id": pane_id})["pane"]
        if pane_identity(current) != identity:
            raise ActionError("对话刚刚切换了，请重新选择路径。")
    else:
        cwd = pane.get("foreground_cwd") or pane.get("cwd")
    return resolve_reference(text, cwd)


def open_target(path, action):
    # No shell evaluation, globbing, or command substitution of selected text.
    argv = ["/usr/bin/open"] + (["-R"] if action == "reveal" else []) + ["--", str(path)]
    subprocess.run(argv, check=True, timeout=10, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("open", "reveal"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        if sys.platform != "darwin":
            raise ActionError("此插件的打开/Finder 操作仅支持 macOS。")
        context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
        text = context.get("selected_text")
        if not text:
            text = subprocess.check_output(["/usr/bin/pbpaste"], text=True, timeout=2)
        target = target_for_context(context, text)
        if args.dry_run:
            print(json.dumps({"action": args.action, "path": str(target)}, ensure_ascii=False))
        else:
            open_target(target, args.action)
        return 0
    except Exception as exc:
        # The CLI boundary also handles optional WebSocket transport failures.
        message = str(exc) if isinstance(exc, ActionError) else "操作失败，请核实插件依赖和本机连接后重试。"
        print(message, file=sys.stderr)
        try:
            herdr_rpc("notification.show", {"title": "文件未打开", "body": message, "sound": "none"})
        except (OSError, ValueError, KeyError):
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())

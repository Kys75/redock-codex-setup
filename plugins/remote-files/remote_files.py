#!/usr/bin/env python3
"""Read one verified remote Herdr file and open a marked local copy on macOS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time

import file_actions

MAX_FILE = 64 * 1024 * 1024
MAX_REQUEST = 64 * 1024
REMOTE_COMMAND = 'exec "$HOME/.local/share/herdr-file-access/venv/bin/python" "$HOME/.local/share/herdr-file-access/remote_files.py" serve'
ACTIVE_SUFFIXES = {'.command', '.terminal', '.workflow', '.scpt', '.scptd', '.applescript',
                   '.pkg', '.mpkg', '.dmg', '.jar', '.exe', '.com', '.bat', '.cmd', '.desktop'}


def rpc_client(session, boot_id=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', session):
        raise ValueError('Invalid Herdr session')
    directory = Path.home() / '.config/herdr'
    if session != 'default':
        directory = directory / 'sessions' / session
    endpoint = directory / 'herdr.sock'
    identity = endpoint.stat()
    if boot_id is not None and not re.fullmatch(r'[1-9][0-9]*-[0-9]+', boot_id):
        raise ValueError('后台身份格式不兼容，请重新连接。')
    expected_pid = int(boot_id.split('-')[0]) if boot_id is not None else None
    # In 0.9.5 the API socket is bound before HeadlessServer creates its
    # pid-nanoseconds boot ID. A newer socket rejects a stale snapshot even if
    # the OS reused the old server PID after a restart.
    if boot_id is not None and identity.st_mtime_ns > int(boot_id.split('-')[1]):
        raise ValueError('Herdr 后台已变化，请重新连接后右键。')
    def rpc(method, params):
        current = endpoint.stat()
        if (current.st_dev, current.st_ino) != (identity.st_dev, identity.st_ino):
            raise ValueError('Herdr 后台已变化，请重新右键。')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(3)
            connection.connect(str(endpoint))
            if expected_pid is not None:
                if sys.platform == 'darwin':
                    peer_pid = connection.getsockopt(0, 2)  # SOL_LOCAL, LOCAL_PEERPID
                elif sys.platform.startswith('linux'):
                    peer_pid = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[0]
                else:
                    raise ValueError('当前远端系统尚不支持后台身份核对。')
                if peer_pid != expected_pid:
                    raise ValueError('Herdr 后台已变化，请重新连接后右键。')
            connection.sendall((json.dumps({'id': 'remote-files', 'method': method, 'params': params})+'\n').encode())
            with connection.makefile('rb') as reader:
                reply = json.loads(reader.readline(2 * 1024 * 1024))
        if 'error' in reply:
            raise ValueError('窗格内容已变化或暂不可读，请重新右键。')
        return reply['result']
    return rpc


def verified_target(request, rpc):
    pane_id = request['pane_id']
    expected = (request['workspace_id'], request['tab_id'], pane_id)
    def identity(pane):
        return tuple(pane.get(k) for k in ('workspace_id', 'tab_id', 'pane_id'))
    before = rpc('pane.get', {'pane_id': pane_id})['pane']
    if (identity(before) != expected or
            request.get('terminal_id', before['terminal_id']) != before['terminal_id']):
        raise ValueError('目标终端已变化，请重新右键。')
    selections = request['selections']
    if not 1 <= len(selections) <= 8:
        raise ValueError('请选择完整文件路径。')
    fragments = []
    for selection, text in selections:
        if selection['pane_id'] != pane_id or selection.get('content_revision') is None:
            raise ValueError('文件路径缺少内容版本。')
        actual = rpc('pane.selection.read', selection)
        if actual.get('pane_id') != pane_id or actual.get('text') != text:
            raise ValueError('路径所在文字已变化，请重新右键。')
        fragments.append(text)
    text = ''.join(fragments)
    path = file_actions.target_for_context({'focused_pane_id': pane_id}, text, rpc)
    after = rpc('pane.get', {'pane_id': pane_id})['pane']
    stable_keys = ('workspace_id', 'tab_id', 'pane_id', 'terminal_id', 'cwd', 'foreground_cwd', 'agent', 'terminal_title')
    if any(before.get(k) != after.get(k) for k in stable_keys):
        raise ValueError('对话或项目目录已变化，请重新右键。')
    return path


def serve(request, output):
    os.environ['HERDR_PLUGIN_CONFIG_DIR'] = str(Path(__file__).parent)
    rpc = rpc_client(request['session'], request['boot_id'])
    path = verified_target(request, rpc)
    # O_NONBLOCK avoids hanging on a FIFO if a file is replaced during the click.
    descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise ValueError('远端查看支持普通文件，请选择具体文件。')
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('远端查看支持普通文件，请选择具体文件。')
        if before.st_size > MAX_FILE:
            raise ValueError('文件超过 64 MiB，请使用专门的文件传输工具。')
        data = stream.read(MAX_FILE + 1)
        after = os.fstat(stream.fileno())
    if len(data) > MAX_FILE or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('文件正在变化，请稍后重新打开。')
    header = {'path': str(path), 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    output.write((json.dumps(header, ensure_ascii=False)+'\n').encode())
    output.write(data)
    output.flush()


def save_copy(header, data, profile, label, cache):
    if (not isinstance(header.get('path'), str) or not Path(header['path']).is_absolute()
            or header.get('size') != len(data) or len(data) > MAX_FILE
            or header.get('sha256') != hashlib.sha256(data).hexdigest()):
        raise ValueError('文件传输不完整，未打开缓存副本。')
    name = Path(header['path']).name
    if not name or name in ('.', '..') or any(ord(c) < 32 for c in name):
        raise ValueError('无效文件名。')
    digest = hashlib.sha256((profile+'\0'+header['path']+'\0'+header['sha256']).encode()).hexdigest()[:24]
    directory = cache / profile / digest
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = directory / 'content' / name
    if existing.exists() or existing.is_symlink():
        if (not existing.is_symlink() and existing.is_file()
                and existing.stat().st_size == len(data)
                and hashlib.sha256(existing.read_bytes()).hexdigest() == header['sha256']):
            return existing
        # A downloaded copy may have been edited locally. Preserve it and give
        # this download a fresh location instead of overwriting those edits.
        directory = Path(tempfile.mkdtemp(prefix=digest+'-', dir=cache/profile))
    content = directory / 'content'
    content.mkdir(exist_ok=True, mode=0o700)
    target = content / name
    with tempfile.NamedTemporaryFile(dir=content, delete=False) as temporary:
        temporary.write(data)
        temporary.flush()
        os.fsync(temporary.fileno())
        staged = Path(temporary.name)
    try:
        if sys.platform == 'darwin':
            subprocess.run(['/usr/bin/xattr', '-w', 'com.apple.quarantine',
                            '0083;%x;HerdrRemoteFiles;' % int(time.time()), str(staged)],
                           check=True, timeout=5, capture_output=True)
        staged.replace(target)
    finally:
        staged.unlink(missing_ok=True)
    source = dict(header, machine=label, profile=profile, fetched_at=time.time(),
                  copy_notice='下载副本；修改不会自动回写远端。')
    metadata = directory / 'source.json'
    metadata.write_text(json.dumps(source, ensure_ascii=False, indent=2)+'\n')
    return target


def open_copy(path, action):
    if action == 'open' and path.suffix.lower() in ACTIVE_SUFFIXES:
        raise ValueError('此类文件可能执行命令或安装软件，请选择“在 Finder 中显示副本”后自行处理。')
    file_actions.open_target(path, action)


def fetch(request, profile, target, session, label, cache=None):
    if not re.fullmatch(r'[a-f0-9]{32}', profile):
        raise ValueError('Invalid machine profile')
    request = dict(request, session=session)
    payload = json.dumps(request).encode()
    if len(payload) > MAX_REQUEST:
        raise ValueError('文件路径请求过长。')
    command = ['/usr/bin/ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
               '--', target, REMOTE_COMMAND]
    # Temporary files bound memory while SSH is running, and partial data is
    # never published to the cache. All file text travels through stdin JSON.
    with tempfile.TemporaryFile() as received, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=received, stderr=errors)
        try:
            process.communicate(payload, timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            raise ValueError('连接或文件获取超过 30 秒，请检查网络后重试。') from None
        if process.returncode:
            errors.seek(0)
            message = errors.read(4096).decode(errors='replace').strip()
            raise ValueError(message or '无法获取远端文件，请检查连接。')
        if received.tell() > MAX_FILE + MAX_REQUEST:
            raise ValueError('远端返回超过文件大小限制。')
        received.seek(0)
        line = received.readline(MAX_REQUEST)
        if not line.endswith(b'\n'):
            raise ValueError('远端文件信息不完整。')
        header = json.loads(line)
        data = received.read(MAX_FILE + 1)
    cache = cache or Path.home() / 'Library/Caches/HerdrRemoteFiles'
    return save_copy(header, data, profile, label, cache)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('serve', 'fetch'))
    parser.add_argument('--profile')
    parser.add_argument('--target')
    parser.add_argument('--session', default='default')
    parser.add_argument('--label', default='Remote')
    args = parser.parse_args()
    try:
        payload = sys.stdin.buffer.read(MAX_REQUEST+1)
        if len(payload) > MAX_REQUEST:
            raise ValueError('Request too large')
        request = json.loads(payload)
        if args.mode == 'serve':
            serve(request, sys.stdout.buffer)
        else:
            if sys.platform != 'darwin':
                raise ValueError('打开文件副本需要在 Mac 显示端运行。')
            if request.get('action') not in ('open', 'reveal'):
                raise ValueError('Invalid action')
            path = fetch(request, args.profile, args.target, args.session, args.label)
            open_copy(path, request['action'])
            print(json.dumps({'path': str(path), 'machine': args.label}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(str(exc)[:4096], file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

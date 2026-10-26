#!/usr/bin/env python3
"""Optional local Redock/Herdr adapter. Python 3.11+, standard library only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import uuid

VERSION = '0.1.0'
MUX_KEYS = ('HERDR_ENV', 'HERDR_SOCKET_PATH', 'HERDR_PANE_ID',
            'HERDR_WORKSPACE_ID', 'HERDR_TAB_ID', 'HERDR_SESSION', 'TMUX', 'TMUX_PANE')


def codex_home(explicit=None, env=None, home=None):
    env = os.environ if env is None else env
    home = Path.home() if home is None else Path(home)
    return Path(explicit or env.get('CODEX_HOME') or home / '.codex').expanduser().resolve()


def data_dir(chome):
    base = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
    profile = hashlib.sha256(str(chome).encode()).hexdigest()[:12]
    return (base / 'redock-codex-setup' / profile).expanduser().resolve()


def atomic_write(path, text, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.redock-')
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(text)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def executable(value, name):
    found = value or shutil.which(name)
    if not found:
        raise ValueError(f'{name} not found; install the official tool first.')
    path = Path(found).expanduser().absolute()
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f'{name} is not executable.')
    # Keep a package manager's launcher pathname (Node launchers may use it).
    return str(path)


def hook_entries(document):
    groups_by_event = document.get('hooks')
    if not isinstance(groups_by_event, dict):
        raise ValueError('Expected a hooks.json object with a hooks mapping.')
    for groups in groups_by_event.values():
        if not isinstance(groups, list):
            raise ValueError('Unsupported hook group format.')
        for group in groups:
            for entry in group.get('hooks', []):
                if isinstance(entry, dict) and entry.get('type') == 'command':
                    yield entry


def official_redock_flags(command):
    """Recognize only the exact official Codex agent-event command shape."""
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    if not words or Path(words[0]).name != 'redock-hook':
        return None
    rest = words[1:]
    required = ['agent-event', '--agent', 'codex', '--stdin']
    if rest == required:
        return []
    if rest == required + ['--chat-only']:
        return ['--chat-only']
    return None


def installation(args):
    if os.name != 'posix':
        raise ValueError('The adapter supports macOS/Linux/WSL. Native Windows is not supported.')
    chome = codex_home(args.codex_home)
    root = Path(args.install_dir).expanduser().resolve() if args.install_dir else data_dir(chome)
    source = Path(__file__).resolve()
    if (any((parent / '.git').exists() for parent in (root, *root.parents)) or
            (source.parent.name == 'scripts' and root.is_relative_to(source.parent.parent))):
        raise ValueError('Choose a private install directory outside Git repositories and this source checkout.')
    hooks_path = chome / 'hooks.json'
    if hooks_path.is_symlink():
        raise ValueError('hooks.json is a symlink; review its actual owner before changing it.')
    if not hooks_path.is_file():
        raise ValueError('No hooks.json here. Complete official Redock pairing in the actual CODEX_HOME first.')
    if (root / 'manifest.json').exists():
        raise ValueError('An installation already exists. Review it or uninstall before reinstalling.')
    config_path = chome / 'config.toml'
    if config_path.exists():
        config = tomllib.loads(config_path.read_text())
        inline = {k: v for k, v in config.get('hooks', {}).items()
                  if k not in ('state', 'managed_dir', 'windows_managed_dir')}
        if inline:
            raise ValueError('Inline hook definitions also exist. Have the Agent review them first.')
    raw = hooks_path.read_text()
    document = json.loads(raw)
    cfg = {
        'version': VERSION,
        'codex_home': str(chome),
        'codex_bin': executable(args.codex_bin, 'codex'),
        'redock_hook': executable(args.redock_hook, 'redock-hook'),
        'herdr_socket': str(Path(args.herdr_socket).expanduser().absolute()),
        'herdr_session': args.herdr_session,
        'root': str(root),
    }
    if Path(cfg['codex_bin']).resolve() == (root / 'bin/codex').resolve():
        raise ValueError('Select the real Codex executable, not the installed reader itself.')
    replacements = {}
    count = 0
    for entry in hook_entries(document):
        old = entry.get('command', '')
        flags = official_redock_flags(old)
        if flags is None:
            continue
        new = shlex.join([sys.executable, str(root / 'adapter.py'), 'hook',
                          '--settings', str(root / 'settings.json'), *flags])
        if new in replacements and replacements[new] != old:
            raise ValueError('Multiple different Redock executables found; resolve them before installation.')
        replacements[new] = old
        entry['command'] = new
        count += 1
    if not count:
        raise ValueError('No exact official Redock Codex hooks found. Custom wrappers are not overwritten.')
    return root, hooks_path, raw, document, cfg, replacements, count


def install(args):
    root, hooks_path, raw, document, cfg, replacements, count = installation(args)
    print(f'{count} official Redock hook commands will be wrapped; other hooks stay in place.')
    print('Writes: private adapter/settings/reader/backup and the selected hooks.json.')
    print('Does not edit shell files, config.toml, credentials, permissions or hook trust.')
    if not args.apply:
        print('Preview only. Add --apply to install.')
        return
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    # Recheck immediately before changing user configuration.
    if hooks_path.read_text() != raw:
        raise ValueError('hooks.json changed during preparation; retry after reviewing the new version.')
    reader = '#!/bin/sh\nexport CODEX_HOME=' + shlex.quote(cfg['codex_home']) + '\n'
    reader += 'exec ' + shlex.quote(cfg['codex_bin']) + ' "$@"\n'
    atomic_write(root / 'adapter.py', Path(__file__).read_text(), 0o700)
    atomic_write(root / 'bin/codex', reader, 0o700)
    atomic_write(root / 'settings.json', encoded(cfg))
    atomic_write(root / 'backups/original-hooks.json', raw)
    atomic_write(root / 'manifest.json', encoded({
        'hooks_path': str(hooks_path), 'replacements': replacements, 'version': VERSION}))
    atomic_write(hooks_path, encoded(document))
    print('Installed. Review the changed Redock definitions in Codex /hooks before relying on them.')


def uninstall(args):
    chome = codex_home(args.codex_home)
    root = Path(args.install_dir).expanduser().resolve() if args.install_dir else data_dir(chome)
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    hooks_path = Path(manifest['hooks_path'])
    if hooks_path != chome / 'hooks.json' or hooks_path.is_symlink():
        raise ValueError('Installation does not match the selected CODEX_HOME.')
    raw = hooks_path.read_text()
    document = json.loads(raw)
    restored = 0
    for entry in hook_entries(document):
        old = manifest['replacements'].get(entry.get('command'))
        if old is not None:
            entry['command'] = old
            restored += 1
    if not restored:
        raise ValueError('Managed commands were changed or removed. Nothing overwritten; review the backup locally.')
    print(f'{restored} managed commands will be restored; later unrelated hook edits are preserved.')
    if not args.apply:
        print('Preview only. Add --apply to uninstall.')
        return
    if hooks_path.read_text() != raw:
        raise ValueError('hooks.json changed; retry after review.')
    atomic_write(root / 'backups/before-uninstall.json', raw)
    atomic_write(hooks_path, encoded(document))
    manifest_path.rename(root / ('uninstalled-' + str(time.time_ns()) + '.json'))
    print('Uninstalled commands. Private files/backups retained. Review restored hooks in /hooks.')


def rpc(cfg, method, params):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(0.25)
        client.connect(cfg['herdr_socket'])
        client.sendall((json.dumps({'id': 'redock-local', 'method': method, 'params': params}) + '\n').encode())
        with client.makefile('rb') as stream:
            response = json.loads(stream.readline(2 * 1024 * 1024))
    if 'error' in response:
        raise ValueError('Herdr API rejected the request.')
    return response['result']


def matching_panes(sid, call):
    if not isinstance(sid, str) or str(uuid.UUID(sid)) != sid:
        return []
    found = []
    for pane in call('pane.list', {}).get('panes', []):
        title = pane.get('terminal_title', '')
        match = re.match(r'^([0-9a-f-]{24,36})(?:\.\.\.|…)? \| codex(?: |$)', title)
        if pane.get('agent') != 'codex' or not match or not sid.startswith(match[1]):
            continue
        info = call('pane.process_info', {'pane_id': pane['pane_id']})['process_info']
        if any(p.get('name') == 'codex' and '--no-daemon' not in p.get('argv', [])
               for p in info.get('foreground_processes', [])):
            found.append(pane)
    return found


def routed_environment(payload, inherited, cfg, call):
    env = inherited.copy()
    # Pin only this reader to the chosen profile; don't modify the user's PATH globally.
    env['PATH'] = str(Path(cfg['root']) / 'bin') + os.pathsep + env.get('PATH', '')
    env['CODEX_HOME'] = cfg['codex_home']
    panes = matching_panes(payload.get('session_id'), call)
    if len(panes) != 1:
        # A shared daemon may have inherited a now-stale Herdr pane at startup.
        if env.get('HERDR_ENV') or panes:
            for key in MUX_KEYS:
                env.pop(key, None)
        return env, None
    pane = panes[0]
    for key in MUX_KEYS:
        env.pop(key, None)
    env.update(HERDR_ENV='1', HERDR_SOCKET_PATH=cfg['herdr_socket'],
               HERDR_SESSION=cfg['herdr_session'], HERDR_PANE_ID=pane['pane_id'],
               HERDR_TAB_ID=pane['tab_id'], HERDR_WORKSPACE_ID=pane['workspace_id'])
    return env, pane


def deliver(raw, cfg, chat_only=False):
    env = os.environ.copy()
    env['PATH'] = str(Path(cfg['root']) / 'bin') + os.pathsep + env.get('PATH', '')
    env['CODEX_HOME'] = cfg['codex_home']
    pane = None
    call = lambda method, params: rpc(cfg, method, params)
    try:
        payload = json.loads(raw)
        env, pane = routed_environment(payload, env, cfg, call)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # Never send an event to stale inherited Herdr coordinates after lookup failure.
        if env.get('HERDR_ENV'):
            for key in MUX_KEYS:
                env.pop(key, None)
    if pane:
        try:
            call('pane.report_agent_session', {
                'pane_id': pane['pane_id'], 'source': 'herdr:codex', 'agent': 'codex',
                'agent_session_id': payload['session_id'], 'seq': time.time_ns(),
                'resume_argv': ['codex', 'resume', payload['session_id']],
            })
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # Identity reporting is best-effort; verified event routing remains valid.
            pass
    command = [cfg['redock_hook'], 'agent-event', '--agent', 'codex', '--stdin']
    if chat_only:
        command.append('--chat-only')
    return subprocess.run(command, input=raw, env=env).returncode


def bind(args):
    chome = codex_home(args.codex_home)
    root = Path(args.install_dir).expanduser().resolve() if args.install_dir else data_dir(chome)
    cfg = json.loads((root / 'settings.json').read_text())
    if cfg['codex_home'] != str(chome):
        raise ValueError('Selected installation uses a different CODEX_HOME.')
    sid = str(uuid.UUID(args.session_id))
    panes = matching_panes(sid, lambda m, p: rpc(cfg, m, p))
    if len(panes) != 1 or panes[0]['pane_id'] != args.pane_id:
        raise ValueError('No unique live shared Codex matches that conversation and pane.')
    files = list((chome / 'sessions').glob('*/*/*/*' + sid + '.jsonl'))
    if len(files) != 1:
        raise ValueError('Expected one legacy JSONL rollout. New storage formats require separate support.')
    with files[0].open() as stream:
        meta = json.loads(next(stream))
    if meta.get('type') != 'session_meta' or meta.get('payload', {}).get('id') != sid:
        raise ValueError('Transcript identity does not match.')
    print('Verified one existing conversation and live pane. No model prompt will be sent.')
    if not args.apply:
        print('Preview only. Add --apply to register it in Redock.')
        return
    payload = {'hook_event_name': 'SessionStart', 'session_id': sid,
               'cwd': meta['payload']['cwd'], 'transcript_path': str(files[0]), 'source': 'resume'}
    code = deliver(json.dumps(payload).encode(), cfg, chat_only=True)
    if code:
        raise ValueError('Redock registration failed.')
    print('Registered history. Send the next normal message in the terminal to verify live turn status.')


def doctor(args):
    chome = codex_home(args.codex_home)
    report = {'python': '.'.join(map(str, sys.version_info[:3])), 'platform': sys.platform,
              'codex_home_source': 'argument' if args.codex_home else 'environment' if os.getenv('CODEX_HOME') else 'default',
              'codex_home_exists': chome.is_dir(), 'hooks_json_exists': (chome / 'hooks.json').is_file(),
              'herdr_socket_exists': Path(args.herdr_socket).expanduser().exists()}
    for name in ('codex', 'herdr', 'redock-hook'):
        path = shutil.which(name)
        version = None
        if path:
            try:
                result = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=5)
                match = re.search(r'\b\d+\.\d+\.\d+\b', result.stdout)
                version = match[0] if match else 'unknown'
            except (OSError, subprocess.TimeoutExpired):
                version = 'unavailable'
        report[name] = {'found_on_path': bool(path), 'version': version}
    print(encoded(report), end='')
    print('Shell aliases/functions are not resolved. Verify them locally before applying changes.')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--version', action='version', version=VERSION)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('doctor', 'install', 'uninstall', 'bind'):
        child = sub.add_parser(name)
        child.add_argument('--codex-home', help='Default: CODEX_HOME, otherwise ~/.codex')
        child.add_argument('--install-dir', help='Private installation directory outside the repository')
        if name in ('doctor', 'install'):
            child.add_argument('--herdr-socket', default=str(Path.home() / '.config/herdr/herdr.sock'))
        if name == 'install':
            child.add_argument('--herdr-session', default='default')
            child.add_argument('--codex-bin')
            child.add_argument('--redock-hook')
        if name != 'doctor':
            child.add_argument('--apply', action='store_true')
        if name == 'bind':
            child.add_argument('--session-id', required=True)
            child.add_argument('--pane-id', required=True)
    child = sub.add_parser('hook', help=argparse.SUPPRESS)
    child.add_argument('--settings', required=True)
    child.add_argument('--chat-only', action='store_true')
    return p


def main():
    args = parser().parse_args()
    try:
        if args.command == 'hook':
            return deliver(sys.stdin.buffer.read(), json.loads(Path(args.settings).read_text()), args.chat_only)
        globals()[args.command](args)
        return 0
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        # Exception paths can contain private local names; do not dump tracebacks.
        print('Operation failed: ' + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

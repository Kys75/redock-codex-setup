#!/usr/bin/env python3
"""Restore verified live Codex bindings after a shared daemon restart."""

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import tempfile
import uuid


class RestoreError(Exception):
    pass


def read_registry(path):
    if path.is_symlink():
        raise RestoreError('registry_symlink')
    doc = json.loads(path.read_text())
    if (not isinstance(doc, dict) or doc.get('schema') != 1
            or not isinstance(doc.get('sessions'), list)
            or not all(isinstance(r, dict) for r in doc['sessions'])):
        raise RestoreError('unsupported_registry_schema')
    return doc


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(prefix='.restore-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def key(row):
    terminal = row.get('terminal') or {}
    return (row.get('agent'), row.get('session_id'), row.get('multiplexer_socket'),
            terminal.get('kind'), terminal.get('session'), terminal.get('pane_id'))


def restore_records(path, expected):
    """Only reactivate unchanged ended records; preserve all other fields."""
    if not expected:
        return []
    # redock-hook v1.1.6 uses mkdir/rmdir, NOT an advisory flock file.
    lock = path.parent / '.registry.lock'
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise RestoreError('registry_busy') from None
    try:
        doc = read_registry(path)
        restored = []
        for old in expected:
            matches = [r for r in doc['sessions'] if key(r) == key(old)]
            # Compare the complete row under the native lock. Never overwrite a
            # prompt, completion, or exit event that arrived after the scan.
            if len(matches) == 1 and matches[0] == old and old.get('session_state') == 'ended':
                matches[0]['session_state'] = 'active'
                restored.append(old['session_id'])
        if restored:
            atomic_json(path, doc)
        return restored
    finally:
        lock.rmdir()


def title_prefix(pane):
    if pane.get('agent') != 'codex':
        return None
    match = re.match(r'^([0-9a-f-]{24,36})(?:\.\.\.|…)? \| codex(?: |$)',
                     pane.get('terminal_title', ''))
    if not match:
        return None
    return match[1]


def pane_identity(pane):
    return (pane.get('pane_id'), pane.get('terminal_id'), pane.get('workspace_id'),
            pane.get('tab_id'), title_prefix(pane))


def select_candidates(doc, panes, cfg):
    candidates = []
    for row in doc['sessions']:
        terminal = row.get('terminal') or {}
        sid = row.get('session_id')
        try:
            valid_id = isinstance(sid, str) and str(uuid.UUID(sid)) == sid
        except ValueError:
            valid_id = False
        if (not valid_id or row.get('agent') != 'codex' or row.get('session_state') != 'ended'
                or terminal.get('kind') != 'herdr' or terminal.get('session') != cfg['herdr_session']
                or row.get('multiplexer_socket') != cfg['herdr_socket']):
            continue
        matches = [p for p in panes if title_prefix(p) and sid.startswith(title_prefix(p))]
        if (len(matches) == 1 and matches[0].get('terminal_id')
                and matches[0].get('pane_id') == terminal.get('pane_id')):
            candidates.append((row, matches[0]))
    return candidates


def herdr_rpc(cfg, method, params):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(1)
        client.connect(cfg['herdr_socket'])
        client.sendall((json.dumps({'id': 'redock-restore', 'method': method, 'params': params}) + '\n').encode())
        with client.makefile('rb') as stream:
            reply = json.loads(stream.readline(2 * 1024 * 1024))
    if 'error' in reply:
        raise RestoreError('herdr_rpc_unavailable')
    return reply['result']


def foreground_identity(call, pane_id):
    processes = call('pane.process_info', {'pane_id': pane_id})['process_info'].get('foreground_processes', [])
    shared = [p for p in processes if p.get('name') == 'codex' and p.get('pid')
              and p.get('argv') and not any(a == '--no-daemon' or a.startswith('--remote') for a in p['argv'])]
    if len(shared) != 1:
        return None
    return shared[0]['pid'], tuple(shared[0]['argv'])


async def read_threads(endpoint, ids):
    from websockets.asyncio.client import unix_connect

    async with unix_connect(path=str(endpoint), uri='ws://localhost/', open_timeout=2,
                            close_timeout=1, max_size=2 * 1024 * 1024) as ws:
        sequence = 0

        async def rpc(method, params):
            nonlocal sequence
            sequence += 1
            await ws.send(json.dumps({'id': sequence, 'method': method, 'params': params}))
            while True:
                reply = json.loads(await ws.recv())
                if reply.get('id') == sequence:
                    if 'error' in reply:
                        raise RestoreError('codex_rpc_unavailable')
                    return reply['result']

        await rpc('initialize', {'clientInfo': {'name': 'redock-binding-restore', 'version': '0.1.0'},
                                 'capabilities': {}})
        await ws.send(json.dumps({'method': 'initialized'}))
        loaded, seen_cursors, cursor = set(), set(), None
        while True:
            result = await rpc('thread/loaded/list', {'limit': 128, 'cursor': cursor})
            loaded.update(result['data'])
            cursor = result.get('nextCursor')
            if not cursor:
                break
            if cursor in seen_cursors:
                raise RestoreError('repeated_codex_cursor')
            seen_cursors.add(cursor)
        threads = {}
        for sid in ids & loaded:
            thread = (await rpc('thread/read', {'threadId': sid, 'includeTurns': False}))['thread']
            # Do not retain the preview, title, or conversation content.
            threads[sid] = {k: thread.get(k) for k in ('id', 'status', 'path', 'cwd', 'ephemeral')}
        return threads


def live_threads(cfg, ids):
    from websockets.exceptions import WebSocketException

    endpoint = Path(cfg['codex_home']) / 'app-server-control/app-server-control.sock'

    async def bounded():
        return await asyncio.wait_for(read_threads(endpoint, ids), timeout=8)

    try:
        return asyncio.run(bounded())
    except WebSocketException as exc:
        raise RestoreError('codex_transport_unavailable') from exc


def valid_thread(row, thread, cfg):
    if (not thread or thread.get('id') != row['session_id'] or thread.get('ephemeral')
            or (thread.get('status') or {}).get('type') not in ('idle', 'active')):
        return False
    if not all(isinstance(x, str) and x for x in (thread.get('path'), thread.get('cwd'),
                                                  row.get('transcript_path'), row.get('cwd'))):
        return False
    path = Path(thread['path']).resolve()
    if (path != Path(row['transcript_path']).resolve() or not path.is_file()
            or not path.is_relative_to((Path(cfg['codex_home']) / 'sessions').resolve())
            or Path(thread['cwd']).resolve() != Path(row['cwd']).resolve()):
        return False
    with path.open() as stream:
        meta = json.loads(stream.readline(1024 * 1024))
    return meta.get('type') == 'session_meta' and meta.get('payload', {}).get('id') == row['session_id']


def scan(cfg, apply=False, call=None, get_threads=None):
    path = Path(cfg['registry_path'])
    doc = read_registry(path)
    result = {'status': 'ok', 'candidates': 0, 'verified': [], 'restored': []}
    if not any(r.get('session_state') == 'ended' and (r.get('terminal') or {}).get('kind') == 'herdr'
               for r in doc['sessions']):
        return result
    call = call or (lambda method, params: herdr_rpc(cfg, method, params))
    candidates = select_candidates(doc, call('pane.list', {})['panes'], cfg)
    result['candidates'] = len(candidates)
    if not candidates:
        return result
    # This is a deliberately version-gated compatibility repair of private
    # registry state. A different binary requires its locking/schema contract
    # to be verified again, even if its advertised version did not change.
    digest = hashlib.sha256(Path(cfg['redock_hook']).read_bytes()).hexdigest()
    if digest != cfg['verified_redock_sha256']:
        raise RestoreError('redock_binary_changed_revalidate_required')
    identities = {p['pane_id']: foreground_identity(call, p['pane_id']) for _, p in candidates}
    candidates = [(r, p) for r, p in candidates if identities[p['pane_id']]]
    if not candidates:
        return result
    threads = (get_threads or (lambda ids: live_threads(cfg, ids)))({r['session_id'] for r, _ in candidates})
    refreshed = call('pane.list', {})['panes']
    current = {p['pane_id']: p for p in refreshed}
    verified = []
    for row, pane in candidates:
        live = current.get(pane['pane_id'], {})
        if (pane_identity(live) != pane_identity(pane)
                or len([p for p in refreshed if title_prefix(p) and row['session_id'].startswith(title_prefix(p))]) != 1
                or foreground_identity(call, pane['pane_id']) != identities[pane['pane_id']]):
            continue
        if valid_thread(row, threads.get(row['session_id']), cfg):
            verified.append(row)
    result['verified'] = [r['session_id'] for r in verified]
    if apply:
        result['restored'] = restore_records(path, verified)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', required=True, type=Path)
    parser.add_argument('--apply', action='store_true', help='Default: read-only preview')
    args = parser.parse_args()
    cfg = json.loads(args.settings.read_text())
    try:
        result = scan(cfg, apply=args.apply)
    except RestoreError as exc:
        result = {'status': 'skipped', 'reason': str(exc), 'restored': []}
    except (OSError, ValueError, KeyError, TypeError, TimeoutError):
        result = {'status': 'skipped', 'reason': 'dependency_unavailable_or_invalid', 'restored': []}
    result['checked_at'] = datetime.now(timezone.utc).isoformat()
    if args.apply:
        state = Path(cfg['state_dir'])
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        previous = json.loads((state / 'status.json').read_text()) if (state / 'status.json').exists() else {}
        atomic_json(state / 'status.json', result)
        if result['restored'] or result.get('reason') != previous.get('reason'):
            with (state / 'events.jsonl').open('a') as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(json.dumps(result) + '\n')
    else:
        print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

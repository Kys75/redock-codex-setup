import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/redock_codex.py'
spec = importlib.util.spec_from_file_location('adapter', SCRIPT)
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)
SID = '11111111-1111-4111-8111-111111111111'
OTHER = '22222222-2222-4222-8222-222222222222'


class HomeSelection(unittest.TestCase):
    def test_default_is_normal_codex_home(self):
        self.assertEqual(adapter.codex_home(env={}, home='/tmp/example-user'),
                         Path('/tmp/example-user/.codex').resolve())

    def test_explicit_beats_environment(self):
        self.assertEqual(adapter.codex_home('/tmp/explicit', {'CODEX_HOME': '/tmp/environment'}),
                         Path('/tmp/explicit').resolve())

    def test_environment_is_honored(self):
        self.assertEqual(adapter.codex_home(env={'CODEX_HOME': '/tmp/custom'}), Path('/tmp/custom').resolve())


def pane(sid=SID, pid='w1:p1'):
    return {'agent': 'codex', 'pane_id': pid, 'tab_id': 'w1:t1', 'workspace_id': 'w1',
            'terminal_title': sid[:26] + '... | codex | Example'}


class Routing(unittest.TestCase):
    def setUp(self):
        self.cfg = {'root': '/tmp/adapter', 'codex_home': '/tmp/custom',
                    'herdr_socket': '/tmp/herdr.sock', 'herdr_session': 'default'}

    def route(self, panes, argv=None, env=None):
        def rpc(method, params):
            if method == 'pane.list':
                return {'panes': panes}
            return {'process_info': {'foreground_processes': [
                {'name': 'codex', 'argv': argv or ['codex', 'resume', OTHER]}]}}
        return adapter.routed_environment({'session_id': SID}, env or {'PATH': '/bin'}, self.cfg, rpc)

    def test_distinct_conversations_select_only_the_live_target(self):
        env, target = self.route([pane(OTHER, 'w2:p2'), pane()], env={'TMUX_PANE': '%1'})
        self.assertEqual(env['HERDR_PANE_ID'], 'w1:p1')
        self.assertNotIn('TMUX_PANE', env)
        self.assertEqual(env['CODEX_HOME'], '/tmp/custom')

    def test_resume_switch_uses_current_title_not_original_process_arguments(self):
        self.assertIsNotNone(self.route([pane()], argv=['codex', 'resume', OTHER])[1])

    def test_stale_report_and_inherited_pane_are_not_used(self):
        p = pane(OTHER)
        p['agent_session'] = {'value': SID}
        env, target = self.route([p], env={'HERDR_ENV': '1', 'HERDR_PANE_ID': 'w1:p1'})
        self.assertIsNone(target)
        self.assertNotIn('HERDR_PANE_ID', env)

    def test_duplicate_conversation_is_not_routed(self):
        env, target = self.route([pane(), pane(pid='w1:p2')], env={'TMUX': 'old'})
        self.assertIsNone(target)
        self.assertNotIn('TMUX', env)

    def test_standalone_lock_screen_is_not_a_shared_target(self):
        self.assertIsNone(self.route([pane()], argv=['codex', '--no-daemon'])[1])

    def test_shell_with_stale_title_is_ignored(self):
        p = pane()
        p.pop('agent')
        self.assertIsNone(self.route([p])[1])

    def test_tmux_native_context_survives_when_no_herdr_target_exists(self):
        env, target = self.route([], env={'TMUX': 'native', 'TMUX_PANE': '%2'})
        self.assertEqual(env['TMUX_PANE'], '%2')

    def test_runtime_forwards_original_bytes_and_flags(self):
        raw = b'{"session_id":"' + SID.encode() + b'", "prompt":"hello"}\n'
        cfg = {**self.cfg, 'redock_hook': '/tmp/redock-hook'}
        with patch.object(adapter, 'rpc', side_effect=OSError), patch.object(adapter.subprocess, 'run') as run:
            run.return_value.returncode = 7
            self.assertEqual(adapter.deliver(raw, cfg, True), 7)
            self.assertEqual(run.call_args.kwargs['input'], raw)
            self.assertEqual(run.call_args.args[0][-1], '--chat-only')

    def test_report_failure_does_not_discard_verified_route(self):
        def rpc(cfg, method, params):
            if method == 'pane.list':
                return {'panes': [pane()]}
            if method == 'pane.process_info':
                return {'process_info': {'foreground_processes': [{'name': 'codex', 'argv': ['codex']}]}}
            raise ValueError('report unsupported')
        with patch.object(adapter, 'rpc', side_effect=rpc), patch.object(adapter.subprocess, 'run') as run:
            adapter.deliver(json.dumps({'session_id': SID}).encode(),
                            {**self.cfg, 'redock_hook': '/tmp/redock-hook'})
            self.assertEqual(run.call_args.kwargs['env'].get('HERDR_PANE_ID'), 'w1:p1')


class InstallLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='redock-tests-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'profile with spaces'
        self.home.mkdir()
        self.root = self.base / 'private adapter'
        self.codex = self.base / 'fake codex'
        self.codex.write_text('#!/bin/sh\nprintf "%s\\n" "$CODEX_HOME" "$@"\n')
        self.codex.chmod(0o700)
        self.redock = self.base / 'redock-hook'
        self.redock.write_text('#!/bin/sh\nexit 0\n')
        self.redock.chmod(0o700)
        self.original_command = adapter.shlex.join([str(self.redock), 'agent-event', '--agent', 'codex', '--stdin'])
        self.other = {'type': 'command', 'command': 'echo unrelated-hook', 'timeout': 8}
        self.document = {'description': 'existing user settings', 'hooks': {
            'Stop': [{'matcher': '', 'hooks': [dict(self.other), {
                'type': 'command', 'command': self.original_command, 'timeout': 3}]}],
            'SessionStart': [{'hooks': [{'type': 'command', 'command': 'bash herdr-agent-state.sh session'}]}]}}
        self.hooks = self.home / 'hooks.json'
        self.hooks.write_text(json.dumps(self.document, indent=4))
        self.before = self.hooks.read_bytes()
        self.args = argparse.Namespace(codex_home=str(self.home), install_dir=str(self.root),
            codex_bin=str(self.codex), redock_hook=str(self.redock),
            herdr_socket='/tmp/example.sock', herdr_session='default', apply=False)

    def install(self):
        with contextlib.redirect_stdout(io.StringIO()):
            adapter.install(self.args)

    def test_preview_makes_no_files_or_changes(self):
        self.install()
        self.assertEqual(self.hooks.read_bytes(), self.before)
        self.assertFalse(self.root.exists())

    def test_installation_inside_git_worktree_is_refused(self):
        (self.base / '.git').write_text('gitdir: /example/worktree')
        with self.assertRaisesRegex(ValueError, 'outside Git'):
            self.install()
        self.assertEqual(self.hooks.read_bytes(), self.before)

    def test_reader_cannot_point_back_to_itself(self):
        self.args.codex_bin = str(self.root / 'bin/codex')
        reader = self.root / 'bin/codex'
        reader.parent.mkdir(parents=True)
        reader.write_text('#!/bin/sh\nexit 0\n')
        reader.chmod(0o700)
        with self.assertRaisesRegex(ValueError, 'reader itself'):
            self.install()

    def test_installed_hook_delivers_event_and_reader_home_through_real_socket(self):
        # Exercise the actual installed command, socket protocol and spawned reader.
        with tempfile.TemporaryDirectory(prefix='rd-', dir='/tmp') as short:
            sock_path = str(Path(short) / 'h.sock')
            self.args.herdr_socket = sock_path
            capture = self.base / 'capture.json'
            self.redock.write_text('#!' + sys.executable + '\n' +
                'import json, os, pathlib, subprocess, sys\n' +
                'raw = sys.stdin.buffer.read()\n' +
                'result = {"raw": raw.hex(), "argv": sys.argv[1:],\n' +
                '"pane": os.environ.get("HERDR_PANE_ID"),\n' +
                '"tmux": os.environ.get("TMUX"),\n' +
                '"reader": subprocess.check_output(["codex", "--version"], text=True)}\n' +
                'pathlib.Path(' + repr(str(capture)) + ').write_text(json.dumps(result))\n')
            self.args.apply = True
            self.install()
            command = json.loads(self.hooks.read_text())['hooks']['Stop'][0]['hooks'][1]['command']
            requests = []
            errors = []
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(sock_path)
                server.listen()
                server.settimeout(5)
                def serve():
                    try:
                        for _ in range(3):
                            conn, _ = server.accept()
                            with conn, conn.makefile('rb') as stream:
                                req = json.loads(stream.readline())
                                requests.append(req)
                                if req['method'] == 'pane.list':
                                    result = {'panes': [pane()]}
                                elif req['method'] == 'pane.process_info':
                                    result = {'process_info': {'foreground_processes': [
                                        {'name': 'codex', 'argv': ['codex', 'resume', SID]}]}}
                                else:
                                    result = {'ok': True}
                                conn.sendall((json.dumps({'result': result}) + '\n').encode())
                    except Exception as exc:
                        errors.append(exc)
                worker = threading.Thread(target=serve, daemon=True)
                worker.start()
                raw = ('{ "session_id": "' + SID + '", "prompt": "hello" }\n').encode()
                result = subprocess.run(command, shell=True, input=raw, capture_output=True,
                                        env={**os.environ, 'TMUX': 'stale', 'CODEX_HOME': '/wrong'}, timeout=10)
                worker.join(timeout=6)
            self.assertFalse(errors)
            self.assertEqual(result.returncode, 0, result.stderr)
            readback = json.loads(capture.read_text())
            self.assertEqual(bytes.fromhex(readback['raw']), raw)
            self.assertEqual(readback['argv'], ['agent-event', '--agent', 'codex', '--stdin'])
            self.assertEqual(readback['pane'], 'w1:p1')
            self.assertIsNone(readback['tmux'])
            self.assertEqual(readback['reader'].splitlines(), [str(self.home.resolve()), '--version'])
            self.assertEqual(requests[-1]['params']['agent_session_id'], SID)
            self.assertEqual(requests[-1]['params']['source'], 'herdr:codex')

    def test_install_preserves_other_hooks_and_custom_home_reader(self):
        self.args.apply = True
        self.install()
        after = json.loads(self.hooks.read_text())
        self.assertEqual(after['hooks']['Stop'][0]['hooks'][0], self.other)
        self.assertEqual(after['hooks']['SessionStart'], self.document['hooks']['SessionStart'])
        result = subprocess.check_output([str(self.root / 'bin/codex'), 'resume', SID], text=True)
        self.assertEqual(result.splitlines(), [str(self.home.resolve()), 'resume', SID])
        self.assertEqual((self.root / 'backups/original-hooks.json').read_bytes(), self.before)
        self.assertEqual((self.root / 'settings.json').stat().st_mode & 0o777, 0o600)

    def test_uninstall_preserves_changes_added_after_install(self):
        self.args.apply = True
        self.install()
        after = json.loads(self.hooks.read_text())
        after['hooks']['Stop'][0]['hooks'].append({'type': 'command', 'command': 'echo added-later'})
        after['hooks']['Stop'][0]['hooks'][1]['timeout'] = 9
        self.hooks.write_text(json.dumps(after))
        with contextlib.redirect_stdout(io.StringIO()):
            adapter.uninstall(self.args)
        restored = json.loads(self.hooks.read_text())['hooks']['Stop'][0]['hooks']
        self.assertEqual(restored[1]['command'], self.original_command)
        self.assertEqual(restored[1]['timeout'], 9)
        self.assertEqual(restored[2]['command'], 'echo added-later')

    def test_repeat_install_refuses_without_rewriting(self):
        self.args.apply = True
        self.install()
        installed = self.hooks.read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.install()
        self.assertEqual(self.hooks.read_bytes(), installed)

    def test_custom_wrapper_is_not_silently_replaced(self):
        self.document['hooks']['Stop'][0]['hooks'][1]['command'] = 'python3 existing-adapter.py'
        self.hooks.write_text(json.dumps(self.document))
        with self.assertRaisesRegex(ValueError, 'No exact official'):
            self.install()
        self.assertFalse(self.root.exists())

    def test_inline_hooks_require_review(self):
        (self.home / 'config.toml').write_text('[[hooks.Stop]]\nmatcher = "*"\n')
        with self.assertRaisesRegex(ValueError, 'Inline hook'):
            self.install()

    def test_trust_records_are_preserved_and_not_rewritten(self):
        config = '[hooks.state.example]\ntrusted_hash = "example-existing-hash"\n'
        (self.home / 'config.toml').write_text(config)
        self.args.apply = True
        self.install()
        self.assertEqual((self.home / 'config.toml').read_text(), config)

    def test_modified_managed_command_causes_safe_uninstall_failure(self):
        self.args.apply = True
        self.install()
        current = json.loads(self.hooks.read_text())
        current['hooks']['Stop'][0]['hooks'][1]['command'] = 'python3 my-new-wrapper.py'
        self.hooks.write_text(json.dumps(current))
        saved = self.hooks.read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed or removed'):
            adapter.uninstall(self.args)
        self.assertEqual(self.hooks.read_bytes(), saved)


if __name__ == '__main__':
    unittest.main()

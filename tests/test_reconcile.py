import copy
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/redock_reconcile.py'
spec = importlib.util.spec_from_file_location('reconcile', SCRIPT)
reconcile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)
SID = '11111111-1111-4111-8111-111111111111'


def record():
    return {'agent': 'codex', 'session_id': SID, 'session_state': 'ended',
            'terminal': {'kind': 'herdr', 'session': 'default', 'pane_id': 'w1:p1'},
            'multiplexer_socket': '/tmp/herdr.sock', 'transcript_path': '/tmp/profile/sessions/old.jsonl',
            'cwd': '/tmp/project', 'turn_status': 'done', 'turn_id': 'original-turn',
            'turn_started_at': '2026-10-27T06:29:01Z', 'turn_status_at': '2026-10-27T06:30:06Z',
            'session_bound_at': '2026-10-27T06:29:01Z', 'last_seen_at': '2026-10-27T20:46:32Z',
            'future_field': {'preserve': True}}


class Registration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'sessions.json'
        self.old = record()
        self.document = {'schema': 1, 'sessions': [self.old], 'future_root_field': 42}
        self.path.write_text(json.dumps(self.document))

    def test_existing_live_conversation_becomes_visible_without_a_new_turn(self):
        restored = reconcile.restore_records(self.path, [copy.deepcopy(self.old)])
        self.assertEqual(restored, [SID])
        expected = copy.deepcopy(self.document)
        expected['sessions'][0]['session_state'] = 'active'
        self.assertEqual(json.loads(self.path.read_text()), expected)

    def test_a_second_pass_does_not_reset_timer_or_rewrite_the_file(self):
        reconcile.restore_records(self.path, [copy.deepcopy(self.old)])
        before = self.path.stat().st_mtime_ns
        self.assertEqual(reconcile.restore_records(self.path, [self.old]), [])
        self.assertEqual(self.path.stat().st_mtime_ns, before)
        self.assertEqual(json.loads(self.path.read_text())['sessions'][0]['session_state'], 'active')

    def test_native_prompt_update_between_scan_and_write_is_preserved(self):
        updated = copy.deepcopy(self.document)
        updated['sessions'][0].update(session_state='active', turn_status='working', turn_id='new-turn')
        self.path.write_text(json.dumps(updated))
        before = self.path.read_bytes()
        self.assertEqual(reconcile.restore_records(self.path, [self.old]), [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_native_lock_is_never_removed_when_owned_by_another_writer(self):
        lock = self.path.parent / '.registry.lock'
        lock.mkdir()
        before = self.path.read_bytes()
        with self.assertRaisesRegex(reconcile.RestoreError, 'registry_busy'):
            reconcile.restore_records(self.path, [self.old])
        self.assertTrue(lock.is_dir())
        self.assertEqual(self.path.read_bytes(), before)

    def test_future_schema_is_not_rewritten_and_own_lock_is_released(self):
        self.document['schema'] = 2
        self.path.write_text(json.dumps(self.document))
        before = self.path.read_bytes()
        with self.assertRaisesRegex(reconcile.RestoreError, 'unsupported_registry_schema'):
            reconcile.restore_records(self.path, [self.old])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.path.parent / '.registry.lock').exists())

    def test_ambiguous_duplicate_records_are_not_changed(self):
        self.document['sessions'].append(copy.deepcopy(self.old))
        self.path.write_text(json.dumps(self.document))
        self.assertEqual(reconcile.restore_records(self.path, [self.old]), [])

    def test_file_permissions_and_unknown_fields_are_preserved(self):
        reconcile.restore_records(self.path, [self.old])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(self.path.read_text())['sessions'][0]['future_field'], {'preserve': True})

    def test_registry_symlink_is_rejected(self):
        link = self.path.parent / 'link.json'
        link.symlink_to(self.path)
        with self.assertRaisesRegex(reconcile.RestoreError, 'registry_symlink'):
            reconcile.restore_records(link, [self.old])


class LiveVerification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        profile = self.root / 'profile with spaces'
        (profile / 'sessions').mkdir(parents=True)
        transcript = profile / 'sessions' / 'old.jsonl'
        transcript.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': SID}}) + '\n')
        binary = self.root / 'redock-hook'
        binary.write_bytes(b'verified-fixture')
        self.path = self.root / 'sessions.json'
        self.old = record()
        self.old['transcript_path'] = str(transcript)
        self.path.write_text(json.dumps({'schema': 1, 'sessions': [self.old]}))
        self.cfg = {'registry_path': str(self.path), 'codex_home': str(profile),
                    'herdr_socket': '/tmp/herdr.sock', 'herdr_session': 'default',
                    'redock_hook': str(binary), 'verified_redock_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
        self.pane = {'pane_id': 'w1:p1', 'workspace_id': 'w1', 'tab_id': 'w1:t1', 'terminal_id': 'term-one',
                     'agent': 'codex', 'terminal_title': SID[:26] + '... | codex | Old conversation'}
        self.panes = [self.pane]
        self.processes = [{'name': 'codex', 'pid': 123, 'argv': ['codex', '--yolo']}]
        self.threads = {SID: {'id': SID, 'status': {'type': 'idle'}, 'path': str(transcript),
                              'cwd': '/tmp/project', 'ephemeral': False}}

    def call(self, method, params):
        if method == 'pane.list':
            return {'panes': copy.deepcopy(self.panes)}
        if method == 'pane.process_info':
            return {'process_info': {'foreground_processes': copy.deepcopy(self.processes)}}
        self.fail('Unexpected mutating Herdr API: ' + method)

    def run_scan(self, get_threads=None):
        return reconcile.scan(self.cfg, apply=True, call=self.call,
                              get_threads=get_threads or (lambda ids: self.threads))

    def assert_skipped(self):
        before = self.path.read_bytes()
        self.assertEqual(self.run_scan()['restored'], [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_loaded_old_conversation_restores_without_prompt_or_notify(self):
        with patch.object(subprocess, 'run', side_effect=AssertionError('No commands or hooks needed')):
            self.assertEqual(self.run_scan()['restored'], [SID])

    def test_closed_agent_with_stale_terminal_title_is_not_revived(self):
        self.pane.pop('agent')
        self.assert_skipped()

    def test_shell_in_foreground_is_not_a_live_codex(self):
        self.processes = [{'name': 'zsh', 'pid': 123, 'argv': ['zsh']}]
        self.assert_skipped()

    def test_independent_and_remote_codex_are_not_assumed_to_use_this_daemon(self):
        for option in ['--no-daemon', '--remote=ws://other-host']:
            with self.subTest(option=option):
                self.processes[0]['argv'] = ['codex', option]
                self.assert_skipped()

    def test_multiple_panes_with_same_thread_are_ambiguous(self):
        self.panes.append({**self.pane, 'pane_id': 'w1:p2', 'terminal_id': 'term-two'})
        self.assert_skipped()

    def test_stale_herdr_report_does_not_override_new_native_title(self):
        self.pane['agent_session'] = {'value': SID}
        self.pane['terminal_title'] = '22222222-2222-4222-8222-22... | codex | Different'
        self.assert_skipped()

    def test_unloaded_thread_or_daemon_restart_is_not_invented(self):
        self.threads = {}
        self.assert_skipped()

    def test_status_and_transcript_identity_must_match(self):
        for change in [{'status': {'type': 'notLoaded'}}, {'id': 'other-id'}, {'cwd': '/tmp/another-project'},
                       {'path': str(self.root / 'missing.jsonl')}, {'ephemeral': True}]:
            with self.subTest(change=change):
                original = copy.deepcopy(self.threads[SID])
                self.threads[SID].update(change)
                self.assert_skipped()
                self.threads[SID] = original

    def test_changed_transcript_header_is_not_accepted(self):
        Path(self.old['transcript_path']).write_text('{"type":"session_meta","payload":{"id":"other"}}\n')
        self.assert_skipped()

    def test_changed_binary_requires_contract_revalidation(self):
        Path(self.cfg['redock_hook']).write_bytes(b'upgraded-binary')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(reconcile.RestoreError, 'redock_binary_changed'):
            self.run_scan()
        self.assertEqual(self.path.read_bytes(), before)

    def test_switch_or_exit_during_metadata_read_is_not_restored(self):
        def switch(ids):
            self.pane['terminal_id'] = 'replacement-terminal'
            return self.threads
        self.assertEqual(self.run_scan(switch)['restored'], [])

    def test_foreground_process_replaced_during_read_is_not_restored(self):
        def replace(ids):
            self.processes[0]['pid'] = 456
            return self.threads
        self.assertEqual(self.run_scan(replace)['restored'], [])

    def test_late_end_event_is_repaired_on_next_check_only_if_still_live(self):
        self.assertEqual(self.run_scan()['restored'], [SID])
        doc = json.loads(self.path.read_text())
        doc['sessions'][0].update(session_state='ended', last_seen_at='2026-10-28T04:46:34Z')
        self.path.write_text(json.dumps(doc))
        self.assertEqual(self.run_scan()['restored'], [SID])
        doc['sessions'][0]['session_state'] = 'ended'
        self.path.write_text(json.dumps(doc))
        self.processes = []
        self.assert_skipped()

    def test_missing_registration_and_other_terminal_namespace_are_not_created(self):
        for rows in [[], [{**self.old, 'terminal': {**self.old['terminal'], 'session': 'other'}}]]:
            self.path.write_text(json.dumps({'schema': 1, 'sessions': rows}))
            self.assert_skipped()

    def test_unavailable_daemon_replaces_previous_healthy_status_without_touching_registry(self):
        state = self.root / 'status'
        state.mkdir()
        (state / 'status.json').write_text('{"status":"ok","checked_at":"previous-run"}')
        config = self.root / 'settings.json'
        config.write_text(json.dumps({**self.cfg, 'state_dir': str(state)}))
        before = self.path.read_bytes()
        with patch('sys.argv', ['restore', '--settings', str(config), '--apply']), \
                patch.object(reconcile, 'scan', side_effect=reconcile.RestoreError('codex_transport_unavailable')):
            self.assertEqual(reconcile.main(), 0)
        actual = json.loads((state / 'status.json').read_text())
        self.assertEqual(actual['status'], 'skipped')
        self.assertEqual(actual['reason'], 'codex_transport_unavailable')
        self.assertNotEqual(actual['checked_at'], 'previous-run')
        self.assertEqual(self.path.read_bytes(), before)


class DaemonDisconnect(unittest.IsolatedAsyncioTestCase):
    async def test_restart_disconnect_is_reported_as_retriable_dependency_state(self):
        from websockets.asyncio.server import unix_serve

        # Keep the pathname below macOS's Unix-socket length limit.
        with tempfile.TemporaryDirectory(dir='/tmp', prefix='redock-ws-') as tmp:
            endpoint = Path(tmp) / 'app-server-control/app-server-control.sock'
            endpoint.parent.mkdir()

            async def restarting(ws):
                await ws.recv()
                await ws.close(code=1012, reason='Service restart')

            async with unix_serve(restarting, path=str(endpoint)):
                with self.assertRaisesRegex(reconcile.RestoreError, 'codex_transport_unavailable'):
                    await asyncio.to_thread(reconcile.live_threads, {'codex_home': tmp}, {SID})


@unittest.skipUnless(os.environ.get('REDOCK_TEST_BINARY'), 'Set REDOCK_TEST_BINARY for isolated native contract checks')
class NativeRegistryContract(unittest.TestCase):
    def test_native_writer_and_restore_share_the_directory_lock_without_losing_turns(self):
        with tempfile.TemporaryDirectory(prefix='redock-native-contract-') as tmp:
            root = Path(tmp)
            config = root / 'config.json'
            config.write_text('{}')
            transcript = root / 'sample.jsonl'
            transcript.write_text(json.dumps({'type': 'session_meta', 'payload': {'id': SID, 'cwd': tmp}}) + '\n')
            env = {k: v for k, v in os.environ.items() if not k.startswith(('HERDR_', 'REDOCK_', 'TMUX'))}
            env.update(XDG_STATE_HOME=str(root / 'state'), REDOCK_CONFIG=str(config),
                       REDOCK_RELAY_URL='http://127.0.0.1:1', HERDR_ENV='1', HERDR_SESSION='default',
                       HERDR_PANE_ID='w1:p1', HERDR_SOCKET_PATH=str(root / 'herdr.sock'))
            registry = root / 'state/redock-hook/chat/sessions.json'

            def emit(event):
                payload = {'hook_event_name': event, 'session_id': SID, 'cwd': tmp,
                           'transcript_path': str(transcript), 'source': 'resume'}
                subprocess.run([os.environ['REDOCK_TEST_BINARY'], 'agent-event', '--agent', 'codex',
                                '--stdin', '--chat-only'], input=json.dumps(payload), env=env,
                               text=True, capture_output=True, timeout=5, check=True)

            def wait_for(predicate):
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if registry.exists():
                        row = json.loads(registry.read_text())['sessions'][0]
                        if predicate(row):
                            return row
                    time.sleep(.01)
                self.fail('Native event did not reach expected state')

            emit('UserPromptSubmit')
            wait_for(lambda r: r.get('turn_status') == 'working')
            emit('Stop')
            wait_for(lambda r: r.get('turn_status') == 'done')
            emit('SessionEnd')
            old = wait_for(lambda r: r.get('session_state') == 'ended')
            self.assertEqual(reconcile.restore_records(registry, [old]), [SID])
            restored = json.loads(registry.read_text())['sessions'][0]
            self.assertEqual(restored, {**old, 'session_state': 'active'})
            lock = registry.parent / '.registry.lock'
            lock.mkdir()
            try:
                emit('UserPromptSubmit')
                time.sleep(.15)
                self.assertEqual(json.loads(registry.read_text())['sessions'][0], restored)
                with self.assertRaisesRegex(reconcile.RestoreError, 'registry_busy'):
                    reconcile.restore_records(registry, [old])
            finally:
                lock.rmdir()
            native = wait_for(lambda r: r.get('turn_status') == 'working')
            self.assertEqual(reconcile.restore_records(registry, [old]), [])
            self.assertEqual(json.loads(registry.read_text())['sessions'][0], native)
            self.assertFalse((root / 'state/redock-hook/queue').exists(), 'No notification queue should be created')

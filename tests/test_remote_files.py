import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/local-files'))
SPEC = importlib.util.spec_from_file_location('remote_files', ROOT / 'plugins/remote-files/remote_files.py')
remote = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remote)


class RemoteFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / '资料 空格(1).md'
        self.file.write_text('remote content')
        self.pane = dict(workspace_id='w1', tab_id='w1:t1', pane_id='w1:p1', terminal_id='term-original', cwd=str(self.root))
        self.request = dict(self.pane, session='default', boot_id='12345-6789', action='open', selections=[
            [dict(pane_id='w1:p1', content_revision=4, anchor=dict(row=0, col=0), cursor=dict(row=0, col=3)), '资料 '],
            [dict(pane_id='w1:p1', content_revision=4, anchor=dict(row=1, col=0), cursor=dict(row=1, col=8)), '空格(1).md']])
        self.reads = 0

    def rpc(self, method, params):
        if method == 'pane.get':
            return {'pane': dict(self.pane)}
        if method == 'pane.selection.read':
            return {'pane_id': params['pane_id'], 'text': self.request['selections'][params['anchor']['row']][1]}
        self.fail(method)

    def test_wrapped_relative_file_uses_remote_directory(self):
        self.assertEqual(remote.verified_target(self.request, self.rpc), self.file)

    def test_wrong_terminal_same_pane_id_is_rejected(self):
        self.request['terminal_id'] = 'term-from-previous-server'
        with self.assertRaisesRegex(ValueError, '终端已变化'):
            remote.verified_target(self.request, self.rpc)

    @unittest.skipUnless(sys.platform == 'darwin' or sys.platform.startswith('linux'), 'Unix peer credentials')
    def test_rpc_checks_actual_server_process_before_reading_pane(self):
        endpoint = self.root/'.config/herdr/herdr.sock'
        endpoint.parent.mkdir(parents=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(endpoint))
        server.listen(2)
        self.addCleanup(server.close)
        def respond():
            for _ in range(2):
                connection, _ = server.accept()
                with connection:
                    if connection.recv(8192):
                        connection.sendall(b'{"result":{"verified":true}}\n')
        thread = threading.Thread(target=respond, daemon=True)
        thread.start()
        with patch.object(remote.Path, 'home', return_value=self.root):
            stamp = str(time.time_ns())
            rpc = remote.rpc_client('default', str(os.getpid())+'-'+stamp)
            self.assertTrue(rpc('pane.get', {})['verified'])
            with self.assertRaisesRegex(ValueError, '后台已变化'):
                remote.rpc_client('default', str(os.getpid()+1)+'-'+stamp)('pane.get', {})
            with self.assertRaisesRegex(ValueError, '后台已变化'):
                remote.rpc_client('default', str(os.getpid())+'-0')
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_changed_text_and_missing_content_revision_are_rejected(self):
        for failure in ('changed', 'version', 'pane'):
            request = json.loads(json.dumps(self.request))
            if failure == 'version':
                request['selections'][0][0]['content_revision'] = None
            if failure == 'pane':
                request['selections'][0][0]['pane_id'] = 'other-pane'
            def rpc(method, params):
                result = self.rpc(method, params)
                if method == 'pane.selection.read' and failure == 'changed':
                    result['text'] = 'other.md'
                return result
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                remote.verified_target(request, rpc)

    def test_project_change_during_resolution_is_rejected(self):
        def rpc(method, params):
            result = self.rpc(method, params)
            if method == 'pane.get':
                self.reads += 1
                if self.reads > 2:
                    result['pane']['cwd'] = '/different-project'
            return result
        with self.assertRaisesRegex(ValueError, '目录已变化'):
            remote.verified_target(self.request, rpc)

    def test_same_path_on_two_machines_gets_distinct_cache(self):
        targets = []
        for profile, data in [('a'*32, b'mini'), ('b'*32, b'spark')]:
            header = dict(path='/project/README.md', size=len(data), sha256=hashlib.sha256(data).hexdigest())
            targets.append(remote.save_copy(header, data, profile, profile, self.root/'cache'))
        self.assertNotEqual(*targets)
        self.assertEqual([p.read_bytes() for p in targets], [b'mini', b'spark'])
        for target in targets:
            source = json.loads((target.parent.parent/'source.json').read_text())
            self.assertIn('不会自动回写', source['copy_notice'])

    def test_incomplete_or_corrupt_transfer_does_not_replace_cached_file(self):
        data = b'original'
        header = dict(path='/project/README.md', size=len(data), sha256=hashlib.sha256(data).hexdigest())
        saved = remote.save_copy(header, data, 'a'*32, 'Remote', self.root/'cache')
        for corrupt in (data[:-1], b'changed!'):
            with self.assertRaises(ValueError):
                remote.save_copy(header, corrupt, 'a'*32, 'Remote', self.root/'cache')
            self.assertEqual(saved.read_bytes(), data)

    def test_serve_returns_verified_hash_and_bytes(self):
        output = io.BytesIO()
        with patch.object(remote, 'rpc_client', return_value=self.rpc):
            remote.serve(self.request, output)
        header, data = output.getvalue().split(b'\n', 1)
        self.assertEqual(data, self.file.read_bytes())
        self.assertEqual(json.loads(header)['sha256'], hashlib.sha256(data).hexdigest())

    def test_metadata_filename_cannot_overwrite_file_contents(self):
        data = b'actual file'
        header = dict(path='/project/source.json', size=len(data), sha256=hashlib.sha256(data).hexdigest())
        saved = remote.save_copy(header, data, 'a'*32, 'Remote', self.root/'cache')
        self.assertEqual(saved.read_bytes(), data)
        self.assertNotEqual(saved, saved.parent.parent/'source.json')

    def test_download_preserves_local_edits_and_remote_versions(self):
        def download(data):
            header = dict(path='/project/README.md', size=len(data), sha256=hashlib.sha256(data).hexdigest())
            return remote.save_copy(header, data, 'a'*32, 'Remote', self.root/'cache')
        original = download(b'remote-v1')
        self.assertEqual(download(b'remote-v1'), original)
        original.write_bytes(b'local-edit')
        refreshed = download(b'remote-v1')
        self.assertNotEqual(original, refreshed)
        self.assertEqual(original.read_bytes(), b'local-edit')
        self.assertEqual(refreshed.read_bytes(), b'remote-v1')
        updated = download(b'remote-v2')
        self.assertNotEqual(updated, refreshed)
        self.assertEqual(updated.read_bytes(), b'remote-v2')

    def test_terminal_and_command_files_require_explicit_finder_handling(self):
        with patch.object(remote.file_actions, 'open_target') as opened:
            for name in ('setup.command', 'run.terminal', 'installer.pkg', 'script.scpt'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    remote.open_copy(Path(name), 'open')
            opened.assert_not_called()
            remote.open_copy(Path('run.terminal'), 'reveal')
            opened.assert_called_once_with(Path('run.terminal'), 'reveal')

    def test_serve_rejects_directory_and_oversized_file(self):
        for target in (self.root, self.root/'large.bin'):
            if target.name == 'large.bin':
                with target.open('wb') as stream:
                    stream.truncate(remote.MAX_FILE+1)
            with patch.object(remote, 'rpc_client'), patch.object(remote, 'verified_target', return_value=target):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    remote.serve(self.request, io.BytesIO())

    def test_ssh_sends_file_request_as_data_not_shell_text(self):
        self.request['selections'][0][1] = '$(touch BAD); "quoted".md'
        class FakeProcess:
            returncode = 0
            def communicate(inner, payload, timeout):
                self.assertEqual(json.loads(payload)['selections'][0][1], self.request['selections'][0][1])
                raise subprocess.TimeoutExpired('ssh', timeout)
            def kill(inner):
                pass
            def wait(inner, timeout):
                return 0
        import subprocess
        with patch.object(remote.subprocess, 'Popen', return_value=FakeProcess()) as popen:
            with self.assertRaisesRegex(ValueError, '30 秒'):
                remote.fetch(self.request, 'a'*32, 'host-alias', 'default', 'Remote', self.root/'cache')
        command = popen.call_args.args[0]
        self.assertEqual(command[-1], remote.REMOTE_COMMAND)
        self.assertNotIn(self.request['selections'][0][1], command[-1])
        self.assertFalse((self.root/'cache').exists())


if __name__ == '__main__':
    unittest.main()

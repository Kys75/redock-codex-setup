import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "plugins/local-files/file_actions.py"
SPEC = importlib.util.spec_from_file_location("file_actions", SOURCE)
actions = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(actions)
THREAD = "01234567-89ab-4def-8123-456789abcdef"


class FileActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.file = self.root / "资料" / "使用 说明.md"
        self.file.parent.mkdir()
        self.file.write_text("test")

    def test_chinese_spaces_relative_and_markdown_line_suffixes(self):
        for text in ("资料/使用 说明.md", "./资料/使用 说明.md:12:3", "[说明](<资料/使用 说明.md#L12>)", "`资料/使用 说明.md`", str(self.file), self.file.as_uri()):
            with self.subTest(text=text):
                self.assertEqual(actions.resolve_reference(text, self.root), self.file)

    def test_parent_relative_directory_and_literal_colon(self):
        literal = self.root / "notes:12"
        literal.touch()
        self.assertEqual(actions.resolve_reference("../notes:12", self.file.parent), literal)
        self.assertEqual(actions.resolve_reference("资料", self.root), self.file.parent)

    def test_missing_file_multiline_and_remote_urls_fail(self):
        for text in ("missing.md", "one.md\ntwo.md", "", "https://example.com/file.md", "file://another-host/tmp/a", "file:///tmp/a%00b"):
            with self.subTest(text=text), self.assertRaises(actions.ActionError):
                actions.resolve_reference(text, self.root)

    def test_relative_path_requires_known_absolute_base(self):
        for base in (None, "relative"):
            with self.subTest(base=base), self.assertRaises(actions.ActionError):
                actions.resolve_reference("资料/使用 说明.md", base)

    def test_shell_metacharacters_are_passed_as_one_filename(self):
        path = self.root / '$(touch BAD); "quoted".md'
        path.touch()
        with patch.object(actions.subprocess, "run") as run:
            actions.open_target(actions.resolve_reference(path.name, self.root), "reveal")
        self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "-R", "--", str(path)])
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertFalse((self.root / "BAD").exists())

    def test_open_uses_default_app_reveal_uses_finder(self):
        with patch.object(actions.subprocess, "run") as run:
            actions.open_target(self.file, "open")
        self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "--", str(self.file)])

    def test_titles_allow_attention_prefix_but_reject_unknown_identity(self):
        for title in (f"{THREAD} | codex | title", f"[ ! ] Action Required | {THREAD[:29]}... | codex | title"):
            self.assertTrue(THREAD.startswith(actions.session_prefix(title)))
        for title in ("codex | title", "other-app", "x" * 29 + " | codex"):
            with self.subTest(title=title), self.assertRaises(actions.ActionError):
                actions.session_prefix(title)

    def pane(self):
        return {"pane_id": "w1:p1", "terminal_id": "t1", "agent": "codex", "cwd": str(self.root), "terminal_title": f"{THREAD[:29]}... | codex | title"}

    def rpc(self, method, params):
        if method == "pane.get":
            return {"pane": self.pane()}
        if method == "pane.process_info":
            return {"process_info": {"foreground_processes": [{"name": "codex", "pid": 10, "argv": ["codex", "resume", THREAD]}]}}
        self.fail(method)

    def test_live_codex_directory_wins_over_same_named_shell_file(self):
        other = self.root / "other-project"
        other.mkdir()
        (self.root / "README.md").write_text("wrong")
        (other / "README.md").write_text("correct")
        target = actions.target_for_context({"focused_pane_id": "w1:p1"}, "README.md", self.rpc, lambda prefix: str(other))
        self.assertEqual(target, other / "README.md")
        self.assertEqual(target.read_text(), "correct")

    def test_unknown_codex_directory_does_not_fall_back_to_shell(self):
        (self.root / "README.md").touch()
        def unavailable(prefix):
            raise actions.ActionError("unknown")
        with self.assertRaises(actions.ActionError):
            actions.target_for_context({"focused_pane_id": "w1:p1"}, "README.md", self.rpc, unavailable)

    def test_switching_thread_during_resolution_aborts(self):
        calls = []
        def rpc(method, params):
            result = self.rpc(method, params)
            if method == "pane.get":
                calls.append(method)
                if len(calls) > 1:
                    result["pane"]["terminal_title"] = "11234567-89ab-4def-8123-456789abcdef | codex"
            return result
        with self.assertRaises(actions.ActionError):
            actions.target_for_context({"focused_pane_id": "w1:p1"}, "资料/使用 说明.md", rpc, lambda _: str(self.root))

    def test_absolute_path_does_not_need_shared_codex_backend(self):
        def unavailable(prefix):
            self.fail("absolute paths must not need Codex RPC")
        self.assertEqual(actions.target_for_context({"focused_pane_id": "w1:p1"}, str(self.file), self.rpc, unavailable), self.file)

    def test_missing_pane_and_remote_codex_are_not_guessed(self):
        with self.assertRaises(actions.ActionError):
            actions.target_for_context({}, str(self.file), self.rpc)
        def remote(method, params):
            result = self.rpc(method, params)
            if method == "pane.process_info":
                result["process_info"]["foreground_processes"][0]["argv"].append("--remote=ws://example.invalid")
            return result
        with self.assertRaises(actions.ActionError):
            actions.target_for_context({"focused_pane_id": "w1:p1"}, "资料/使用 说明.md", remote)


if __name__ == "__main__":
    unittest.main()

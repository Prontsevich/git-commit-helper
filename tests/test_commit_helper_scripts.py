from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


class ScriptTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_dir.name)
        self.git("init", "-q")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "commit.gpgsign", "false")
        self.write_file("README.md", "base\n")
        self.git("add", "README.md")
        self.git("commit", "-m", "chore: init")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )

    def write_file(self, relative_path: str, content: str) -> None:
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def run_script(self, script_name: str, *args: str) -> tuple[int, dict[str, object]]:
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / script_name), *args],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        payload = json.loads(result.stdout)
        return result.returncode, payload

    def test_check_conflicts_reads_staged_snapshot(self) -> None:
        self.write_file("app.txt", "clean\n")
        self.git("add", "app.txt")
        self.git("commit", "-m", "chore: add app file")

        staged_conflict = (
            "<<<<<<< HEAD\n"
            "left side\n"
            "=======\n"
            "right side\n"
            ">>>>>>> main\n"
        )
        self.write_file("app.txt", staged_conflict)
        self.git("add", "app.txt")
        self.write_file("app.txt", "resolved in worktree\n")

        code, payload = self.run_script("check_conflicts.py")
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "conflicts")
        self.assertEqual(payload["source"], "index")
        self.assertEqual(len(payload["conflicts"]), 1)
        self.assertEqual(payload["conflicts"][0]["file"], "app.txt")

    def test_check_conflicts_ignores_separator_without_block(self) -> None:
        self.write_file("notes.md", "line 1\n")
        self.git("add", "notes.md")
        self.git("commit", "-m", "docs: add notes file")

        self.write_file("notes.md", "line 1\n=======\nline 2\n")

        code, payload = self.run_script("check_conflicts.py")
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "ok")

    def test_sensitive_files_skip_untracked_by_default(self) -> None:
        self.write_file(".env", "API_KEY=demo\n")

        code_default, payload_default = self.run_script("check_sensitive_files.py")
        self.assertEqual(code_default, 0)
        self.assertEqual(payload_default["status"], "ok")
        self.assertEqual(payload_default["checked_files"], 0)

        code_untracked, payload_untracked = self.run_script(
            "check_sensitive_files.py", "--include-untracked"
        )
        self.assertEqual(code_untracked, 2)
        self.assertEqual(payload_untracked["status"], "sensitive_files_detected")
        self.assertEqual(payload_untracked["flagged_files"][0]["file"], ".env")

    def test_regex_scan_detects_unstaged_tracked_changes(self) -> None:
        self.write_file("config.py", "token = 'placeholder'\n")
        self.git("add", "config.py")
        self.git("commit", "-m", "chore: add config module")

        self.write_file("config.py", 'token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"\n')

        code, payload = self.run_script("check_sensitive_regex_staged.py")
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "secrets_detected")
        self.assertEqual(payload["source"], "worktree")
        self.assertEqual(payload["findings"][0]["file"], "config.py")

    def test_regex_scan_can_include_untracked_files(self) -> None:
        self.write_file("secrets.txt", 'password = "supersecretvalue123"\n')

        code_default, payload_default = self.run_script("check_sensitive_regex_staged.py")
        self.assertEqual(code_default, 0)
        self.assertEqual(payload_default["status"], "no_changes")

        code_untracked, payload_untracked = self.run_script(
            "check_sensitive_regex_staged.py", "--include-untracked"
        )
        self.assertEqual(code_untracked, 2)
        self.assertEqual(payload_untracked["status"], "secrets_detected")
        self.assertEqual(payload_untracked["findings"][0]["file"], "secrets.txt")

    def test_validate_commit_message_script(self) -> None:
        valid_message = "feat(parser): add scope support\n\nHandle tracked file selection.\n"
        valid_code, valid_payload = self.run_script(
            "validate_commit_message.py", "--message", valid_message
        )
        self.assertEqual(valid_code, 0)
        self.assertEqual(valid_payload["status"], "ok")

        invalid_message = "feat: added validator.\nBody without required blank line\n"
        invalid_code, invalid_payload = self.run_script(
            "validate_commit_message.py", "--message", invalid_message
        )
        self.assertEqual(invalid_code, 2)
        self.assertEqual(invalid_payload["status"], "invalid")
        self.assertTrue(invalid_payload["errors"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"


class GitRepoTestCase(unittest.TestCase):
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

    def run_script(
        self, script_name: str, *args: str, env: dict[str, str] | None = None
    ) -> tuple[int, dict[str, object]]:
        merged_env = {**os.environ, **(env or {})}
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / script_name), *args],
            cwd=self.repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=merged_env,
        )
        payload = json.loads(result.stdout)
        return result.returncode, payload

    def validate(self, message: str, *args: str, env: dict[str, str] | None = None):
        return self.run_script(
            "validate_commit_message.py", "--message", message, *args, env=env
        )


class ScriptTestCase(GitRepoTestCase):
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



class ValidateCommitMessageTestCase(GitRepoTestCase):
    TRAILER = "Co-Authored-By: Some Model <noreply@example.com>"

    def test_header_tiers(self) -> None:
        soft = "feat: " + "x" * 70  # 76 chars: over 72, under 100
        code, payload = self.validate(soft + "\n\n" + self.TRAILER + "\n")
        self.assertEqual(code, 0)
        self.assertTrue(any("preferred 72" in w for w in payload["warnings"]))

        hard = "feat: " + "x" * 100
        code, payload = self.validate(hard + "\n\n" + self.TRAILER + "\n")
        self.assertEqual(code, 2)
        self.assertTrue(any("hard limit of 100" in e for e in payload["errors"]))

    def test_trailers_and_urls_exempt_from_wrap(self) -> None:
        long_trailer = "Co-Authored-By: " + "A" * 120 + " <noreply@example.com>"
        url_line = "See https://example.com/" + "p" * 120
        msg = "fix(core): handle wrap\n\n" + url_line + "\n\n" + long_trailer + "\n"
        code, payload = self.validate(msg)
        self.assertEqual(code, 0)
        self.assertEqual(payload["errors"], [])

    def test_merge_type_accepted(self) -> None:
        code, payload = self.validate("merge: branch 'feature' into main\n\n" + self.TRAILER + "\n")
        self.assertEqual(code, 0)
        self.assertEqual(payload["parsed"]["type"], "merge")

    def test_coauthor_nudge_uses_env_default(self) -> None:
        code, payload = self.validate(
            "feat: add thing\n",
            env={"GIT_COMMIT_HELPER_COAUTHOR": "Co-Authored-By: Env Model <e@example.com>"},
        )
        self.assertEqual(code, 0)
        self.assertTrue(any("Env Model" in w for w in payload["warnings"]))

    def test_coauthor_check_can_be_disabled(self) -> None:
        code, payload = self.validate("feat: add thing\n", "--no-coauthor-check")
        self.assertEqual(code, 0)
        self.assertFalse(any("Co-Authored-By" in w for w in payload["warnings"]))

    def test_body_shape_warnings(self) -> None:
        long_body = (
            "feat(api): add endpoint\n\n"
            "Line one why.\n"
            "Line two what.\n"
            "Line three extra.\n\n"
            + self.TRAILER + "\n"
        )
        code, payload = self.validate(long_body)
        self.assertEqual(code, 0)
        self.assertTrue(any("two lines" in w for w in payload["warnings"]))

        leaky_body = (
            "fix(auth): refresh token early\n\n"
            "Token expired before refresh.\n"
            "Update src/auth/session.ts and call refreshToken().\n\n"
            + self.TRAILER + "\n"
        )
        code, payload = self.validate(leaky_body)
        self.assertEqual(code, 0)
        self.assertTrue(any("file paths" in w or "function names" in w for w in payload["warnings"]))

        clean = "fix(auth): refresh token early\n\nToken expired before refresh.\nRefresh one minute earlier.\n\n" + self.TRAILER + "\n"
        code, payload = self.validate(clean)
        self.assertEqual(code, 0)
        self.assertEqual(payload["warnings"], [])

    def test_commitlint_config_without_tool_falls_back(self) -> None:
        self.write_file("commitlint.config.js", "module.exports = {extends: []};\n")
        code, payload = self.validate(
            "feat: add thing\n\n" + self.TRAILER + "\n",
            env={"PATH": os.path.dirname(sys.executable)},
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["mode"], "builtin")
        self.assertTrue(any("commitlint" in w for w in payload["warnings"]))

    def test_no_commitlint_flag_skips_detection(self) -> None:
        self.write_file("commitlint.config.js", "module.exports = {extends: []};\n")
        code, payload = self.validate(
            "feat: add thing\n\n" + self.TRAILER + "\n", "--no-commitlint"
        )
        self.assertEqual(code, 0)
        self.assertEqual(payload["mode"], "builtin")
        self.assertEqual(payload["warnings"], [])



class SecretsAndSensitiveFilesTestCase(GitRepoTestCase):
    def test_env_example_is_not_flagged(self) -> None:
        self.write_file(".env.example", "API_KEY=\n")
        self.write_file(".envrc", "export FOO=bar\n")
        code, payload = self.run_script("check_sensitive_files.py", "--include-untracked")
        self.assertEqual(code, 2)
        flagged = [f["file"] for f in payload["flagged_files"]]
        self.assertNotIn(".env.example", flagged)
        self.assertIn(".envrc", flagged)

    def test_new_patterns_detected(self) -> None:
        samples = {
            "a.txt": "key = sk-ant-" + "a" * 40 + "\n",
            "b.txt": "postgres://user:hunter22@db.example.com/app\n",
            "c.txt": "eyJ" + "a" * 20 + ".eyJ" + "b" * 20 + "." + "c" * 20 + "\n",
            "d.txt": "STRIPE=sk_live_" + "Z" * 30 + "\n",
        }
        for name, content in samples.items():
            self.write_file(name, content)
        code, payload = self.run_script("check_secrets.py", "--include-untracked")
        self.assertEqual(code, 2)
        patterns = {f["pattern"] for f in payload["findings"]}
        self.assertTrue({"anthropic_key", "url_with_password", "jwt", "stripe_key"} <= patterns, patterns)

    def test_allowlist_suppresses_known_fixtures(self) -> None:
        self.write_file("fixture.py", 'token = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"\n')
        code, payload = self.run_script("check_secrets.py", "--include-untracked")
        self.assertEqual(code, 2)

        self.write_file(".git-commit-helper-allow", "# fixtures\nghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456\n")
        code, payload = self.run_script("check_secrets.py", "--include-untracked", "fixture.py")
        self.assertEqual(code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["suppressed_by_allowlist"], 2)

        code, payload = self.run_script(
            "check_secrets.py", "--include-untracked", "--no-allowlist", "fixture.py"
        )
        self.assertEqual(code, 2)

    def test_path_allowlist_suppresses_file_name_match(self) -> None:
        self.write_file("tools/check_secrets.py", "print('scanner')\n")
        code, payload = self.run_script("check_sensitive_files.py", "--include-untracked")
        self.assertEqual(code, 2)

        self.write_file(".git-commit-helper-allow", "path:tools/check_secrets.py\n")
        code, payload = self.run_script("check_sensitive_files.py", "--include-untracked")
        self.assertEqual(code, 0)
        self.assertEqual(payload["suppressed_by_allowlist"], 1)

        code, payload = self.run_script(
            "check_sensitive_files.py", "--include-untracked", "--no-allowlist"
        )
        self.assertEqual(code, 2)

    def test_legacy_alias_still_works(self) -> None:
        self.write_file("cfg.py", 'password = "supersecretvalue123"\n')
        code, payload = self.run_script(
            "check_sensitive_regex_staged.py", "--include-untracked"
        )
        self.assertEqual(code, 2)
        self.assertEqual(payload["status"], "secrets_detected")


class ProposeSplitTestCase(GitRepoTestCase):
    def test_groups_by_domain_and_kind(self) -> None:
        files = [
            "src/core/http.ts",
            "src/orders/store.ts",
            "src/orders/page.tsx",
            "src/orders/__tests__/store.test.ts",
            "src/users/store.ts",
            "docs/orders.md",
            ".github/workflows/ci.yml",
            "package-lock.json",
        ]
        for path in files:
            self.write_file(path, "x\n")
        code, payload = self.run_script("propose_split.py", "--include-untracked")
        self.assertEqual(code, 0)
        self.assertTrue(payload["multi_commit_recommended"])
        groups = payload["review_friendly"]
        kinds = [g["kind"] for g in groups]
        self.assertEqual(kinds[0], "infra")
        self.assertEqual(kinds[-1], "generated")
        by_domain = {g["domain"]: g for g in groups}
        self.assertEqual(
            sorted(by_domain["orders"]["files"]),
            ["src/orders/__tests__/store.test.ts", "src/orders/page.tsx", "src/orders/store.ts"],
        )
        self.assertEqual(by_domain["orders"]["header_stub"], "feat(orders): ")
        self.assertEqual(by_domain["ci"]["suggested_type"], "ci")
        self.assertEqual(len(payload["minimal"]), 2)

    def test_single_group_not_recommended(self) -> None:
        self.write_file("src/orders/store.ts", "x\n")
        code, payload = self.run_script("propose_split.py", "--include-untracked")
        self.assertEqual(code, 0)
        self.assertFalse(payload["multi_commit_recommended"])

    def test_text_format(self) -> None:
        self.write_file("src/orders/store.ts", "x\n")
        result = subprocess.run(
            ["python3", str(SCRIPTS_DIR / "propose_split.py"), "--include-untracked", "--format", "text"],
            cwd=self.repo, stdout=subprocess.PIPE, text=True, check=True,
        )
        self.assertIn("feat(orders): <summary>", result.stdout)


if __name__ == "__main__":
    unittest.main()

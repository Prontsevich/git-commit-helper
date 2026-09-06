#!/usr/bin/env python3
"""Scan added lines in the selected commit scope for likely secrets.

Only added lines are inspected: the staged diff for --source index, the
working-tree diff for --source worktree, and whole files for untracked paths
included with --include-untracked.

Known false positives (test fixtures, documentation samples) can be silenced
with `.git-commit-helper-allow` at the repo root: one regular expression per
line matched against the finding's excerpt, or `path:<glob>` to skip a file
entirely; `#` comments allowed. Suppressed findings are counted in the output
so they never disappear silently.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gitscope  # noqa: E402


@dataclass(frozen=True)
class PatternSpec:
    name: str
    regex: re.Pattern[str]


PATTERNS = [
    PatternSpec("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    PatternSpec(
        "private_key_block",
        re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----"),
    ),
    PatternSpec("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    PatternSpec("github_fine_grained_token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b")),
    PatternSpec("gitlab_token", re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    PatternSpec("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    PatternSpec(
        "slack_webhook",
        re.compile(r"hooks\.slack\.com/services/T[A-Za-z0-9]+/B[A-Za-z0-9]+/[A-Za-z0-9]+"),
    ),
    PatternSpec("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    PatternSpec("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b")),
    PatternSpec("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{32,}\b")),
    PatternSpec("stripe_key", re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{24,}\b")),
    PatternSpec("sendgrid_key", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b")),
    PatternSpec("npm_token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    PatternSpec("huggingface_token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b")),
    PatternSpec("telegram_bot_token", re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b")),
    PatternSpec(
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    ),
    PatternSpec(
        "azure_account_key",
        re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}"),
    ),
    PatternSpec(
        "url_with_password",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:[^\s@/]{3,}@[^\s/]+"),
    ),
    PatternSpec(
        "generic_secret_assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|password|passwd|client[_-]?secret)\b"
            r".{0,20}[:=]\s*['\"][^'\"]{12,}['\"]"
        ),
    ),
]

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def run_git_diff(files: list[str], source: str, timeout_seconds: float) -> str:
    if not files:
        return ""

    cmd = ["git", "diff"]
    if source == "index":
        cmd.append("--cached")
    cmd.extend(["--unified=0", "--no-color", "--diff-filter=ACMR", "--", *files])

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"{' '.join(cmd)} failed")
    return result.stdout


def match_line(file: str, lineno: int, text: str) -> list[dict[str, object]]:
    return [
        {"file": file, "line": lineno, "pattern": spec.name, "excerpt": text[:160]}
        for spec in PATTERNS
        if spec.regex.search(text)
    ]


def scan_diff(diff_text: str) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    current_file = ""
    current_new_line = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if line.startswith("@@"):
            match = HUNK_RE.match(line)
            if match:
                current_new_line = int(match.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            findings.extend(match_line(current_file, current_new_line, line[1:]))
            current_new_line += 1
            continue
        if line.startswith(" "):
            current_new_line += 1

    return findings


def scan_whole_file(path: str) -> list[dict[str, object]]:
    payload = gitscope.load_bytes(path, "worktree")
    if payload is None or gitscope.is_binary(payload):
        return []
    text = payload.decode("utf-8", errors="ignore")
    findings: list[dict[str, object]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        findings.extend(match_line(path, lineno, line))
    return findings


def apply_allowlist(
    findings: list[dict[str, object]], allow: gitscope.Allowlist
) -> tuple[list[dict[str, object]], int]:
    kept: list[dict[str, object]] = []
    suppressed = 0
    for finding in findings:
        if allow.allows_path(str(finding.get("file", ""))) or allow.allows_excerpt(
            str(finding.get("excerpt", ""))
        ):
            suppressed += 1
        else:
            kept.append(finding)
    return kept, suppressed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="optional explicit file paths")
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="include untracked files when source resolves to worktree",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "index", "worktree"),
        default="auto",
        help="resolve selected file scope from git index or working tree",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="timeout in seconds for diff collection",
    )
    parser.add_argument(
        "--no-allowlist",
        action="store_true",
        help=f"ignore {gitscope.ALLOWLIST_FILE} even if present",
    )
    args = parser.parse_args()

    try:
        gitscope.ensure_git_repo()
        source, tracked_files, untracked_files = gitscope.resolve_scope(
            args.files, args.source, args.include_untracked
        )
        diff_text = run_git_diff(tracked_files, source, args.timeout)

        findings = scan_diff(diff_text)
        for file_path in untracked_files:
            findings.extend(scan_whole_file(file_path))

        allow = gitscope.Allowlist.empty() if args.no_allowlist else gitscope.Allowlist.load()
        findings, suppressed = apply_allowlist(findings, allow)

        selected_count = len(tracked_files) + len(untracked_files)
        if selected_count == 0:
            status = "no_changes"
        else:
            status = "secrets_detected" if findings else "ok"

        print(
            json.dumps(
                {
                    "status": status,
                    "source": source,
                    "timeout_seconds": args.timeout,
                    "selected_file_count": selected_count,
                    "tracked_files_scanned": tracked_files,
                    "untracked_files_scanned": untracked_files,
                    "suppressed_by_allowlist": suppressed,
                    "findings": findings,
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return 2 if findings else 0
    except subprocess.TimeoutExpired:
        print(
            json.dumps(
                {"status": "timeout", "timeout_seconds": args.timeout, "findings": []},
                ensure_ascii=True,
                indent=2,
            )
        )
        return 3
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

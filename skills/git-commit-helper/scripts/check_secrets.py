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
import time
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
C_ESCAPES = {"a": 7, "b": 8, "t": 9, "n": 10, "v": 11, "f": 12, "r": 13, '"': 34, "\\": 92}
# Lines between deadline checks: keeps the clock cheap on large files.
DEADLINE_STRIDE = 1000


class ScanTimeout(Exception):
    pass


class Deadline:
    """One time budget for diff collection and the regex pass together."""

    def __init__(self, seconds: float):
        self.end = time.monotonic() + seconds

    def remaining(self) -> float:
        left = self.end - time.monotonic()
        if left <= 0:
            raise ScanTimeout()
        return left

    def check(self, counter: int) -> None:
        if counter % DEADLINE_STRIDE == 0:
            self.remaining()


def unquote_c(text: str) -> str:
    """Decode a path git printed in C-style quotes."""
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            if nxt in "01234567":
                out.append(int(text[i + 1 : i + 4], 8))
                i += 4
                continue
            out.append(C_ESCAPES.get(nxt, ord(nxt)))
            i += 2
            continue
        out.extend(ch.encode("utf-8", errors="surrogateescape"))
        i += 1
    return out.decode("utf-8", errors="surrogateescape")


def diff_new_path(header: str) -> str:
    """Path from a `+++ b/<path>` line.

    git appends a tab after names that contain spaces and C-quotes names with
    quotes, backslashes or control characters even with core.quotePath off.
    """
    raw = header[4:].rstrip("\t")
    if raw.startswith('"') and raw.endswith('"'):
        raw = unquote_c(raw[1:-1])
    return raw[2:] if raw.startswith("b/") else raw


def run_git_diff(files: list[str], source: str, deadline: Deadline) -> str:
    if not files:
        return ""

    cmd = ["git", "-c", "core.quotePath=false", "diff"]
    if source == "index":
        cmd.append("--cached")
    cmd.extend(["--unified=0", "--no-color", "--diff-filter=ACMR", "--", *files])

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="surrogateescape",
        check=False,
        timeout=deadline.remaining(),
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


def scan_diff(diff_text: str, deadline: Deadline) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    current_file = ""
    current_new_line = 0

    for counter, line in enumerate(diff_text.splitlines()):
        deadline.check(counter)
        if line.startswith("+++ "):
            current_file = diff_new_path(line)
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


def scan_whole_file(path: str, deadline: Deadline) -> list[dict[str, object]]:
    deadline.remaining()
    payload = gitscope.load_bytes(path, "worktree")
    if payload is None or gitscope.is_binary(payload):
        return []
    text = payload.decode("utf-8", errors="ignore")
    findings: list[dict[str, object]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        deadline.check(lineno)
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


def scan(
    source: str,
    tracked_files: list[str],
    untracked_files: list[str],
    allow: gitscope.Allowlist,
    timeout: float,
) -> dict[str, object]:
    """Scan the scope; a timeout is reported as a status, not raised."""
    selected_count = len(tracked_files) + len(untracked_files)
    deadline = Deadline(timeout)
    try:
        findings = scan_diff(run_git_diff(tracked_files, source, deadline), deadline)
        for file_path in untracked_files:
            findings.extend(scan_whole_file(file_path, deadline))
    except (ScanTimeout, subprocess.TimeoutExpired):
        return {"status": "timeout", "timeout_seconds": timeout, "findings": []}

    findings, suppressed = apply_allowlist(findings, allow)
    if selected_count == 0:
        status = "no_changes"
    else:
        status = "secrets_detected" if findings else "ok"
    return {
        "status": status,
        "source": source,
        "timeout_seconds": timeout,
        "selected_file_count": selected_count,
        "suppressed_by_allowlist": suppressed,
        "findings": findings,
    }


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
        help="time budget in seconds for diff collection and the regex pass",
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
        allow = gitscope.Allowlist.empty() if args.no_allowlist else gitscope.Allowlist.load()
        result = scan(source, tracked_files, untracked_files, allow, args.timeout)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        if result["status"] == "timeout":
            return 3
        return 2 if result["findings"] else 0
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Scan selected added lines for likely secrets using regex."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatternSpec:
    name: str
    regex: re.Pattern[str]


PATTERNS = [
    PatternSpec("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    PatternSpec("aws_sts_key_id", re.compile(r"\bASIA[0-9A-Z]{16}\b")),
    PatternSpec(
        "private_key_block",
        re.compile(r"-----BEGIN (RSA|EC|DSA|OPENSSH|PGP|PRIVATE) PRIVATE KEY-----"),
    ),
    PatternSpec("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    PatternSpec("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    PatternSpec("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    PatternSpec(
        "generic_secret_assignment",
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret|password)\b.{0,20}[:=]\s*['\"][^'\"]{12,}['\"]"
        ),
    ),
]

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def ensure_git_repo() -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("not inside a git repository")


def run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def list_staged_files() -> list[str]:
    return [
        p
        for p in run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMRD"]).splitlines()
        if p.strip()
    ]


def list_unstaged_tracked_files() -> list[str]:
    return [
        p
        for p in run_git(["diff", "--name-only", "--diff-filter=ACMRD"]).splitlines()
        if p.strip()
    ]


def list_untracked_files() -> list[str]:
    return [
        p
        for p in run_git(["ls-files", "--others", "--exclude-standard"]).splitlines()
        if p.strip()
    ]


def unique_paths(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def resolve_scope(
    explicit_files: list[str], source: str, include_untracked: bool
) -> tuple[str, list[str], list[str]]:
    if explicit_files:
        effective_source = "worktree" if source == "auto" else source
        resolved = unique_paths(explicit_files)
        untracked_set = set(list_untracked_files()) if effective_source == "worktree" else set()
        untracked = [item for item in resolved if item in untracked_set]
        tracked = [item for item in resolved if item not in untracked_set]
        return effective_source, tracked, untracked

    if source == "index":
        return "index", list_staged_files(), []

    if source == "worktree":
        tracked = list_unstaged_tracked_files()
        untracked = list_untracked_files() if include_untracked else []
        return "worktree", unique_paths(tracked), unique_paths(untracked)

    staged = list_staged_files()
    if staged:
        return "index", staged, []

    tracked = list_unstaged_tracked_files()
    untracked = list_untracked_files() if include_untracked else []
    return "worktree", unique_paths(tracked), unique_paths(untracked)


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


def scan(diff_text: str) -> list[dict[str, object]]:
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
            added_line = line[1:]
            for spec in PATTERNS:
                if spec.regex.search(added_line):
                    findings.append(
                        {
                            "file": current_file,
                            "line": current_new_line,
                            "pattern": spec.name,
                            "excerpt": added_line[:160],
                        }
                    )
            current_new_line += 1
            continue
        if line.startswith(" "):
            current_new_line += 1

    return findings


def scan_untracked_file(path: str) -> list[dict[str, object]]:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return []

    try:
        payload = file_path.read_bytes()
    except OSError:
        return []

    if b"\x00" in payload[:2048]:
        return []

    text = payload.decode("utf-8", errors="ignore")
    findings: list[dict[str, object]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for spec in PATTERNS:
            if spec.regex.search(line):
                findings.append(
                    {
                        "file": path,
                        "line": lineno,
                        "pattern": spec.name,
                        "excerpt": line[:160],
                    }
                )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
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
    args = parser.parse_args()

    try:
        ensure_git_repo()
        source, tracked_files, untracked_files = resolve_scope(
            args.files, args.source, args.include_untracked
        )
        diff_text = run_git_diff(tracked_files, source, args.timeout)

        findings = scan(diff_text)
        for file_path in untracked_files:
            findings.extend(scan_untracked_file(file_path))

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
                {
                    "status": "timeout",
                    "timeout_seconds": args.timeout,
                    "findings": [],
                },
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

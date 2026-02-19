#!/usr/bin/env python3
"""Scan staged added lines for likely secrets using regex."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass


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


def run_git_diff(timeout_seconds: float) -> str:
    result = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color", "--diff-filter=ACMR"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff --cached failed")
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="timeout in seconds for staged diff collection",
    )
    args = parser.parse_args()

    try:
        ensure_git_repo()
        diff_text = run_git_diff(args.timeout)
        if not diff_text.strip():
            print(
                json.dumps(
                    {
                        "status": "no_staged_changes",
                        "timeout_seconds": args.timeout,
                        "findings": [],
                    },
                    ensure_ascii=True,
                    indent=2,
                )
            )
            return 0

        findings = scan(diff_text)
        status = "secrets_detected" if findings else "ok"
        print(
            json.dumps(
                {
                    "status": status,
                    "timeout_seconds": args.timeout,
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

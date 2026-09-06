#!/usr/bin/env python3
"""Detect unresolved merge conflict blocks in the selected commit scope."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gitscope  # noqa: E402

START_RE = re.compile(r"^<{7}(?: .*)?$")
MIDDLE_RE = re.compile(r"^={7}$")
END_RE = re.compile(r"^>{7}(?: .*)?$")


@dataclass
class ConflictBlock:
    start_line: int
    saw_middle: bool = False


def scan_conflicts(text: str) -> list[dict[str, object]]:
    """Report only real marker blocks; a lone ======= is not a conflict."""
    blocks: list[ConflictBlock] = []
    findings: list[dict[str, object]] = []

    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if START_RE.match(line):
            blocks.append(ConflictBlock(start_line=lineno))
            continue

        if MIDDLE_RE.match(line):
            if blocks:
                blocks[-1].saw_middle = True
            continue

        if END_RE.match(line):
            if not blocks:
                continue
            block = blocks.pop()
            marker = "<<<<<<<" if block.saw_middle else "<<<<<<< (missing =======)"
            findings.append({"line": block.start_line, "marker": marker})

    for block in blocks:
        findings.append({"line": block.start_line, "marker": "<<<<<<< (unterminated block)"})

    return findings


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
        help="read file contents from git index or working tree",
    )
    args = parser.parse_args()

    try:
        gitscope.ensure_git_repo()
        source, tracked, untracked = gitscope.resolve_scope(
            args.files, args.source, args.include_untracked
        )
        files = gitscope.unique_paths(tracked + untracked)
        conflicts: list[dict[str, object]] = []
        checked = 0
        skipped_binary = 0
        skipped_unreadable = 0

        for item in files:
            payload = gitscope.load_bytes(item, source)
            if payload is None:
                skipped_unreadable += 1
                continue
            if gitscope.is_binary(payload):
                skipped_binary += 1
                continue
            checked += 1
            text = payload.decode("utf-8", errors="ignore")
            for finding in scan_conflicts(text):
                conflicts.append({"file": item, **finding})

        print(
            json.dumps(
                {
                    "status": "conflicts" if conflicts else "ok",
                    "source": source,
                    "checked_files": checked,
                    "skipped_binary_files": skipped_binary,
                    "skipped_unreadable_files": skipped_unreadable,
                    "conflicts": conflicts,
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return 2 if conflicts else 0
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

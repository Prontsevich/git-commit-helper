#!/usr/bin/env python3
"""Detect merge conflict markers in selected files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import re
import subprocess
import sys
from pathlib import Path

START_RE = re.compile(r"^<{7}(?: .*)?$")
MIDDLE_RE = re.compile(r"^={7}$")
END_RE = re.compile(r"^>{7}(?: .*)?$")


@dataclass
class ConflictBlock:
    start_line: int
    saw_middle: bool = False


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


def run_git_bytes(args: list[str]) -> bytes:
    result = subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="ignore").strip() or f"git {' '.join(args)} failed")
    return result.stdout


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
) -> tuple[str, list[str]]:
    if explicit_files:
        effective_source = "worktree" if source == "auto" else source
        return effective_source, unique_paths(explicit_files)

    if source == "index":
        return "index", list_staged_files()

    if source == "worktree":
        files = list_unstaged_tracked_files()
        if include_untracked:
            files.extend(list_untracked_files())
        return "worktree", unique_paths(files)

    staged = list_staged_files()
    if staged:
        return "index", staged

    files = list_unstaged_tracked_files()
    if include_untracked:
        files.extend(list_untracked_files())
    return "worktree", unique_paths(files)


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:2048]


def load_bytes(path: str, source: str) -> bytes | None:
    if source == "index":
        try:
            return run_git_bytes(["show", f":{path}"])
        except RuntimeError:
            return None

    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None
    try:
        return file_path.read_bytes()
    except OSError:
        return None


def scan_conflicts(text: str) -> list[dict[str, object]]:
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
            if block.saw_middle:
                findings.append({"line": block.start_line, "marker": "<<<<<<<"})
            else:
                findings.append(
                    {
                        "line": block.start_line,
                        "marker": "<<<<<<< (missing =======)",
                    }
                )

    for block in blocks:
        findings.append(
            {
                "line": block.start_line,
                "marker": "<<<<<<< (unterminated block)",
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
        help="read file contents from git index or working tree",
    )
    args = parser.parse_args()

    try:
        ensure_git_repo()
        source, files = resolve_scope(args.files, args.source, args.include_untracked)
        conflicts: list[dict[str, object]] = []
        checked = 0
        skipped_binary = 0
        skipped_unreadable = 0

        for item in files:
            payload = load_bytes(item, source)
            if payload is None:
                skipped_unreadable += 1
                continue
            if is_binary(payload):
                skipped_binary += 1
                continue
            checked += 1
            text = payload.decode("utf-8", errors="ignore")
            for finding in scan_conflicts(text):
                conflicts.append({"file": item, **finding})

        status = "conflicts" if conflicts else "ok"
        print(
            json.dumps(
                {
                    "status": status,
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

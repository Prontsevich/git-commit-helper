#!/usr/bin/env python3
"""Detect merge conflict markers in selected files."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

MARKERS = ("<<<<<<<", "=======", ">>>>>>>")


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


def default_files() -> list[str]:
    staged = [
        p
        for p in run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMRD"]).splitlines()
        if p.strip()
    ]
    if staged:
        return staged
    tracked = [
        p
        for p in run_git(["diff", "--name-only", "--diff-filter=ACMRD"]).splitlines()
        if p.strip()
    ]
    untracked = [
        p
        for p in run_git(["ls-files", "--others", "--exclude-standard"]).splitlines()
        if p.strip()
    ]
    return tracked + untracked


def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return b"\x00" in handle.read(2048)
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", help="optional explicit file paths")
    args = parser.parse_args()

    try:
        ensure_git_repo()
        files = args.files or default_files()
        conflicts: list[dict[str, object]] = []
        checked = 0
        skipped_binary = 0

        for item in files:
            path = Path(item)
            if not path.exists() or not path.is_file():
                continue
            if is_binary(path):
                skipped_binary += 1
                continue
            checked += 1
            try:
                with path.open("r", encoding="utf-8", errors="ignore") as handle:
                    for lineno, line in enumerate(handle, start=1):
                        for marker in MARKERS:
                            if marker in line:
                                conflicts.append(
                                    {"file": item, "line": lineno, "marker": marker}
                                )
            except OSError:
                continue

        status = "conflicts" if conflicts else "ok"
        print(
            json.dumps(
                {
                    "status": status,
                    "checked_files": checked,
                    "skipped_binary_files": skipped_binary,
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

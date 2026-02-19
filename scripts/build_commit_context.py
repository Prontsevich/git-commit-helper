#!/usr/bin/env python3
"""Build deterministic git commit context for the skill."""

from __future__ import annotations

import json
import argparse
import subprocess
import sys
from typing import Any


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


def parse_name_status(raw: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            entries.append(
                {
                    "status": status,
                    "path": parts[2],
                    "old_path": parts[1],
                }
            )
            continue
        if len(parts) >= 2:
            entries.append(
                {
                    "status": status,
                    "path": parts[1],
                    "old_path": None,
                }
            )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    try:
        ensure_git_repo()
        staged_files = [
            p
            for p in run_git(["diff", "--cached", "--name-only", "--diff-filter=ACMRD"]).splitlines()
            if p.strip()
        ]
        unstaged_files = [
            p
            for p in run_git(["diff", "--name-only", "--diff-filter=ACMRD"]).splitlines()
            if p.strip()
        ]
        untracked_files = [
            p
            for p in run_git(["ls-files", "--others", "--exclude-standard"]).splitlines()
            if p.strip()
        ]

        if staged_files:
            mode = "staged"
            selected_files = staged_files
            selected_name_status = parse_name_status(
                run_git(["diff", "--cached", "--name-status", "--diff-filter=ACMRD"])
            )
            shortstat = run_git(["diff", "--cached", "--shortstat"])
        else:
            mode = "unstaged"
            selected_files = unstaged_files
            selected_name_status = parse_name_status(
                run_git(["diff", "--name-status", "--diff-filter=ACMRD"])
            )
            shortstat = run_git(["diff", "--shortstat"])

        payload = {
            "mode": mode,
            "selected_files": selected_files,
            "selected_name_status": selected_name_status,
            "selected_count": len(selected_files),
            "untracked_files": untracked_files,
            "untracked_count": len(untracked_files),
            "shortstat": shortstat,
        }
        print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 0
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

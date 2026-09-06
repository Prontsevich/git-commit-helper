#!/usr/bin/env python3
"""Build a deterministic JSON snapshot of the pending changes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gitscope  # noqa: E402


def parse_name_status(raw: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith(("R", "C")) and len(parts) >= 3:
            entries.append({"status": status, "path": parts[2], "old_path": parts[1]})
            continue
        if len(parts) >= 2:
            entries.append({"status": status, "path": parts[1], "old_path": None})
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    try:
        gitscope.ensure_git_repo()
        staged_files = gitscope.list_staged_files()
        unstaged_files = gitscope.list_unstaged_tracked_files()
        untracked_files = gitscope.list_untracked_files()

        if staged_files:
            mode = "staged"
            selected_files = staged_files
            diff_args = ["diff", "--cached"]
        else:
            mode = "unstaged"
            selected_files = unstaged_files
            diff_args = ["diff"]

        name_status = parse_name_status(
            gitscope.run_git([*diff_args, "--name-status", f"--diff-filter={gitscope.DIFF_FILTER}"])
        )
        shortstat = gitscope.run_git([*diff_args, "--shortstat"])

        payload = {
            "mode": mode,
            "source": "index" if staged_files else "worktree",
            "selected_files": selected_files,
            "selected_name_status": name_status,
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

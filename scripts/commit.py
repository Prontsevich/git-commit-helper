#!/usr/bin/env python3
"""Validate a commit message, stage explicit paths and commit, in one call.

The paths are the approved file list, exactly as preflight.py printed it.
When the index already holds staged files, they must be exactly these paths:
`git commit` takes the whole index, so anything else staged would slip into
the commit unreviewed. Otherwise the paths are added with `git add -- <paths>`
first. Hooks always run; there is no --no-verify.

--dry-run validates and checks the scope without touching git state; run it
before asking the user, then run the same command without it on approval.

Exit codes: 0 committed (or dry run ok), 2 invalid message or scope
mismatch, 1 error or failed commit (hook output included).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gitscope  # noqa: E402
import validate_commit_message  # noqa: E402


def staged_paths() -> set[str]:
    return set(gitscope.run_git_z(["diff", "--cached", "--name-only", "--no-renames"]))


def scope_problem(paths: list[str], staged: set[str]) -> str | None:
    if not staged:
        return None
    wanted = set(paths)
    if staged == wanted:
        return None
    extra = sorted(staged - wanted)
    missing = sorted(wanted - staged)
    parts = []
    if extra:
        parts.append(f"staged but not listed: {', '.join(extra)}")
    if missing:
        parts.append(f"listed but not staged: {', '.join(missing)}")
    return "Index does not match the given paths (" + "; ".join(parts) + ")."


def unchanged_paths(paths: list[str]) -> list[str]:
    """Paths with nothing to stage: typos, or files outside the worktree scope."""
    changed = set(gitscope.run_git_z(["diff", "--name-only", "--no-renames"]))
    changed |= set(gitscope.list_untracked_files())
    return sorted(set(paths) - changed)


def emit(payload: dict[str, object], code: int) -> int:
    print(json.dumps(payload, ensure_ascii=True, indent=2))
    return code


def run_commit(message_file: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "commit", "-F", message_file],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", help="commit message text")
    group.add_argument("--file", help="path to a commit message file")
    parser.add_argument("paths", nargs="+", help="explicit paths to commit")
    parser.add_argument("--dry-run", action="store_true", help="validate and check only")
    parser.add_argument("--no-commitlint", action="store_true")
    parser.add_argument("--no-coauthor-check", action="store_true")
    args = parser.parse_args()

    try:
        gitscope.ensure_git_repo()
        if args.file is not None:
            with open(args.file, "r", encoding="utf-8") as handle:
                message = handle.read()
        else:
            message = args.message

        validation = validate_commit_message.validate(
            message,
            use_commitlint=not args.no_commitlint,
            check_coauthor=not args.no_coauthor_check,
        )
        if validation["status"] != "ok":
            return emit({"status": "invalid", "validation": validation}, 2)

        staged = staged_paths()
        problem = scope_problem(args.paths, staged)
        if not staged and not problem:
            unchanged = unchanged_paths(args.paths)
            if unchanged:
                problem = f"No changes to stage in: {', '.join(unchanged)}."
        if problem:
            return emit({"status": "scope_mismatch", "error": problem}, 2)

        if args.dry_run:
            return emit(
                {"status": "ok", "dry_run": True, "paths": args.paths,
                 "warnings": validation["warnings"]},
                0,
            )

        if not staged:
            gitscope.run_git(["add", "--", *args.paths])
            problem = scope_problem(args.paths, staged_paths())
            if problem:
                return emit({"status": "scope_mismatch", "error": problem}, 2)

        if args.file is not None:
            result = run_commit(args.file)
        else:
            fd, temp_path = tempfile.mkstemp(prefix="commit-msg-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(message)
                result = run_commit(temp_path)
            finally:
                os.unlink(temp_path)

        if result.returncode != 0:
            return emit({"status": "commit_failed", "output": result.stdout.strip()}, 1)

        head = gitscope.run_git(["log", "-1", "--format=%h%x00%s"]).split("\0", 1)
        return emit(
            {"status": "committed", "commit": head[0], "subject": head[1],
             "paths": args.paths, "warnings": validation["warnings"]},
            0,
        )
    except (RuntimeError, OSError) as exc:
        return emit({"status": "error", "error": str(exc)}, 1)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""One-call inspection of the pending commit scope.

Resolves the scope (staged files if any, else unstaged tracked files plus
untracked files as an option), lists the files with line counts, and runs the
conflict, sensitive-filename and secret checks over it. Replaces running
the individual check scripts and the read-only git commands one by one.

Exit codes: 0 ok or nothing to commit, 2 findings, 3 secret scan timed out,
1 error. Untracked files are checked so they can be offered, but they are
committed only when the user picks an option that lists them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_conflicts  # noqa: E402
import check_secrets  # noqa: E402
import check_sensitive_files  # noqa: E402
import gitscope  # noqa: E402
import propose_split  # noqa: E402


def name_status(diff_args: list[str]) -> list[dict[str, object]]:
    """Changed files without rename pairing, so every path is committable as listed."""
    fields = gitscope.run_git_z(
        [*diff_args, "--name-status", "--no-renames", f"--diff-filter={gitscope.DIFF_FILTER}"]
    )
    return [{"path": path, "status": status} for status, path in zip(fields[::2], fields[1::2])]


def numstat(diff_args: list[str]) -> dict[str, tuple[str, str]]:
    fields = gitscope.run_git_z([*diff_args, "--numstat", "--no-renames"])
    counts: dict[str, tuple[str, str]] = {}
    for field in fields:
        parts = field.split("\t", 2)
        if len(parts) == 3:
            counts[parts[2]] = (parts[0], parts[1])
    return counts


def recent_subjects(count: int) -> list[str]:
    try:
        return gitscope.run_git(["log", f"-n{count}", "--format=%s"]).splitlines()
    except RuntimeError:
        return []  # no commits yet


def inspect(source_arg: str, timeout: float, use_allowlist: bool) -> dict[str, object]:
    source, tracked, untracked = gitscope.resolve_scope([], source_arg, True)
    diff_args = ["diff", "--cached"] if source == "index" else ["diff"]

    files = name_status(diff_args)
    counts = numstat(diff_args)
    for entry in files:
        added, deleted = counts.get(str(entry["path"]), ("-", "-"))
        entry["added"], entry["deleted"] = added, deleted

    staged = set(tracked) if source == "index" else set()
    partially_staged = (
        [p for p in gitscope.list_unstaged_tracked_files() if p in staged] if staged else []
    )

    allow = gitscope.Allowlist.load() if use_allowlist else gitscope.Allowlist.empty()
    scope = gitscope.unique_paths(tracked + untracked)
    deleted = {str(f["path"]) for f in files if f["status"] == "D"}
    conflicts = check_conflicts.check([p for p in scope if p not in deleted], source)
    sensitive = check_sensitive_files.check(scope, allow)
    secrets = check_secrets.scan(source, tracked, untracked, allow, timeout)

    has_findings = bool(
        conflicts["conflicts"] or sensitive["flagged_files"] or secrets["findings"]
    )
    if not scope:
        status = "no_changes"
    elif has_findings:
        status = "findings"
    elif secrets["status"] == "timeout":
        status = "timeout"
    else:
        status = "ok"

    return {
        "status": status,
        "source": source,
        "diff_command": " ".join(["git", *diff_args]),
        "files": files,
        "untracked": untracked,
        "partially_staged": partially_staged,
        "shortstat": gitscope.run_git([*diff_args, "--shortstat"]),
        "checks": {
            "conflicts": conflicts["conflicts"],
            "sensitive_files": sensitive["flagged_files"],
            "secrets": secrets["findings"],
            "secret_scan": secrets["status"],
            "suppressed_by_allowlist": int(sensitive["suppressed_by_allowlist"])
            + int(secrets.get("suppressed_by_allowlist", 0)),
            "unreadable_files": conflicts["skipped_unreadable_files"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        choices=("auto", "index", "worktree"),
        default="auto",
        help="force the scope instead of staged-first detection",
    )
    parser.add_argument("--split", action="store_true", help="add a draft multi-commit plan")
    parser.add_argument("--log", type=int, default=5, help="recent commit subjects to include")
    parser.add_argument(
        "--timeout", type=float, default=2.0, help="time budget for the secret scan"
    )
    parser.add_argument(
        "--no-allowlist",
        action="store_true",
        help=f"ignore {gitscope.ALLOWLIST_FILE} even if present",
    )
    args = parser.parse_args()

    try:
        gitscope.ensure_git_repo()
        result = inspect(args.source, args.timeout, not args.no_allowlist)
        result["recent_subjects"] = recent_subjects(args.log)
        if args.split:
            paths = [str(f["path"]) for f in result["files"]] + list(result["untracked"])
            result["split"] = propose_split.draft_plan(paths)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return {"findings": 2, "timeout": 3}.get(str(result["status"]), 0)
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

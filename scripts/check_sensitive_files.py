#!/usr/bin/env python3
"""Detect sensitive file names in selected commit scope."""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

EXACT_NAMES = {
    ".env",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials",
    "secrets",
}

GLOB_PATTERNS = [
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.kubeconfig",
    "*secret*",
    "*credential*",
]


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


def classify(path: str) -> list[str]:
    hits: list[str] = []
    name = Path(path).name.lower()
    full = path.lower()
    for exact in EXACT_NAMES:
        if name == exact:
            hits.append(f"exact:{exact}")
    for pattern in GLOB_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(full, pattern):
            hits.append(f"glob:{pattern}")
    return hits


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
    args = parser.parse_args()

    try:
        ensure_git_repo()
        source, files = resolve_scope(args.files, args.source, args.include_untracked)
        flagged: list[dict[str, object]] = []
        for file_path in files:
            rules = classify(file_path)
            if rules:
                flagged.append({"file": file_path, "rules": rules})

        status = "sensitive_files_detected" if flagged else "ok"
        print(
            json.dumps(
                {
                    "status": status,
                    "source": source,
                    "checked_files": len(files),
                    "flagged_files": flagged,
                },
                ensure_ascii=True,
                indent=2,
            )
        )
        return 2 if flagged else 0
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

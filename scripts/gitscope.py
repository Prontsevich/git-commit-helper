#!/usr/bin/env python3
"""Shared git helpers for the commit-helper scripts.

Every check script resolves the same "selected scope": staged files when the
index is non-empty, otherwise unstaged tracked files plus, on request,
untracked files. Keeping that logic in one place means a scope bug is fixed
once and every script sees the same file list.

Scripts import this module by adding their own directory to sys.path, so each
one stays runnable by absolute path from any workspace.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

DIFF_FILTER = "ACMRD"
ALLOWLIST_FILE = ".git-commit-helper-allow"


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
        raise RuntimeError(
            result.stderr.decode("utf-8", errors="ignore").strip()
            or f"git {' '.join(args)} failed"
        )
    return result.stdout


def _lines(raw: str) -> list[str]:
    return [p for p in raw.splitlines() if p.strip()]


def list_staged_files() -> list[str]:
    return _lines(run_git(["diff", "--cached", "--name-only", f"--diff-filter={DIFF_FILTER}"]))


def list_unstaged_tracked_files() -> list[str]:
    return _lines(run_git(["diff", "--name-only", f"--diff-filter={DIFF_FILTER}"]))


def list_untracked_files() -> list[str]:
    return _lines(run_git(["ls-files", "--others", "--exclude-standard"]))


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
    """Return (effective_source, tracked_files, untracked_files).

    `source` is one of "auto", "index", "worktree". Explicit files win over
    discovery; with "auto" they are read from the working tree.
    """
    if explicit_files:
        effective_source = "worktree" if source == "auto" else source
        resolved = unique_paths(explicit_files)
        untracked_set = (
            set(list_untracked_files()) if effective_source == "worktree" else set()
        )
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


def is_binary(data: bytes) -> bool:
    return b"\x00" in data[:2048]


def load_bytes(path: str, source: str) -> bytes | None:
    """Read a file from the index (`git show :path`) or the working tree."""
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


class Allowlist:
    """Repo-level suppressions from `.git-commit-helper-allow`.

    One entry per line, `#` comments allowed. `path:<glob>` entries match file
    paths (used by the file-name check and to skip whole files in the secret
    scan); every other line is a regex matched against a secret finding's
    excerpt.
    """

    def __init__(self, path_globs: list[str], excerpt_patterns: list[re.Pattern[str]]):
        self.path_globs = path_globs
        self.excerpt_patterns = excerpt_patterns

    @classmethod
    def load(cls, root: str | None = None) -> "Allowlist":
        if root is None:
            try:
                root = run_git(["rev-parse", "--show-toplevel"])
            except RuntimeError:
                root = "."
        file_path = Path(root) / ALLOWLIST_FILE
        if not file_path.exists():
            return cls([], [])
        globs: list[str] = []
        patterns: list[re.Pattern[str]] = []
        for raw in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("path:"):
                globs.append(line[5:].strip())
                continue
            try:
                patterns.append(re.compile(line))
            except re.error:
                continue
        return cls(globs, patterns)

    @classmethod
    def empty(cls) -> "Allowlist":
        return cls([], [])

    def allows_path(self, path: str) -> bool:
        name = Path(path).name
        return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(name, g) for g in self.path_globs)

    def allows_excerpt(self, excerpt: str) -> bool:
        return any(p.search(excerpt) for p in self.excerpt_patterns)

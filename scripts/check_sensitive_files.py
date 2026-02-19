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
    args = parser.parse_args()

    try:
        ensure_git_repo()
        files = args.files or default_files()
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

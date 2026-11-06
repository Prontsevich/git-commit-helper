#!/usr/bin/env python3
"""Detect sensitive file names in the selected commit scope.

`path:<glob>` entries in `.git-commit-helper-allow` at the repo root suppress
matches for files that legitimately carry a risky name (for example a script
called check_secrets.py). Suppressed files are counted in the output.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gitscope  # noqa: E402

EXACT_NAMES = {
    ".env",
    ".envrc",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
    "secrets",
    "service-account.json",
    "terraform.tfvars",
}

GLOB_PATTERNS = [
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.jks",
    "*.keystore",
    "*.kubeconfig",
    "*.tfstate",
    "*.tfstate.backup",
    "*secret*",
    "*credential*",
    "*.private",
]

# Names that match a broad glob above but are almost always safe to commit.
SAFE_NAMES = {
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
}


def classify(path: str) -> list[str]:
    hits: list[str] = []
    name = Path(path).name.lower()
    full = path.lower()
    if name in SAFE_NAMES:
        return hits
    for exact in sorted(EXACT_NAMES):
        if name == exact:
            hits.append(f"exact:{exact}")
    for pattern in GLOB_PATTERNS:
        if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(full, pattern):
            hits.append(f"glob:{pattern}")
    return hits


def check(files: list[str], allow: gitscope.Allowlist) -> dict[str, object]:
    flagged: list[dict[str, object]] = []
    suppressed = 0
    for file_path in files:
        rules = classify(file_path)
        if not rules:
            continue
        if allow.allows_path(file_path):
            suppressed += 1
            continue
        flagged.append({"file": file_path, "rules": rules})
    return {
        "status": "sensitive_files_detected" if flagged else "ok",
        "checked_files": len(files),
        "suppressed_by_allowlist": suppressed,
        "flagged_files": flagged,
    }


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
        help="resolve selected file scope from git index or working tree",
    )
    parser.add_argument(
        "--no-allowlist",
        action="store_true",
        help=f"ignore {gitscope.ALLOWLIST_FILE} even if present",
    )
    args = parser.parse_args()

    try:
        gitscope.ensure_git_repo()
        source, tracked, untracked = gitscope.resolve_scope(
            args.files, args.source, args.include_untracked
        )
        files = gitscope.unique_paths(tracked + untracked)
        allow = gitscope.Allowlist.empty() if args.no_allowlist else gitscope.Allowlist.load()
        result = {"source": source, **check(files, allow)}
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 2 if result["flagged_files"] else 0
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

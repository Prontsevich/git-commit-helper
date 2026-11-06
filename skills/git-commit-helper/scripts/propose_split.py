#!/usr/bin/env python3
"""Draft a multi-commit plan from the selected commit scope.

Files are classified by kind (source, tests, docs, config, ci, generated) and
grouped by the domain their path implies. The output is a starting point: the
agent renames scopes, merges groups that belong together and writes the real
headers. Nothing here touches git state.

Ordering follows the review-friendly strategy from references/commit.md:
shared infrastructure first, one commit per domain (its tests included),
docs and config next, generated artifacts last.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
from collections import OrderedDict
from pathlib import PurePosixPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gitscope  # noqa: E402

GENERATED_PATTERNS = [
    "*.generated.*",
    "*/__generated__/*",
    "__generated__/*",
    "*.g.dart",
    "*.pb.go",
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*.min.js",
    "*.min.css",
    "*.snap",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "poetry.lock",
    "uv.lock",
    "composer.lock",
    "Gemfile.lock",
    "graphify-out/*",
    "dist/*",
    "build/*",
    "coverage/*",
]

TEST_PATTERNS = [
    "tests/*",
    "test/*",
    "*/tests/*",
    "*/test/*",
    "*/__tests__/*",
    "spec/*",
    "*/spec/*",
    "*_test.go",
    "*_test.py",
    "test_*.py",
    "*.test.*",
    "*.spec.*",
    "*Tests.cs",
    "*Test.java",
    "*Test.kt",
]

DOC_PATTERNS = ["*.md", "*.rst", "*.adoc", "docs/*", "doc/*", "LICENSE*", "CHANGELOG*"]

CI_PATTERNS = [".github/*", ".gitlab-ci.yml", ".circleci/*", "azure-pipelines.yml", "Jenkinsfile"]

CONFIG_NAMES = {
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".prettierrc",
    ".eslintrc",
    "package.json",
    "pyproject.toml",
    "setup.cfg",
    "tsconfig.json",
    "Makefile",
    "justfile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
}
CONFIG_SUFFIXES = {".toml", ".ini", ".cfg", ".yml", ".yaml"}

# Path segments that carry no domain meaning on their own.
STRUCTURAL_SEGMENTS = {
    "src", "lib", "libs", "app", "apps", "packages", "pkg", "internal", "cmd",
    "modules", "components", "features", "domains", "services",
}

# Domain names that mean "shared infrastructure" and should be committed first.
INFRA_DOMAINS = {"core", "shared", "common", "utils", "util", "infra", "infrastructure", "base"}

KIND_ORDER = {"infra": 0, "source": 1, "tests": 2, "config": 3, "ci": 4, "docs": 5, "generated": 6}
KIND_TYPE = {
    "infra": "feat",
    "source": "feat",
    "tests": "test",
    "config": "chore",
    "ci": "ci",
    "docs": "docs",
    "generated": "chore",
}


def matches_any(path: str, patterns: list[str]) -> bool:
    name = PurePosixPath(path).name
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)


def classify_kind(path: str) -> str:
    name = PurePosixPath(path).name
    if matches_any(path, GENERATED_PATTERNS):
        return "generated"
    if matches_any(path, CI_PATTERNS):
        return "ci"
    if matches_any(path, TEST_PATTERNS):
        return "tests"
    if matches_any(path, DOC_PATTERNS):
        return "docs"
    parts = PurePosixPath(path).parts
    if len(parts) == 1 and (name in CONFIG_NAMES or PurePosixPath(name).suffix in CONFIG_SUFFIXES):
        return "config"
    return "source"


def domain_of(path: str, kind: str) -> str:
    """First path segment that names a domain, skipping structural folders."""
    parts = list(PurePosixPath(path).parts[:-1])
    if kind == "tests":
        parts = [p for p in parts if p not in {"tests", "test", "__tests__", "spec"}]
    for segment in parts:
        if segment in STRUCTURAL_SEGMENTS:
            continue
        return segment
    return "root"


def build_groups(files: list[str]) -> list[dict[str, object]]:
    groups: "OrderedDict[tuple[str, str], list[str]]" = OrderedDict()
    for path in files:
        kind = classify_kind(path)
        if kind in {"generated", "docs", "ci", "config"}:
            key = (kind, kind)
        else:
            domain = domain_of(path, kind)
            if kind == "source" and domain in INFRA_DOMAINS:
                key = ("infra", domain)
            else:
                # Tests join the domain they exercise so each commit stays self-contained.
                key = ("source", domain)
        groups.setdefault(key, []).append(path)

    result: list[dict[str, object]] = []
    for (kind, domain), paths in groups.items():
        scope = None if domain in {"docs", "config", "ci", "generated", "root"} else domain
        if kind == "source" and all(classify_kind(p) == "tests" for p in paths):
            kind = "tests"
        result.append(
            {
                "kind": kind,
                "domain": domain,
                "suggested_type": KIND_TYPE[kind],
                "suggested_scope": scope,
                "header_stub": f"{KIND_TYPE[kind]}({scope}): " if scope else f"{KIND_TYPE[kind]}: ",
                "files": paths,
            }
        )
    result.sort(key=lambda g: (KIND_ORDER[str(g["kind"])], str(g["domain"])))
    return result


def draft_plan(files: list[str]) -> dict[str, object]:
    """Review-friendly grouping plus the minimal fallback for the same files."""
    groups = build_groups(files)
    generated = [g for g in groups if g["kind"] == "generated"]
    rest_files = [p for g in groups if g["kind"] != "generated" for p in g["files"]]
    minimal: list[dict[str, object]] = []
    if rest_files:
        minimal.append(
            {
                "kind": "source",
                "domain": "all",
                "suggested_type": "feat",
                "suggested_scope": None,
                "header_stub": "feat: ",
                "files": rest_files,
            }
        )
    minimal.extend(generated)
    return {
        "multi_commit_recommended": len(groups) > 1,
        "review_friendly": groups,
        "minimal": minimal,
    }


def render_text(plan: dict[str, object]) -> str:
    lines: list[str] = []
    groups = plan["review_friendly"]
    assert isinstance(groups, list)
    lines.append(f"Selected {plan['selected_count']} file(s) from {plan['source']}.")
    lines.append("")
    lines.append(f"Review-friendly plan ({len(groups)} commit(s)):")
    for index, group in enumerate(groups, start=1):
        lines.append(f"  {index}. {group['header_stub']}<summary>   [{group['kind']}]")
        for path in group["files"]:
            lines.append(f"       {path}")
    minimal = plan["minimal"]
    assert isinstance(minimal, list)
    lines.append("")
    lines.append(f"Minimal plan ({len(minimal)} commit(s)):")
    for index, group in enumerate(minimal, start=1):
        lines.append(f"  {index}. {group['header_stub']}<summary>   ({len(group['files'])} files)")
    return "\n".join(lines)


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
        "--format",
        choices=("json", "text"),
        default="json",
        help="output format",
    )
    args = parser.parse_args()

    try:
        gitscope.ensure_git_repo()
        source, tracked, untracked = gitscope.resolve_scope(
            args.files, args.source, args.include_untracked
        )
        files = gitscope.unique_paths(tracked + untracked)
        plan: dict[str, object] = {
            "status": "ok" if files else "no_changes",
            "source": source,
            "selected_count": len(files),
            **draft_plan(files),
        }
        if args.format == "text":
            print(render_text(plan))
        else:
            print(json.dumps(plan, ensure_ascii=True, indent=2))
        return 0
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

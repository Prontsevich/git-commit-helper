#!/usr/bin/env python3
"""Validate a Conventional Commit message against repo policy.

Two validation modes:
  * commitlint  - if the repo has a commitlint config AND commitlint is
                  runnable via `npx`, defer to it as the authoritative
                  format check, then layer the project-specific extras
                  (ASCII-only, Co-Authored-By trailer nudge) on top.
  * builtin     - otherwise, use the self-contained Conventional Commit
                  rules below.

Header length is a soft rule: <= 72 preferred, up to 100 allowed with a
warning (aligns with commitlint's default header-max-length), > 100 is an
error. Git trailers (Co-Authored-By, Signed-off-by, BREAKING CHANGE, …)
and lines containing URLs are exempt from the body wrap entirely; other body
lines follow the header's two tiers - 72 preferred, 100 hard.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ALLOWED_TYPES = (
    "feat",
    "fix",
    "refactor",
    "docs",
    "test",
    "perf",
    "style",
    "build",
    "ci",
    "chore",
    "revert",
    # Not in the Conventional Commits spec, which says nothing about merges.
    # Added because merge commits are real commits that still want a readable
    # subject, and rejecting the only type that fits pushes them to bypass the
    # validator entirely.
    "merge",
)

TYPE_PATTERN = "|".join(ALLOWED_TYPES)
HEADER_RE = re.compile(
    rf"^(?P<type>{TYPE_PATTERN})(?:\((?P<scope>[^()\r\n]+)\))?(?P<breaking>!)?: (?P<summary>.+)$"
)

HEADER_SOFT_MAX = 72
HEADER_HARD_MAX = 100
# Body lines are tiered the same way the header is: the wrap is a preference,
# not a gate. A hard failure a few characters over teaches people to skip the
# check, which costs more than an unwrapped line.
BODY_WRAP = 72
BODY_HARD_MAX = 100

BREAKING_FOOTER_PREFIX = "BREAKING CHANGE:"
# A git trailer line: "Key: value" with a hyphenated single-token key.
TRAILER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*: .+$")

PAST_TENSE_HINTS = {
    "added",
    "fixed",
    "updated",
    "removed",
    "changed",
    "refactored",
    "improved",
    "created",
    "merged",
    "bumped",
}

COMMITLINT_CONFIG_NAMES = (
    "commitlint.config.js",
    "commitlint.config.cjs",
    "commitlint.config.mjs",
    "commitlint.config.ts",
    ".commitlintrc",
    ".commitlintrc.json",
    ".commitlintrc.yaml",
    ".commitlintrc.yml",
    ".commitlintrc.js",
    ".commitlintrc.cjs",
    ".commitlintrc.ts",
)


def load_message(args: argparse.Namespace) -> str:
    if args.message is not None:
        return args.message

    if args.file is not None:
        with open(args.file, "r", encoding="utf-8") as handle:
            return handle.read()

    return sys.stdin.read()


def repo_root() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "."
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return "."


def detect_commitlint(root: str) -> bool:
    base = Path(root)
    for name in COMMITLINT_CONFIG_NAMES:
        if (base / name).exists():
            return True
    pkg = base / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if isinstance(data, dict) and "commitlint" in data:
            return True
    return False


def run_commitlint(message: str, root: str, timeout: float = 20.0) -> dict[str, object]:
    """Run the repo's commitlint over `message` via stdin.

    Returns {"available": False} when commitlint cannot be resolved/run, so
    the caller can fall back to the built-in validator.
    """
    try:
        version = subprocess.run(
            ["npx", "--no-install", "commitlint", "--version"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"available": False}
    if version.returncode != 0:
        return {"available": False}

    try:
        proc = subprocess.run(
            ["npx", "--no-install", "commitlint"],
            cwd=root,
            input=message,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"available": True, "passed": False, "output": "commitlint timed out."}

    output = (proc.stdout + proc.stderr).strip()
    return {"available": True, "passed": proc.returncode == 0, "output": output}


def is_exempt_from_wrap(line: str) -> bool:
    """Trailers and URL-bearing lines are not subject to the body wrap."""
    return (
        bool(TRAILER_RE.match(line))
        or line.startswith(BREAKING_FOOTER_PREFIX)
        or "://" in line
    )


def coauthor_nudge(trailing_lines: list[str]) -> list[str]:
    has_coauthor = any(
        line.lower().startswith("co-authored-by:") for line in trailing_lines
    )
    if has_coauthor:
        return []
    return [
        "No Co-Authored-By trailer found; append the harness-required trailer "
        "(e.g. 'Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>')."
    ]


def builtin_validate(message: str, lines: list[str]) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []

    if any(ord(ch) > 127 for ch in message):
        errors.append("Commit message must use English ASCII text only.")

    header = lines[0] if lines else ""
    if not header:
        errors.append("Header line is required.")
        return {"status": "invalid", "mode": "builtin", "errors": errors, "warnings": warnings}

    header_len = len(header)
    if header_len > HEADER_HARD_MAX:
        errors.append(
            f"Header exceeds the hard limit of {HEADER_HARD_MAX} characters ({header_len}); shorten it."
        )
    elif header_len > HEADER_SOFT_MAX:
        warnings.append(
            f"Header is {header_len} chars (over the preferred {HEADER_SOFT_MAX}); "
            "acceptable when it genuinely improves clarity, but keep it tight."
        )

    match = HEADER_RE.match(header)
    parsed: dict[str, object] = {}
    if not match:
        allowed = ", ".join(ALLOWED_TYPES)
        errors.append(
            f"Header must match Conventional Commit format with allowed type: {allowed}."
        )
    else:
        summary = match.group("summary")
        parsed = {
            "type": match.group("type"),
            "scope": match.group("scope"),
            "breaking": bool(match.group("breaking")),
            "summary": summary,
        }
        if summary.endswith("."):
            errors.append("Header summary must not end with a period.")
        words = summary.split()
        if words and words[0].lower() in PAST_TENSE_HINTS:
            warnings.append("Summary may not be imperative mood; review wording.")

    if len(lines) > 1 and lines[1] != "":
        errors.append("Second line must be blank.")

    trailing_lines = lines[2:] if len(lines) > 2 else []
    for lineno, line in enumerate(trailing_lines, start=3):
        if is_exempt_from_wrap(line):
            continue
        line_len = len(line)
        if line_len > BODY_HARD_MAX:
            errors.append(
                f"Line {lineno} exceeds the hard limit of {BODY_HARD_MAX} characters "
                f"({line_len}); wrap it."
            )
        elif line_len > BODY_WRAP:
            warnings.append(
                f"Line {lineno} is {line_len} chars (over the preferred {BODY_WRAP}); "
                "wrap it when convenient."
            )

    has_breaking_footer = any(
        line.startswith(BREAKING_FOOTER_PREFIX) for line in trailing_lines
    )
    if parsed:
        breaking = bool(parsed.get("breaking"))
        if breaking and not has_breaking_footer:
            errors.append("Header uses ! but BREAKING CHANGE: footer is missing.")
        if has_breaking_footer and not breaking:
            errors.append("BREAKING CHANGE: footer requires ! in the header.")

    warnings.extend(coauthor_nudge(trailing_lines))

    status = "invalid" if errors else "ok"
    payload: dict[str, object] = {
        "status": status,
        "mode": "builtin",
        "errors": errors,
        "warnings": warnings,
    }
    if parsed:
        payload["parsed"] = parsed
    return payload


def validate(message: str, use_commitlint: bool = True) -> dict[str, object]:
    lines = message.splitlines()

    if not message.strip():
        return {
            "status": "invalid",
            "mode": "builtin",
            "errors": ["Commit message must not be empty."],
            "warnings": [],
        }

    root = repo_root()
    if use_commitlint and detect_commitlint(root):
        cl = run_commitlint(message, root)
        if cl.get("available"):
            errors: list[str] = []
            warnings: list[str] = []
            output = str(cl.get("output") or "").strip()
            if not cl.get("passed"):
                errors.append("commitlint reported problems:\n" + (output or "(no output)"))
            elif output:
                warnings.append(output)

            trailing_lines = lines[2:] if len(lines) > 2 else []
            if any(ord(ch) > 127 for ch in message):
                errors.append("Commit message must use English ASCII text only.")
            warnings.extend(coauthor_nudge(trailing_lines))

            status = "invalid" if errors else "ok"
            return {
                "status": status,
                "mode": "commitlint",
                "errors": errors,
                "warnings": warnings,
            }

        # Config present but commitlint not runnable: fall back, but say so.
        result = builtin_validate(message, lines)
        result.setdefault("warnings", [])
        result["warnings"].insert(
            0,
            "commitlint config detected but commitlint is not runnable via npx; "
            "used built-in validation instead.",
        )
        return result

    return builtin_validate(message, lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--message", help="commit message text passed inline")
    group.add_argument("--file", help="path to commit message file")
    parser.add_argument(
        "--no-commitlint",
        action="store_true",
        help="skip commitlint delegation and always use built-in validation",
    )
    args = parser.parse_args()

    try:
        message = load_message(args)
        result = validate(message, use_commitlint=not args.no_commitlint)
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 2 if result["status"] != "ok" else 0
    except OSError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

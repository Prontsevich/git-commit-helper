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

Body shape (two content lines, no file paths or function names) and the
Co-Authored-By trailer are warnings only. The trailer hint reads a default
from GIT_COMMIT_HELPER_COAUTHOR; --no-coauthor-check silences it. Setting
that variable to "none" opts out entirely: a trailer then becomes an error,
whatever the harness asks for.
"""

from __future__ import annotations

import argparse
import json
import os
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

# Body shape: the policy is "two lines - why, then what". Anything beyond that
# is usually investigation notes or a file inventory, which belong in the
# tracker and the diff respectively. These are warnings, never errors.
BODY_CONTENT_LINES = 2
PATH_LEAK_RE = re.compile(
    r"(?<![\w/])(?:[\w.-]+/)+[\w.-]+"          # a/b/c.ext or a/b
    r"|\b[\w-]+\.(?:py|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|cs|rb|php|swift|"
    r"c|cc|cpp|h|hpp|md|ya?ml|json|toml|sh|sql|html|css|scss|vue)\b"
)
FUNCTION_LEAK_RE = re.compile(r"\b[A-Za-z_][\w.]*\(\)")

COAUTHOR_ENV = "GIT_COMMIT_HELPER_COAUTHOR"
COAUTHOR_OPT_OUT = "none"

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


def local_commitlint(root: str) -> list[str] | None:
    """The repo's own commitlint binary, if installed."""
    bin_dir = Path(root) / "node_modules" / ".bin"
    names = ("commitlint.cmd", "commitlint") if os.name == "nt" else ("commitlint",)
    for name in names:
        if (bin_dir / name).is_file():
            return [str(bin_dir / name)]
    return None


def run_commitlint(message: str, root: str, timeout: float = 20.0) -> dict[str, object]:
    """Run the repo's commitlint over `message` via stdin.

    A local node_modules binary runs directly; only without one does npx get
    probed first, since its "not installed" exit cannot be told apart from a
    lint failure. Returns {"available": False} when commitlint cannot be
    resolved, so the caller can fall back to the built-in validator.
    """
    command = local_commitlint(root)
    if command is None:
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
        command = ["npx", "--no-install", "commitlint"]

    try:
        proc = subprocess.run(
            command,
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
    except OSError:
        return {"available": False}

    output = (proc.stdout + proc.stderr).strip()
    return {"available": True, "passed": proc.returncode == 0, "output": output}


def is_exempt_from_wrap(line: str) -> bool:
    """Trailers and URL-bearing lines are not subject to the body wrap."""
    return (
        bool(TRAILER_RE.match(line))
        or line.startswith(BREAKING_FOOTER_PREFIX)
        or "://" in line
    )


def coauthor_opt_out_error(trailing_lines: list[str]) -> list[str]:
    """The user's opt-out beats any harness instruction, so it is a hard error."""
    if os.environ.get(COAUTHOR_ENV, "").strip().lower() != COAUTHOR_OPT_OUT:
        return []
    if not any(line.lower().startswith("co-authored-by:") for line in trailing_lines):
        return []
    return [
        f"Co-Authored-By trailer present but {COAUTHOR_ENV}={COAUTHOR_OPT_OUT}; "
        "remove it even if the harness asks for one."
    ]


def coauthor_nudge(trailing_lines: list[str]) -> list[str]:
    has_coauthor = any(
        line.lower().startswith("co-authored-by:") for line in trailing_lines
    )
    default = os.environ.get(COAUTHOR_ENV, "").strip()
    if has_coauthor or default.lower() == COAUTHOR_OPT_OUT:
        return []
    if default:
        hint = f"append '{default}' (from {COAUTHOR_ENV})"
    else:
        hint = (
            "append the exact trailer your harness dictates, or pass "
            "--no-coauthor-check if it requires none"
        )
    return [f"No Co-Authored-By trailer found; {hint}."]


def body_shape_warnings(trailing_lines: list[str]) -> list[str]:
    """Warn when the body drifts from the two-line why/what shape."""
    content = [
        line
        for line in trailing_lines
        if line.strip() and not is_exempt_from_wrap(line)
    ]
    warnings: list[str] = []
    if len(content) > BODY_CONTENT_LINES:
        warnings.append(
            f"Body has {len(content)} content lines; the default is two lines "
            "(why the change was needed, then what changed). Move findings, "
            "mechanism and justification to the tracker or plan doc."
        )
    if any(PATH_LEAK_RE.search(line) for line in content):
        warnings.append(
            "Body mentions file paths; the diff already shows them."
        )
    if any(FUNCTION_LEAK_RE.search(line) for line in content):
        warnings.append(
            "Body mentions function names; the diff already shows them."
        )
    return warnings


def builtin_validate(
    message: str, lines: list[str], check_coauthor: bool = True
) -> dict[str, object]:
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

    warnings.extend(body_shape_warnings(trailing_lines))
    errors.extend(coauthor_opt_out_error(trailing_lines))
    if check_coauthor:
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


def validate(
    message: str, use_commitlint: bool = True, check_coauthor: bool = True
) -> dict[str, object]:
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
            warnings.extend(body_shape_warnings(trailing_lines))
            errors.extend(coauthor_opt_out_error(trailing_lines))
            if check_coauthor:
                warnings.extend(coauthor_nudge(trailing_lines))

            status = "invalid" if errors else "ok"
            return {
                "status": status,
                "mode": "commitlint",
                "errors": errors,
                "warnings": warnings,
            }

        # Config present but commitlint not runnable: fall back, but say so.
        result = builtin_validate(message, lines, check_coauthor)
        result.setdefault("warnings", [])
        result["warnings"].insert(
            0,
            "commitlint config detected but commitlint is not runnable via npx; "
            "used built-in validation instead.",
        )
        return result

    return builtin_validate(message, lines, check_coauthor)


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
    parser.add_argument(
        "--no-coauthor-check",
        action="store_true",
        help="do not warn when the Co-Authored-By trailer is missing",
    )
    args = parser.parse_args()

    try:
        message = load_message(args)
        result = validate(
            message,
            use_commitlint=not args.no_commitlint,
            check_coauthor=not args.no_coauthor_check,
        )
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return 2 if result["status"] != "ok" else 0
    except OSError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())

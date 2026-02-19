---
name: git-commit-helper
description: Use when a user asks to prepare, draft, or execute a git commit. Enforce a safe commit workflow with explicit confirmation, staged-first analysis, sensitive data checks, conflict checks, and strict Conventional Commits formatting in English.
---

# Git Commit Helper

Read `references/commit.md` before running commands.

Use deterministic helpers when available:
- `scripts/build_commit_context.py`
- `scripts/check_conflicts.py`
- `scripts/check_sensitive_files.py`
- `scripts/check_sensitive_regex_staged.py`

## Workflow Contract

1. Run read-only inspection first.
2. If staged files exist, scope analysis and commit to staged files only.
3. If no staged files exist, analyze unstaged tracked files and ask whether to include untracked files.
4. Block commit on unresolved merge conflict markers.
5. Run sensitive file-name checks; require explicit user confirmation if matches are found.
6. Run regex secret checks on staged diff only. If timeout occurs, continue with filename checks and warn that regex scan timed out.
7. Propose a full English Conventional Commit message and request explicit `yes` or `no`.
8. Execute `git commit` only after explicit `yes`.
9. Never use `git add .`; always use explicit file paths.
10. If user requests cancel/stop, end workflow without running write commands.

## Commit Message Rules

- Header max 50 characters.
- Imperative mood in summary.
- No trailing period in summary.
- Body lines max 72 characters.
- Allowed types: `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `style`, `build`, `ci`, `chore`, `revert`.
- For breaking changes: use `!` in header and add `BREAKING CHANGE:` footer.
- Keep commit messages in English only.

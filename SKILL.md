---
name: git-commit-helper
description: Use when a user asks to prepare, draft, or execute a git commit. Enforce a safe commit workflow with explicit confirmation, staged-first analysis, sensitive data checks, conflict checks, Conventional Commits formatting in English (deferring to the repo's commitlint config when present), scope derived from paths (not repo name), a required Co-Authored-By trailer, and a review-friendly multi-commit plan when changes span layers or domains.
---

# Git Commit Helper

Read `references/commit.md` before running commands.

**Scripts location:** Commands run in the **workspace** (project) directory, not in the skill folder. Always invoke helper scripts by **absolute path** to the skill:

- **Unix/macOS:** `~/.claude/skills/git-commit-helper/scripts/`
- **Windows:** `%USERPROFILE%\.claude\skills\git-commit-helper\scripts\`

Example: `python3 ~/.claude/skills/git-commit-helper/scripts/validate_commit_message.py --file <path>`.

Use deterministic helpers when available (prefix with the path above):
- `scripts/build_commit_context.py`
- `scripts/check_conflicts.py`
- `scripts/check_sensitive_files.py`
- `scripts/check_sensitive_regex_staged.py`
- `scripts/validate_commit_message.py`

## Workflow Contract

1. Run read-only inspection first.
2. If staged files exist, scope analysis and commit to staged files only (`--source index`).
3. If no staged files exist, analyze unstaged tracked files and ask whether to include untracked files.
4. Include untracked files only after explicit user `yes` (`--include-untracked`).
5. If unresolved merge conflict markers are detected, require explicit user confirmation before continuing.
6. Run sensitive file-name checks in the selected scope; require explicit user confirmation if matches are found.
7. Run regex secret checks in the selected scope (`--source index|worktree`). If timeout occurs, continue with filename checks only after explicit user confirmation.
8. Propose a full English Conventional Commit message. Include the harness-required `Co-Authored-By` trailer as the last line (see **Co-Authored-By trailer** below), then validate it with `scripts/validate_commit_message.py`.
9. Request explicit `yes` or `no` for the full validated message before running `git commit`.
10. Never use `git add .`; always use explicit file paths.
11. If user requests cancel/stop, end workflow without running write commands.

## Commit Message Rules

- Header length: keep **≤ 72 characters** by default. Up to **100** is allowed when it genuinely improves the description — the validator warns but does not block. Over 100 is an error: shorten it. Never pad a header just to fill space.
- Imperative mood in summary.
- No trailing period in summary.
- Body: **two lines by default** — one on **why** the change was needed, one on briefly **what** changed. Omit the body entirely when the header already says it. Every limit here is a ceiling, never a target: do not stretch a body to fill the allowance. Do not list files, function names, or implementation details — the diff shows that. Do not narrate the bug mechanism, the investigation, or comparisons to sibling modules — that belongs in the tracker or plan doc.
- Body lines: **≤ 72 preferred**, up to **100 allowed** (the validator warns), **> 100 is an error** — the same two tiers as the header, so a line a few characters over is a nudge, not a refusal. Git trailers (`Co-Authored-By`, `Signed-off-by`, `BREAKING CHANGE`, …) and lines containing URLs are exempt from the wrap entirely.
- Allowed types: `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `style`, `build`, `ci`, `chore`, `revert`, `merge`.
- `merge` is a local addition, not part of the Conventional Commits spec: a merge commit still wants a readable subject, and having no type that fits only teaches people to skip the check.
- For breaking changes: use `!` in header and add `BREAKING CHANGE:` footer.
- Keep commit messages in English only.
- **When the repo has a commitlint config, commitlint is the source of truth** for these format rules — see **commitlint / husky** below.

## Co-Authored-By trailer

The running agent's harness requires every commit it authors to end with a
`Co-Authored-By` trailer naming the model, e.g.:

```text
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

Always append this trailer as the **last line** of the message body, after a
blank line. The exact model string comes from the harness instruction in effect
for the current session — use the string that session requires, not a hardcoded
one. `validate_commit_message.py` warns when the trailer is missing so it is not
forgotten.

## commitlint / husky

- `validate_commit_message.py` auto-detects a commitlint config (`commitlint.config.*`, `.commitlintrc*`, or a `commitlint` key in `package.json`). When one exists **and** commitlint is runnable via `npx`, the validator delegates format checks to commitlint (`"mode": "commitlint"` in its output) and layers only the project extras (ASCII-only, Co-Authored-By nudge) on top. The built-in rules above then act as documentation of the intended defaults, not a second gate.
- If a commitlint config exists but the tool is not installed, the validator falls back to built-in rules and emits a warning saying so.
- Pass `--no-commitlint` to force built-in validation regardless of repo config.
- **Never bypass git hooks.** If the repo uses husky (`.husky/` directory), do not pass `--no-verify` to `git commit`; let the `commit-msg`/`pre-commit` hooks run. A husky `commit-msg` hook typically runs commitlint again — that is expected and complements the pre-commit validation.

## Commit plan (before any `git commit`)

When changes touch **multiple layers or domains**, do not default to a single commit.
Read **Commit split strategy** and **Scope selection** in `references/commit.md`, then propose a
**multi-commit plan** (message + explicit file list per commit) and wait for user approval.

Offer two options unless the user already chose:
1. **Minimal** — one source commit (+ optional separate commit for generated artifacts if applicable)
2. **Review-friendly** — infrastructure → per-domain integration → generated artifacts last

Execute commits **sequentially** in the approved order; re-run read-only inspection between commits if needed.

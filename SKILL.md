---
name: git-commit-helper
description: This skill should be used when a user requests help preparing or creating a git commit with mandatory safety checks and Conventional Commits formatting.
---

# Git Commit Helper

## Purpose

- Enforce a safe, repeatable commit workflow with required read-only checks before any commit.
- Ensure Conventional Commits formatting rules are applied consistently.
- Prevent committing sensitive files or conflict markers and require explicit confirmation before running git commit.

## When to Use

- Use when the user asks to prepare, draft, or create a git commit (e.g., “Make a commit”, “Prepare a commit message”, “Commit staged changes”).
- Use when the user wants safety checks before committing (e.g., “Scan for secrets before commit”).
- Do not use when the user requests cancel/stop the commit workflow (e.g., “Cancel commit”).

## How to Use

- Read and follow the repository policy in [`references/commit.md`](git-commit-helper/references/commit.md).
- Start immediately by executing read-only git inspections: `git status`, `git diff`, `git diff --cached`, `git log --oneline -n 3`.
- If there are staged files, limit all analysis and commit scope to staged files only; otherwise, analyze unstaged files.
- Scan the selected files for sensitive filenames (e.g., `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials*`, `secrets*`). If found, stop and require explicit confirmation.
- Check for merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`). If found, stop and instruct to resolve conflicts.
- Evaluate whether changes are unrelated. If unrelated, propose splitting into separate commits and ask for confirmation.
- Compose a Conventional Commit message using the rules in [`references/commit.md`](git-commit-helper/references/commit.md):
  - Header ≤50 characters, imperative mood, no trailing period.
  - Body wrapped at 72 characters when needed, include what changed + why.
  - Types limited to `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `style`, `build`, `ci`, `chore`, `revert`.
  - For breaking changes, use `!` after scope and include `BREAKING CHANGE:` in footer.
- Show the full proposed commit message and ask: “Create commit with this message? (yes/no)”.
- If the user says “yes”, run `git add` with explicit file list (never `git add .`), then commit via `git commit -F - <<'EOF' ... EOF` and show `git log --oneline -n 1`.
- If the user says “no”, ask whether to edit or cancel; never commit without re-proposing and receiving “yes”.
- If the user requests cancel/stop, end the workflow with no commands executed.

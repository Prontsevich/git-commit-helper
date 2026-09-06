---
name: git-commit-helper
description: Use when a user asks to prepare, draft, review, or execute a git commit, or to split pending changes into commits. Works in any agent harness (Claude Code, Codex, Cursor, Gemini, Hermes, OpenCode, Copilot).
---

# Git Commit Helper

Read `references/commit.md` before running commands.

## Locating the helper scripts

Commands run in the **workspace** (project) directory, never in the skill folder,
so helper scripts must be called by absolute path. Let `$SKILL_DIR` be the
directory that contains this `SKILL.md`:

- If your harness printed the skill's base directory when it loaded this file, that is `$SKILL_DIR`.
- Otherwise resolve it once with `scripts/find_skill_dir.sh` from any known install, or check the
  usual locations: `~/.agents/skills`, `~/.claude/skills`, `~/.codex/skills`, `~/.cursor/skills`,
  `~/.gemini/skills`, `~/.hermes/skills`, `~/.config/opencode/skills`, `~/.copilot/skills`,
  plus `.claude/skills` and `.agents/skills` inside the project. On Windows replace `~` with
  `%USERPROFILE%`.

Every command below is written as `python3 $SKILL_DIR/scripts/<name>.py`; substitute the real path.

Helpers (all print JSON, exit 0 on ok, 2 on findings, 1 on error):
- `build_commit_context.py` - staged/unstaged/untracked inventory
- `check_conflicts.py` - unresolved merge-conflict blocks
- `check_sensitive_files.py` - risky file names
- `check_secrets.py` - regex secret scan of added lines (`check_sensitive_regex_staged.py` is a compatibility alias)
- `propose_split.py` - draft multi-commit grouping by path and artifact kind
- `validate_commit_message.py` - message format gate (delegates to commitlint when the repo has one)

## Workflow Contract

1. Run read-only inspection first.
2. If staged files exist, scope analysis and commit to staged files only (`--source index`).
3. If no staged files exist, analyze unstaged tracked files and ask whether to include untracked files.
4. Include untracked files only after explicit user `yes` (`--include-untracked`).
5. If unresolved merge conflict markers are detected, require explicit user confirmation before continuing.
6. Run sensitive file-name checks in the selected scope; require explicit user confirmation if matches are found.
7. Run regex secret checks in the selected scope (`--source index|worktree`). If timeout occurs, continue with filename checks only after explicit user confirmation.
8. Propose a full English Conventional Commit message. Append the `Co-Authored-By` trailer your harness dictates (see **Co-Authored-By trailer**), then validate with `validate_commit_message.py`.
9. Request explicit `yes` or `no` for the full validated message before running `git commit`.
10. Never use `git add .`; always use explicit file paths.
11. If user requests cancel/stop, end workflow without running write commands.

## Commit Message Rules

- Header length: keep **<= 72 characters** by default. Up to **100** is allowed when it genuinely improves the description; the validator warns but does not block. Over 100 is an error: shorten it. Never pad a header just to fill space.
- Imperative mood in summary.
- No trailing period in summary.
- Body: **two lines by default**. Line one says **why** the change was needed, line two says briefly **what** changed. Omit the body entirely when the header already says it. Every limit here is a ceiling, never a target.
- Body lines: **<= 72 preferred**, up to **100 allowed** (the validator warns), **> 100 is an error**. Git trailers (`Co-Authored-By`, `Signed-off-by`, `BREAKING CHANGE`, ...) and lines containing URLs are exempt from the wrap entirely.
- Allowed types: `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `style`, `build`, `ci`, `chore`, `revert`, `merge`.
- `merge` is a local addition, not part of the Conventional Commits spec: a merge commit still wants a readable subject, and having no type that fits only teaches people to skip the check.
- For breaking changes: use `!` in header and add `BREAKING CHANGE:` footer.
- Keep commit messages in English only.
- **When the repo has a commitlint config, commitlint is the source of truth** for these format rules. See **commitlint / husky** below.

### What never goes in a body

The diff already shows files, functions and mechanics; the tracker or plan doc
holds the investigation. A body is for the reader of `git log`, not for the
author's notes. The validator warns on the usual leaks.

| Temptation | Reality |
|-----------|---------|
| "The root cause is interesting, worth recording" | It is. Record it in the task, not the commit. |
| "Listing the files makes review easier" | `git show --stat` lists them better and never goes stale. |
| "Three or four lines is still within the limit" | The limit is a ceiling. Two lines is the target. |
| "I should justify why I chose this approach" | If the header cannot carry it, the PR description can. |
| "The user asked for a detailed commit" | Ask what the reader of `git log` needs, then keep it to that. |

## Co-Authored-By trailer

Many harnesses require every commit the agent authors to end with a
`Co-Authored-By` trailer naming the model, e.g.:

```text
Co-Authored-By: <Model Name> <noreply@vendor.example>
```

Rules:
- Use the **exact string your harness or system prompt dictates** for the current session. Never invent one and never copy an example from these docs.
- Append it as the **last line**, after a blank line.
- If the harness dictates none, set `GIT_COMMIT_HELPER_COAUTHOR` in the environment to a default, or omit the trailer.
- The validator warns (never errors) when the trailer is missing; pass `--no-coauthor-check` when the harness does not want one.

## commitlint / husky

- `validate_commit_message.py` auto-detects a commitlint config (`commitlint.config.*`, `.commitlintrc*`, or a `commitlint` key in `package.json`). When one exists **and** commitlint is runnable via `npx`, the validator delegates format checks to commitlint (`"mode": "commitlint"` in its output) and layers only the project extras (ASCII-only, Co-Authored-By nudge, body-shape warnings) on top. The built-in rules above then act as documentation of the intended defaults, not a second gate.
- If a commitlint config exists but the tool is not installed, the validator falls back to built-in rules and emits a warning saying so.
- Pass `--no-commitlint` to force built-in validation regardless of repo config.
- **Never bypass git hooks.** If the repo uses husky (`.husky/` directory), do not pass `--no-verify` to `git commit`; let the `commit-msg`/`pre-commit` hooks run. A husky `commit-msg` hook typically runs commitlint again; that is expected and complements the pre-commit validation.

## Commit plan (before any `git commit`)

When changes touch **multiple layers or domains**, do not default to a single commit.
Run `propose_split.py` for a draft grouping, then read **Commit split strategy** and
**Scope selection** in `references/commit.md`, and propose a **multi-commit plan**
(message + explicit file list per commit). Wait for user approval.

Offer two options unless the user already chose:
1. **Minimal**: one source commit (+ optional separate commit for generated artifacts if applicable)
2. **Review-friendly**: infrastructure -> per-domain integration -> generated artifacts last

Execute commits **sequentially** in the approved order; re-run read-only inspection between commits if needed.

# Git commit reference

Details behind `SKILL.md`. Read only the section the current situation needs.

## Split plans

Split when the change spans unrelated domains, or shared infrastructure plus the
features that use it, or source plus generated artifacts. `preflight.py --split`
drafts a grouping by path and kind (`split.review_friendly`, `split.minimal`);
rename scopes and merge groups by hand.

Review-friendly order:

1. UI-only refactors, e.g. `refactor(<component>): ...`
2. Shared infrastructure, e.g. `feat(core): ...`
3. One commit per feature domain, its tests included, e.g. `feat(<domain>): ...`
4. Generated artifacts last, e.g. `chore(<generator>): ...`, never mixed with source

Offer the full plan (each header with its files) before the first commit. If the
user asks for one commit, use the minimal plan: one source commit, plus a
separate one for generated artifacts when present. Intermediate commits may be
temporarily inconsistent.

`commit.py` refuses when the index holds files outside the paths it is given,
because `git commit` takes the whole index. To split an already staged index,
unstage the later groups first (`git restore --staged -- <paths>`), then commit
group by group. Files in `partially_staged` lose their partial staging that
way; offer a single commit for them instead.

```text
refactor(dialogs): use computed for submit disabled state
feat(core): add hooks for store mutation callbacks
feat(<domain-a>): close create dialog via store onSuccess hook
chore(codegen): update generated artifacts after store changes
```

## Scope selection

Pick the scope from the changed paths and their responsibility. Avoid monorepo
project names, generic repo labels and catch-alls like `app`.

| Scope | Typical meaning |
|-------|-----------------|
| Feature or domain | the feature the change belongs to (its store, pages, components) |
| `core` / `shared` | cross-domain infrastructure |
| Layer or component | a specific shared layer when the change is limited to it |
| Tool or integration | match existing repo conventions |

One commit, one scope where possible.

## Passing the message

`--message` takes the whole text; in a POSIX shell a quoted heredoc keeps it
intact:

```bash
python3 "$SKILL_DIR/scripts/commit.py" --dry-run --message "$(cat <<'EOF'
fix(auth): refresh token before expiry

Sessions dropped when the token expired mid-request.
Refresh one minute before expiry.

Co-Authored-By: <exact trailer dictated by the harness>
EOF
)" src/auth/session.ts
```

Where heredocs are awkward (for example PowerShell), write the message to a
temporary file and pass `--file <path>` instead.

## Question tools

| Harness | Tool | Where the proposal goes |
|---------|------|-------------------------|
| Claude Code | `AskUserQuestion` | option `preview` |
| omp | `ask` | option `preview` |
| OpenCode | `question` | message before the call |
| Hermes | `clarify` | message before the call |
| Codex | `request_user_input` (CLI: Plan mode only) or `request_user_input_async` | message before the call |
| pi | none built in; an extension may add `question` | message before the call |

Other harnesses: use an equivalent tool if there is one, else the text prompts.
An async tool returns before the user answers: end the turn and act on the reply
when it arrives, never on the tool's return.

Ask about a finding as its own question with `Stop` (recommended) and
`Continue`. Continuing with conflict markers or sensitive files keeps them
listed in the commit proposal.

### Text prompts

Without a question tool, show the recommended proposal in full and ask exactly:

- `Create commit with this message? (yes/no)`
- `Create commit with this message, including the new files? (yes/no)`
- `Create these <N> commits in order? (yes/no)`
- `Edit message or cancel? (edit/cancel)` (after a bare `no`)
- `Sensitive files detected. Continue anyway? (yes/no)`
- `Conflict markers detected. Continue anyway? (yes/no)`
- `Secret scan timed out. Continue with filename checks only? (yes/no)`

Any reply other than `yes` or `no` is an edit or an alternative such as
"tracked only": apply it, re-validate, ask again.

## Checks and allowlist

- Sensitive file names: `.env*` (except `.env.example` and similar), keys and
  certificates, `*secret*`, `*credential*`, cloud and package-manager configs.
- Secret scan: only added lines of the selected scope (whole files for
  untracked), with a 2 second budget (`--timeout`). On timeout the filename
  check still ran; continue only after an explicit yes.
- Conflict markers: only real `<<<<<<<` ... `>>>>>>>` blocks; a lone `=======`
  is not a conflict.
- `.git-commit-helper-allow` at the repo root: one regex per line matched
  against a secret finding's excerpt, or `path:<glob>` to skip a file in both
  checks. Suppressions are counted, never silent. Never add an entry to hide a
  real secret; remove the secret instead.

Each check also runs alone (`check_conflicts.py`, `check_sensitive_files.py`,
`check_secrets.py`, `propose_split.py`, `validate_commit_message.py`), with
`--source index|worktree` and `--include-untracked`, for debugging or a harness
that cannot run `preflight.py`.

## commitlint and husky

- The validator detects `commitlint.config.*`, `.commitlintrc*` or a
  `commitlint` key in `package.json`. It runs `node_modules/.bin/commitlint`
  when installed, else `npx --no-install commitlint`, and reports
  `"mode": "commitlint"`. Its failures become validation errors.
- With a config but no runnable commitlint it falls back to the built-in rules
  and warns. `--no-commitlint` forces the built-in rules.
- Never pass `--no-verify`. A husky `commit-msg` hook re-running commitlint is
  expected; a hook failure comes back from `commit.py` as `commit_failed`.

## Locating the skill

If the harness did not print the skill's base directory, check the usual roots
for `git-commit-helper/SKILL.md`: `~/.agents/skills`, `~/.claude/skills`,
`~/.codex/skills`, `~/.cursor/skills`, `~/.gemini/skills`, `~/.hermes/skills`,
`~/.config/opencode/skills`, `~/.copilot/skills`, `~/.pi/agent/skills`,
`~/.omp/agent/skills`, and `.claude/skills` or `.agents/skills` in the project.
On Windows replace `~` with `%USERPROFILE%`.

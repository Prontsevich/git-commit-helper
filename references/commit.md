## Git Commit Policy

Follow this file as the single source of truth for commit behavior.

**Helper scripts:** Run from the workspace; call them by absolute path. `$SKILL_DIR` below is the directory containing `SKILL.md` (see **Locating the helper scripts** there).

## Required command sequence

1. Run read-only context collection first:
   - `python3 $SKILL_DIR/scripts/build_commit_context.py`
   - `git status`
   - `git diff`
   - `git diff --cached`
   - `git log --oneline -n 3`
2. Determine commit scope:
   - If staged files exist: use staged files only (`--source index`).
   - If no staged files exist: use unstaged tracked files (`--source worktree`).
   - Ask whether to include untracked files:
     - `Include untracked files in this commit? (yes/no)`
   - Include untracked files only after explicit `yes` and pass `--include-untracked`.
3. Run mandatory checks on selected files:
   - Conflict markers: `python3 $SKILL_DIR/scripts/check_conflicts.py --source <index|worktree> [--include-untracked]`
   - Sensitive filenames: `python3 $SKILL_DIR/scripts/check_sensitive_files.py --source <index|worktree> [--include-untracked]`
4. Run regex secret scan on selected scope:
   - `python3 $SKILL_DIR/scripts/check_secrets.py --source <index|worktree> [--include-untracked] --timeout 2.0`
   - If timeout happens, warn and continue with filename checks only after explicit `yes`.
5. Draft full commit message in English (Conventional Commits). Append the `Co-Authored-By` trailer your harness dictates as the last line after a blank line (see **Co-Authored-By trailer**).
6. Validate message before confirmation:
   - `python3 $SKILL_DIR/scripts/validate_commit_message.py --file <temp-file>`
   - The validator delegates to the repo's commitlint when configured and runnable (`"mode": "commitlint"`); otherwise it uses built-in rules (`"mode": "builtin"`).
   - If validation fails (`status` is `invalid`), revise and re-run validation until status is `ok`. Warnings do not block, but read them.
7. Show full proposal and ask exactly:
   - `Create commit with this message? (yes/no)`
8. On `yes`:
   - Run `git add` with explicit selected paths only.
   - Run `git commit -F <temp-file>` (never `--no-verify`).
   - Show `git log --oneline -n 1`.
9. On `no`:
   - Ask whether to edit or cancel.
   - If edit, update message, re-validate, and show the full proposal again.
10. On cancel/stop request:
   - End without write commands.

## Hard rules

1. Never run `git commit` without explicit `yes` to the full current message.
2. Never use `git add .` or wildcard add commands.
3. Never commit when there are no selected files.
4. If unresolved merge conflict markers are present, require explicit confirmation before proceeding.
5. Always warn and ask explicit confirmation when sensitive filenames are detected.
6. Always keep commit message text in English.
7. Always re-show full message after any edit request.
8. Always run the skill's `validate_commit_message.py` (absolute path under `$SKILL_DIR`) and require `status: ok` before confirmation.
9. Never run destructive commands (`git reset --hard`, `git clean`, `git push`, `git rebase`) unless user explicitly requests them.
10. Never bypass git hooks (`--no-verify`); let husky `commit-msg`/`pre-commit` hooks run.

## Conventional Commit rules

Template:

```text
type(scope): short summary

[optional body]

[optional footer / trailers]
Co-Authored-By: <Model Name> <noreply@vendor.example>
```

Rules:

- Header length: **≤ 72 preferred**, up to **100 allowed** (validator warns), **> 100 is an error**. Do not pad a header to fill space; do not truncate it into something unclear either.
- Use imperative mood.
- Do not end header with a period.
- Body: **two lines by default** — **why** first, then briefly **what**. Omit the body entirely when the header already says it. Every limit here is a ceiling, never a target: do not stretch a body to fill the allowance. Do not list files, function names, or technical details — the diff shows that. Do not narrate the bug mechanism, the investigation, or comparisons to sibling modules — that belongs in the tracker or plan doc.
- Body line length: **<= 72 preferred**, up to **100 allowed** (validator warns), **> 100 is an error** — tiered exactly like the header. Git trailers and URL-bearing lines are exempt from the wrap entirely.
- Allowed `type`: `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `style`, `build`, `ci`, `chore`, `revert`, `merge`.
- `merge` is a local addition, not part of the Conventional Commits spec: a merge commit still wants a readable subject, and having no type that fits only teaches people to skip the check.
- For breaking changes: include `!` in header and `BREAKING CHANGE:` footer.
- No ticket format is required.
- **When the repo has a commitlint config, commitlint's rules win** over the defaults above for header format/type/length — the validator enforces them for you.

## Co-Authored-By trailer

Most harnesses require every commit the agent authors to end with a
`Co-Authored-By` trailer naming the model, on its own line after a blank line:

```text
Co-Authored-By: <Model Name> <noreply@vendor.example>
```

Resolution order for the exact string:

1. The harness or system-prompt instruction in effect for the current session (always wins).
2. `GIT_COMMIT_HELPER_COAUTHOR` from the environment, if set.
3. Otherwise omit the trailer and pass `--no-coauthor-check` to the validator.

Never hardcode a model name from these docs. The validator emits a warning (not
an error) when the trailer is absent, so it is a nudge, not a gate.

## commitlint / husky policy

- `validate_commit_message.py` auto-detects commitlint config: `commitlint.config.{js,cjs,mjs,ts}`, `.commitlintrc`, `.commitlintrc.{json,yaml,yml,js,cjs,ts}`, or a `commitlint` key in `package.json`.
- When a config exists and commitlint resolves via `npx --no-install commitlint`, the validator runs commitlint over the message via stdin and reports `"mode": "commitlint"`. commitlint failures become validation errors with its raw output attached.
- When a config exists but commitlint is not installed, the validator falls back to built-in rules and warns that it did so.
- When no config exists, the built-in rules apply (`"mode": "builtin"`).
- `--no-commitlint` forces built-in validation regardless of repo config (escape hatch for debugging).
- Never pass `--no-verify` to `git commit`. If husky is present, its `commit-msg` hook usually re-runs commitlint — that redundancy is intentional.

## Scope selection

Pick scope from **changed paths and responsibility**, not from the repo or app package name.

**If the repository documents its own commit scopes** (e.g. in `CLAUDE.md`, a
`CONTRIBUTING`/commit-conventions doc, or a commitlint `scope-enum` rule), follow
those — they take precedence over the generic guidance here.

**Avoid as scope:** monorepo project names, generic repo labels, or a catch-all like `app`.

**Prefer:**

| Scope | Typical meaning |
|-------|-----------------|
| Feature / domain | the feature or domain the change belongs to (its store, pages, components) |
| `core` / `shared` | cross-domain infrastructure (shared utils, HTTP helpers, common patterns) |
| Layer / component | a specific shared layer or component when the change is scoped to it |
| Tool / integration | match existing repo conventions when obvious |

Keep generated artifacts under their own scope (e.g. `chore(<generator>):`) rather than mixing them with source.

One commit = one scope when possible. Mixed domains in one commit only for a truly atomic cross-cutting fix the user requested as a single unit.

## Commit split strategy

Use when a task spans **UI refactors + shared infra + multiple feature domains + generated files**.

### Default: review-friendly order

1. **UI-only refactors** — e.g. `refactor(<component>): …` (no store/API behavior change)
2. **Shared infrastructure** — e.g. `feat(core): …` (new types/utils used by multiple domains)
3. **Per-feature integration** — one commit per domain, e.g. `feat(<domain-a>): …`, `feat(<domain-b>): …`
   (store + page/component for that domain together)
4. **Generated artifacts last** — e.g. `chore(<generator>): …`; never mix with source in the same commit

### Rules

- Start from `python3 $SKILL_DIR/scripts/propose_split.py --source <index|worktree> [--include-untracked]`; it groups the selected files by top-level path and artifact kind (source, tests, docs, config, generated) and prints a draft plan. Rename scopes and merge groups by hand.
- Propose the **full plan** (each commit: header, files) before the first `git add`.
- Do not combine unrelated domains in one commit.
- Intermediate commits may be temporarily inconsistent; that is OK for bisect/review.
- If the user asks for one commit, use **minimal** plan and say what review-friendly would look like.

### Example

```text
refactor(dialogs): use computed for submit disabled state
feat(core): add hooks for store mutation callbacks
feat(<domain-a>): close create dialog via store onSuccess hook
feat(<domain-b>): close create dialog via store onSuccess hook
chore(codegen): update generated artifacts after store changes
```

## Secret detection policy

Run two tiers:

1. Fast filename policy scan:
   - Detect risky names and extensions like `.env*`, `*.pem`, `*.key`, `id_rsa`, `*secret*`, `*credential*`.
   - Run on selected scope (staged or unstaged, with optional untracked).
   - If matched, stop for confirmation.
2. Regex content scan:
   - Scan only added lines from selected scope:
     - staged scope: staged diff (`--source index`)
     - unstaged scope: worktree diff (`--source worktree`)
     - included untracked files: full file content as added lines (`--include-untracked`)
   - Use short timeout (default 2 seconds) to avoid slow commits.
   - If timeout occurs, state that regex scan timed out and ask whether to continue.
3. Allowlist (`.git-commit-helper-allow` at the repo root):
   - One regex per line matched against a finding's excerpt, or `path:<glob>` to skip a file in both tiers.
   - Both scripts report `suppressed_by_allowlist`; mention a non-zero count in the confirmation summary.
   - Never add an entry to silence a real secret; the fix is to remove the secret.

## Conflict marker policy

Search selected files for unresolved merge conflict blocks:

- `<<<<<<<`
- `=======`
- `>>>>>>>`

Treat only real marker blocks as conflicts. If any are found, stop and ask user to resolve them first.
If user explicitly approves override, continue with extra caution and keep checks/results visible in the confirmation summary.

## Confirmation text

Use these exact prompts to keep behavior deterministic:

- `Include untracked files in this commit? (yes/no)`
- `Create commit with this message? (yes/no)`
- `Edit message or cancel? (edit/cancel)`
- `Sensitive files detected. Continue anyway? (yes/no)`
- `Conflict markers detected. Continue anyway? (yes/no)`
- `Regex secret scan timed out. Continue with filename checks only? (yes/no)`

## Commit execution

Use temp-file commit message flow:

```bash
tmp_msg="$(mktemp)"
cat >"$tmp_msg" <<'EOF'
<FULL COMMIT MESSAGE>

Co-Authored-By: <exact trailer dictated by the harness>
EOF
python3 $SKILL_DIR/scripts/validate_commit_message.py --file "$tmp_msg"
git add <explicit path 1> <explicit path 2>
git commit -F "$tmp_msg"
rm -f "$tmp_msg"
```

Ensure `EOF` is on its own line with no trailing text.

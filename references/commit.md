## Git Commit Policy

Follow this file as the single source of truth for commit behavior.

## Required Command Sequence

1. Run read-only context collection first:
   - `python3 scripts/build_commit_context.py`
   - `git status`
   - `git diff`
   - `git diff --cached`
   - `git log --oneline -n 3`
2. Determine commit scope:
   - If staged files exist: use staged files only.
   - If no staged files exist: analyze unstaged tracked files; ask user whether to include untracked files.
3. Run mandatory checks on selected files:
   - `python3 scripts/check_conflicts.py`
   - `python3 scripts/check_sensitive_files.py`
4. Run regex secret scan only on staged diff:
   - `python3 scripts/check_sensitive_regex_staged.py --timeout 2.0`
   - If timeout happens, warn and continue with filename checks only.
5. Draft full commit message in English (Conventional Commits).
6. Show full proposal and ask exactly:
   - `Create commit with this message? (yes/no)`
7. On `yes`:
   - Run `git add` with explicit paths only.
   - Write commit message to a temporary file.
   - Run `git commit -F <temp-file>`.
   - Show `git log --oneline -n 1`.
8. On `no`:
   - Ask whether to edit or cancel.
   - If edit, update message and show proposal again.
9. On cancel/stop request:
   - End without write commands.

## Hard Rules

1. Never run `git commit` without explicit `yes` to the full current message.
2. Never use `git add .` or wildcard add commands.
3. Never commit when there are no selected files.
4. Never proceed when merge conflict markers are present.
5. Always warn and ask explicit confirmation when sensitive filenames are detected.
6. Always keep commit message text in English.
7. Always re-show full message after any edit request.
8. Never run destructive commands (`git reset --hard`, `git clean`, `git push`, `git rebase`) unless user explicitly requests them.

## Conventional Commit Rules

Template:

```text
type(scope): short summary

[optional body]
[optional footer]
```

Rules:

- Header length <= 50.
- Use imperative mood.
- Do not end header with a period.
- Wrap body lines to <= 72.
- Allowed `type`: `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `style`, `build`, `ci`, `chore`, `revert`.
- For breaking changes: include `!` in header and `BREAKING CHANGE:` footer.
- No ticket format is required.

## Secret Detection Policy

Run two tiers:

1. Fast filename policy scan:
   - Detect risky names and extensions like `.env*`, `*.pem`, `*.key`, `id_rsa`, `*secret*`, `*credential*`.
   - If matched, stop for confirmation.
2. Regex content scan on staged diff:
   - Scan only added lines from `git diff --cached`.
   - Use short timeout (default 2 seconds) to avoid slow commits.
   - If timeout occurs, state that regex scan timed out and ask whether to continue.

## Conflict Marker Policy

Search selected files for:

- `<<<<<<<`
- `=======`
- `>>>>>>>`

If any marker is found, stop and ask user to resolve conflicts first.

## Confirmation Text

Use these exact prompts to keep behavior deterministic:

- `Create commit with this message? (yes/no)`
- `Edit message or cancel? (edit/cancel)`
- `Sensitive files detected. Continue anyway? (yes/no)`
- `Regex secret scan timed out. Continue with filename checks only? (yes/no)`

## Commit Execution

Use temp-file commit message flow:

```bash
tmp_msg="$(mktemp)"
cat >"$tmp_msg" <<'EOF'
<FULL COMMIT MESSAGE>
EOF
git commit -F "$tmp_msg"
rm -f "$tmp_msg"
```

Ensure `EOF` is on its own line with no trailing text.

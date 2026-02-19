## 🔒 Safety & Execution Policy

1. **NEVER** run destructive commands (`git push`, `git reset --hard`, `git rebase`, `git clean`, etc.) without explicit confirmation.

2. **ALWAYS** inspect with read-only commands: `git status`, `git diff`, `git diff --cached`, `git log --oneline -n 3`. **DO NOT** display command output to the user — use it internally for analysis only.

3. **DO NOT** commit if no changes.

4. **ONLY** execute `git commit` after "yes" to full proposal.

5. **ALWAYS** show complete message before confirmation.

6. **CRITICAL**: When using here-documents with `<<'EOF'`, ensure no text (including comments, explanations, whitespace or newline) follows the `EOF`.
    Make sure the EOF is on its own line with no additional content.
    This is not just a formatting preference - it's a strict bash requirement that will break the commit command.

7. **All code, commands, commits, docs in English.**

---

## 🚨 Mandatory Checks

- ✅ No conflicts (no `<<<<<<<`, `=======`, `>>>>>>>` in files).

- ✅ No sensitive files (e.g., `.env`, `*.pem`, `*.key`, `id_rsa`, `credentials*`, `secrets*`); warn and require confirmation.

- ✅ Changes grouped; suggest splitting if unrelated (e.g., bug fix + refactor).

- ✅ At least one changed file.

---

## 📋 Format: Conventional Commits

```text
type(scope): short summary
[optional body: what changed + why]
[optional footer: Closes #123, BREAKING CHANGE: ...]
```

### Rules:

- **Header**: ≤50 characters, imperative mood (`add`, not `added`), no trailing period.

- **Body**: Wrap at 72 characters per line.

- **Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `perf`, `style`, `build`, `ci`, `chore`, `revert`.

- **Breaking changes**: Use `!` after scope (e.g., `feat(api)!: drop Node 14`) AND `BREAKING CHANGE: ...` in footer.

- **Scope**: Lowercase, no spaces (e.g., `auth`, `ui/layout`, `deps`).

### Example:

```text
feat(auth): add JWT validation
- Implemented token parsing with expiry checks
- Added tests for invalid/expired tokens
BREAKING CHANGE: requires new env var JWT_SECRET
```

---

## 🎯 Workflow

**IMPORTANT**: Upon receiving this instruction, **IMMEDIATELY** begin analyzing changes and preparing the commit. Do not wait for additional prompts — start the workflow right away.

1. **Check state**: Run `git status`. List modified/staged/untracked. If untracked: "Add new files [list]? (yes/no)"

2. **Scan for secrets**: If matches: "⚠️ Sensitive files detected: [files]. Do not commit credentials! Continue? (yes/no)"

3. **Check for conflicts**: If markers found: "Merge conflicts detected. Resolve them first."

4. **Evaluate granularity**: If unrelated changes: "Changes seem unrelated. Split into separate commits? (yes/no)"

5. **Compose message**: Simple → header only; Complex → add body (what + why). Aanalyze available context (open files, selected code, file diffs) to understand changes and suggest appropriate type/scope/summary.

6. **Show full proposal**:

```text
📋 Proposing commit:
[COMPLETE COMMIT MESSAGE]
Create commit with this message? (yes/no)
```

7. **Handle response and execute**:

    - If "yes": Run `git add [explicit file list]`; then `git commit -F - <<'EOF' [COMPLETE MESSAGE] EOF`. Show `git log --oneline -n 1` to confirm.

    - If "no": "Why not? Edit message or cancel? (edit/cancel)" If "edit": Request changes, revise, and **ALWAYS show the updated proposal again** with "Create commit with this message? (yes/no)" — **NEVER commit without showing the updated proposal and getting confirmation**.

    - If user requests any changes (edit message, split commits, modify scope, etc.): Make the requested changes and **ALWAYS show the updated proposal again** with "Create commit with this message? (yes/no)" — **NEVER commit immediately after making changes without showing the proposal and getting confirmation**.

    - If "cancel": Stop.

    - If other response: "Please respond with 'yes' or 'no'."

    - If any command fails (e.g., permissions error, Git issue): "Error: [description]. Retry or cancel? (retry/cancel)". Do not proceed until fixed.

---

## ⚠️ Common Mistakes to Avoid

- Vague summaries (`"update"`, `"fix stuff"`)

- Committing unrelated changes together

- Ignoring untracked or sensitive files

- Skipping confirmation before `git commit`

- Using non-English in commits/code

- Exceeding line limits (50 header, 72 body)

- Displaying raw output of `git status`, `git diff`, `git log` commands to the user

- Committing immediately after making changes to the message without showing the updated proposal and getting confirmation

---

> 💡 Never use `git add .` — explicit files only. Never assume intent — always confirm. Use available IDE context (open files, selected code, diffs) to better understand changes when composing commit messages.

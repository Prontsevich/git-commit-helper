# git-commit-helper

An agent skill that turns "commit this" into a safe, reviewable workflow:
staged-first scoping, secret and conflict checks, Conventional Commits with a
validator, and an explicit confirmation before anything is written.

The skill is harness-agnostic. The same folder works in Claude Code, Codex,
Cursor, Gemini CLI, Hermes, OpenCode and Copilot; only the install location
differs.

## Install

Clone the repo once, then link it into every harness you use:

```bash
git clone https://github.com/Prontsevich/git-commit-helper.git ~/Projects/git-commit-helper
cd ~/Projects/git-commit-helper
./install.sh              # symlink into every harness whose home dir exists
./install.sh claude cursor  # or name the targets
./install.sh --copy codex   # copy for hosts that do not follow symlinks
./install.sh --check        # show drift between the repo and each install
```

Targets and their paths:

| Target | Path |
|--------|------|
| `claude` | `~/.claude/skills/git-commit-helper` |
| `cursor` | `~/.cursor/skills/git-commit-helper` |
| `codex` | `~/.codex/skills/git-commit-helper` |
| `agents` | `~/.agents/skills/git-commit-helper` (shared by Codex, Copilot, Gemini) |
| `gemini` | `~/.gemini/skills/git-commit-helper` |
| `hermes` | `~/.hermes/skills/git-commit-helper` |
| `opencode` | `~/.config/opencode/skills/git-commit-helper` |
| `copilot` | `~/.copilot/skills/git-commit-helper` |

A symlink keeps every harness on the repo's current state. An existing plain
directory is only replaced with `--force`; it is moved to
`~/.git-commit-helper-backups/<target>-<timestamp>` first (never left beside
the skill, where a harness would load it as a duplicate).

Requirements: `git`, `python3` (3.10+). `commitlint` via `npx` is used when the
target repo has a config; otherwise built-in rules apply.

## What the agent does

1. Reads the pending changes (`build_commit_context.py`) and picks the scope: staged files if any, else unstaged tracked files, untracked only after a `yes`.
2. Runs `check_conflicts.py`, `check_sensitive_files.py` and `check_secrets.py` on that scope and stops for confirmation on any finding.
3. For changes spanning several domains, drafts a multi-commit plan with `propose_split.py` and asks which plan to use.
4. Writes a Conventional Commit message, appends the `Co-Authored-By` trailer the harness dictates, validates it with `validate_commit_message.py`.
5. Shows the full message, asks `Create commit with this message? (yes/no)`, and only then runs `git add <explicit paths>` and `git commit -F`.

Policy details live in `SKILL.md` and `references/commit.md`.

## Configuration

- `GIT_COMMIT_HELPER_COAUTHOR`: default trailer used in validator hints when the harness dictates none.
- `.git-commit-helper-allow` at the target repo root: one regex per line matched against a secret finding's excerpt, or `path:<glob>` to skip a file in both the name check and the secret scan. Suppressions are counted in the output, never silent.
- A commitlint config in the target repo takes precedence over the built-in format rules.

## Development

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m unittest tests.test_commit_helper_scripts.ValidateCommitMessageTestCase
```

Scripts share `scripts/gitscope.py` for scope resolution. Each script prints
JSON and exits `0` (ok), `2` (findings), `1` (error); the secret scanner exits
`3` on timeout.

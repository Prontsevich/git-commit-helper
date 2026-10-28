# git-commit-helper

An agent skill that turns "commit this" into a safe, reviewable workflow:
staged-first scoping, secret and conflict checks, Conventional Commits with a
validator, and an explicit confirmation before anything is written.

The skill is harness-agnostic. The same folder works in Claude Code, Codex,
Cursor, Gemini CLI, Hermes, OpenCode, Copilot, pi and omp; only the install
location differs.

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
| `agents` | `~/.agents/skills/git-commit-helper` (shared by Codex, Copilot, Gemini, pi, omp) |
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

1. Runs `preflight.py` once: it picks the scope (staged files if any, else unstaged tracked files with untracked files as an option), lists the files, and runs the conflict, sensitive-filename and secret checks. Any finding stops for confirmation. `--split` adds a draft multi-commit plan.
2. Reads the scoped diff and writes a Conventional Commit message with the `Co-Authored-By` trailer the harness dictates, unless the user opted out.
3. Checks it with `commit.py --dry-run`: message validation (commitlint when the repo has it) and a scope check.
4. Shows every full message and asks one question (the harness's question dialog when it has one, else a `(yes/no)` prompt).
5. On approval runs `commit.py` again without `--dry-run`, which stages the explicit paths and commits with hooks enabled.

Policy details live in `SKILL.md` and `references/commit.md`.

## Configuration

- `GIT_COMMIT_HELPER_COAUTHOR`: default trailer used in validator hints when the harness dictates none. Set it to `none` to never add a trailer: this overrides the harness, and the validator rejects a message that still has one.
- `.git-commit-helper-allow` at the target repo root: one regex per line matched against a secret finding's excerpt, or `path:<glob>` to skip a file in both the name check and the secret scan. Suppressions are counted in the output, never silent.
- A commitlint config in the target repo takes precedence over the built-in format rules.

## Development

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m unittest tests.test_commit_helper_scripts.ValidateCommitMessageTestCase
```

Scripts share `scripts/gitscope.py` for scope resolution. `preflight.py` and
`commit.py` compose the single-purpose check scripts, which stay runnable on
their own. Each script prints JSON and exits `0` (ok), `2` (findings), `1`
(error); `preflight.py` and `check_secrets.py` exit `3` on a secret-scan timeout.

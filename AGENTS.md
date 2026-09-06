# AGENTS.md

Guidance for agentic coding assistants working in this repo.

## What this repo is

An agent skill: `SKILL.md` (entry point), `references/commit.md` (policy),
`scripts/*.py` (deterministic helpers), `tests/` (unit tests), `install.sh`
(links the skill into agent harnesses). Python 3.10+ standard library only; no
package manager, no third-party dependencies.

## Build, lint, test

- Syntax check: `python3 -m py_compile scripts/*.py tests/*.py`
- All tests: `python3 -m unittest discover -s tests -p 'test_*.py'`
- One module: `python3 -m unittest tests.test_commit_helper_scripts`
- One case: `python3 -m unittest tests.test_commit_helper_scripts.ValidateCommitMessageTestCase.test_header_tiers`
- Installer dry run: `sh install.sh --check`

CI (`.github/workflows/test.yml`) runs the same on Linux, macOS and Windows.

## Conventions

- All code, comments, commit messages and docs in English.
- Scripts: shebang, executable bit, `argparse`, JSON on stdout, exit `0` ok / `2` findings / `1` error. Reuse `scripts/gitscope.py` for scope resolution instead of copying git helpers.
- Every behavior change to a script comes with a test in `tests/test_commit_helper_scripts.py` (write the failing test first).
- Docs must stay harness-neutral: refer to `$SKILL_DIR`, never to `~/.claude/...` or another harness path; never hardcode a model name in a trailer example.
- Markdown: ATX headings, `-` bullets, fenced blocks with a language tag, sentence-case headings.
- Keep `SKILL.md` short; long reference material goes to `references/`.

## Commits

Follow `SKILL.md` and `references/commit.md`; they apply to this repo too.
Never use `git add .`. Never commit `.env*`, keys or credentials.

## Do not

- Edit an installed copy under `~/.claude/skills` or similar; edit the repo and re-run `install.sh` (symlinked installs need no refresh).
- Add per-harness forks of `SKILL.md`.
- Overwrite user changes without being asked.

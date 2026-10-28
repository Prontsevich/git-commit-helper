---
name: git-commit-helper
description: Use when a user asks to prepare, draft, review, or execute a git commit, or to split pending changes into several commits.
---

# Git commit helper

Inspect, draft, confirm, commit. The scripts do the deterministic part (scope,
safety checks, validation, staging); you read the change, write the message and
talk to the user. Nothing is written to git before the user approves.

## Setup

Run commands from the workspace and call scripts by absolute path. `$SKILL_DIR`
is the directory containing this file: the base directory your harness printed
when it loaded the skill, or the output of `sh <any install>/scripts/find_skill_dir.sh`.
Scripts print JSON and exit `0` ok, `2` findings, `1` error.

## Workflow

1. **Inspect**: `python3 $SKILL_DIR/scripts/preflight.py` (add `--split` when the
   files span several domains or the user wants a split).
   - Scope is staged-first: only the staged files if any are staged; otherwise
     unstaged tracked files, with `untracked` files offered as an option.
   - `no_changes`: say so and stop.
   - `findings` or `timeout`: ask about each kind (conflict markers, sensitive
     files, secrets, scan timeout) with `Stop` / `Continue` before going on.
     Mention a non-zero `suppressed_by_allowlist`.
   - `partially_staged`: the commit takes the staged version; tell the user.
2. **Read the change** with `diff_command` from the output. For a large diff use
   `files[].added/deleted` to read file by file and skip lockfiles and generated
   output. `recent_subjects` shows the repo's style.
3. **Draft and check**:
   `python3 $SKILL_DIR/scripts/commit.py --dry-run --message "<message>" <paths>`.
   Paths are the files from preflight, plus untracked ones only in the option
   that offers them. Revise until `status` is `ok`; read the warnings.
4. **Confirm** with one question (see **Confirmation**).
5. **Commit** on approval: the same command without `--dry-run`. It stages the
   explicit paths, commits with hooks enabled and prints the new commit. For a
   plan, one call per commit in order; on `commit_failed`, stop, report what was
   committed with the hook output, and ask once about the rest.

On cancel or stop at any point, end without write commands. Never use
`git add .`, `--no-verify`, or `reset`/`clean`/`push`/`rebase`/`--amend` unless
the user asks.

## Commit message

- Conventional Commits in English ASCII: `type(scope): summary`, imperative
  mood, no trailing period. Types: `feat`, `fix`, `refactor`, `docs`, `test`,
  `perf`, `style`, `build`, `ci`, `chore`, `revert`, `merge`. Header up to 72
  characters, 100 only when it clearly reads better.
- Scope names the domain or layer the paths belong to, never the repo name. Repo
  conventions (CLAUDE.md, CONTRIBUTING, a commitlint `scope-enum`) win.
- Body: two lines by default, why the change was needed and then what changed.
  Drop it when the header already says it. Limits are ceilings, not targets.
- Breaking change: `!` in the header and a `BREAKING CHANGE:` footer.
- Last line, after a blank line: the exact `Co-Authored-By` trailer your harness
  or system prompt dictates. If none is dictated, use `GIT_COMMIT_HELPER_COAUTHOR`
  when set, else omit it and pass `--no-coauthor-check`. Never copy a name from
  these docs.
- When the repo has a commitlint config, the validator runs it and its rules win.

### What never goes in a body

The diff shows files, functions and mechanics; the tracker or plan doc holds the
investigation. The body is for the reader of `git log`.

| Temptation | Reality |
|-----------|---------|
| "The root cause is interesting, worth recording" | It is. Record it in the task, not the commit. |
| "Listing the files makes review easier" | `git show --stat` lists them better and never goes stale. |
| "Three or four lines is still within the limit" | The limit is a ceiling. Two lines is the target. |
| "I should justify why I chose this approach" | If the header cannot carry it, the PR description can. |
| "The user asked for a detailed commit" | Ask what the reader of `git log` needs, then keep it to that. |

## Confirmation

Show every full message with its file list, new files marked `(new)`, then ask
one question, through the harness's question tool when it has one (Claude Code:
`AskUserQuestion`, with the proposal in the option `preview`). At most 3
options, recommended first:

| Situation | Options |
|-----------|---------|
| One commit | `Commit`, `Cancel` |
| New files present | `Commit with new files`, `Tracked only`, `Cancel` |
| Split plan | `Commit all <N>`, `Single commit`, `Cancel` |

- One approval covers every message the chosen option showed in full.
- A free-form answer is an edit: apply it, re-run `--dry-run`, ask again.
- A dismissed question, an empty answer or an option the harness picked itself
  means no. Only an explicit commit option allows the commit.

## When to read `references/commit.md`

- Split plans: ordering, scope selection, splitting an already staged index.
- Another harness's question tool, async tools, or plain-text prompts.
- Allowlist, commitlint and husky details; running the checks one by one.

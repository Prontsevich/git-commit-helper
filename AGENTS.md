# AGENTS.md

Guidance for agentic coding assistants working in this repo.

Repository snapshot
- Primary content: skill documentation plus deterministic helper scripts.
- Files of interest: `SKILL.md`, `references/commit.md`, `scripts/*.py`,
  `tests/test_commit_helper_scripts.py`.
- No package build system detected.

Authoritative rules to include
- Cursor rules: none found (`.cursor/rules/` or `.cursorrules`).
- Copilot rules: none found (`.github/copilot-instructions.md`).
- If such files appear later, treat them as highest priority.

Language and tone
- All code, commands, and docs in English.
- Prefer clear, concise, instructional text.

Build, lint, test
- No build configuration detected (no `package.json`, `pyproject.toml`,
  `go.mod`, `Cargo.toml`, or `Makefile`).
- No dedicated lint tool is configured.
- Validate Python syntax:
  - `python3 -m py_compile scripts/*.py tests/test_commit_helper_scripts.py`
- Run tests:
  - `python3 -m unittest discover -s tests -p 'test_*.py'`

Running a single test
- Run one test module:
  - `python3 -m unittest tests.test_commit_helper_scripts`
- Run one test case:
  - `python3 -m unittest tests.test_commit_helper_scripts.ScriptTestCase.test_validate_commit_message_script`

Detecting tooling
- Check for `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`,
  `Makefile`, or `justfile` before writing commands.
- Prefer repo-specific scripts over global defaults.

Project structure
- Root: skill entry docs and workflow policy.
- `scripts/`: deterministic git workflow and validation helpers.
- `tests/`: unit tests for helper scripts.
- `references/`: policy and reference docs.

Code style overview (docs-first repo)
- Prefer Markdown with short paragraphs and bullet lists.
- Use headings to structure intent; avoid overly deep nesting.
- Keep line length readable; wrap long sentences.
- Use backticks for file paths, commands, and inline literals.
- Avoid emoji and excessive emphasis unless present in existing docs.

Formatting rules
- Use ATX headings (`#`, `##`, `###`).
- Separate sections with a blank line.
- Use `-` for bullet lists.
- Keep lists consistent within a section.
- Prefer sentence case for headings.
- Use fenced code blocks with a language tag.

Imports
- If you add code, prefer explicit imports over wildcard imports.
- Keep imports grouped: standard library, third-party, local.
- Remove unused imports.

Types and typing
- If adding typed languages, prefer strict settings.
- For TypeScript, avoid `any` unless required; use explicit interfaces.
- For Python, add type hints for public functions.
- For Go, follow `gofmt` and standard types.

Naming conventions
- Files: lowercase with hyphens or underscores, consistent with existing names.
- Directories: lowercase, descriptive.
- Functions: verbs that describe behavior.
- Types/classes: PascalCase.
- Constants: UPPER_SNAKE_CASE.

Error handling
- Handle errors explicitly; do not ignore returned errors.
- Include actionable context in error messages.
- Avoid panics/exceptions for expected failure paths.
- If scripts are added, exit non-zero on failure.

Documentation conventions
- State purpose before procedure.
- Provide prerequisites when a step depends on tools.
- Use numbered lists for ordered steps.
- Keep examples minimal and correct.
- Use absolute or repo-relative paths consistently.

Commit and git workflow
- Follow `references/commit.md` when preparing commits.
- Use Conventional Commits with 50/72 rules.
- Never commit sensitive files (`.env`, `*.pem`, `*.key`, etc.).
- Never use `git add .`; list files explicitly.

Agent workflow guidance
- Read relevant docs before proposing changes.
- Avoid speculative instructions not grounded in repo content.
- Update documentation if behavior or tooling changes.
- Do not overwrite user changes unless explicitly requested.

If adding new tooling
- Add a section named "Build, lint, test" with exact commands.
- Include how to run a single test.
- Include how to run formatting, if applicable.
- Update any references to new config files.

If adding scripts
- Document script purpose and usage in `scripts/`.
- Use POSIX-compatible shell unless a different runtime is required.
- Add a shebang and keep scripts executable.
- Validate input and fail fast.

If adding code
- Keep modules small and cohesive.
- Prefer pure functions where practical.
- Avoid global state.
- Add minimal unit tests for new behavior.
- Update docs to match behavior.

Security and safety
- Do not add secrets to the repo.
- Keep credentials in local environment variables or secret stores.
- Redact sensitive data in examples.

File additions
- New files should include a brief description in related docs.
- Keep naming consistent with existing patterns.

Review checklist for changes
- Does the change align with `SKILL.md` and `references/commit.md`?
- Are new instructions accurate and verifiable?
- Are examples runnable or clearly marked as illustrative?

Known limitations
- No package manager/test runner config file exists; Python stdlib tools are used directly.
- Secret regex heuristics are intentionally conservative and may require user override.

Maintenance
- Revisit this file when project structure changes.
- Keep this file around 150 lines to remain readable.

Contact/ownership
- Not specified; leave questions in PR/issue if added later.

Appendix: key files
- `SKILL.md`: skill purpose and usage.
- `references/commit.md`: commit safety and formatting rules.

End

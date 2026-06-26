# Commands

All commands accept `--root` to operate on a specific project root:

```bash
codemate --root /path/to/repo status
```

## `codemate init`

Creates the default project contract and local harness files.

```bash
codemate init
codemate init --force
```

Creates:

```text
team.yml
.team/prompts/
.team/schemas/
.team/runs/
docs/team.md
```

It also updates `.gitignore` with:

```text
.team/runs/
.team/lock.json
```

Use `--force` only when you intentionally want to overwrite generated config,
prompts, schemas, and the generated project docs.

## `codemate doctor`

Checks that configured agent commands exist and that simple command-group
executables can be found.

```bash
codemate doctor
codemate doctor --flow plan_implement_review_test
```

Empty command groups are warnings, not failures. This allows a project to
bootstrap before test commands are configured.

## `codemate run`

Runs a task through the configured workflow.

```bash
codemate run "Add rate limiting to login"
codemate run --file task.md
codemate run --flow codex_heavy "Fix auth tests"
```

The default config requires a clean worktree before starting. This prevents a
run from mixing agent changes with unrelated user edits.

## `codemate status`

Shows the latest run status or a specific run.

```bash
codemate status
codemate status --run-id 2026-06-26T10-15-00-123456
```

## `codemate logs`

Prints logs or outputs recorded for a run.

```bash
codemate logs
codemate logs --step implement
codemate logs --run-id 2026-06-26T10-15-00-123456
```

Agent steps prefer raw logs. Command steps print their command log.

## `codemate diff`

Prints the current git diff.

```bash
codemate diff
```

This uses git directly. It does not trust agent summaries.

## `codemate accept`

Accepts the latest run.

```bash
codemate accept
codemate accept --commit
codemate accept --commit --message "Fix checkout test"
```

Without `--commit`, this only acknowledges the run and leaves changes in the
working tree. With `--commit`, it commits non-`.team/` changed files.

## `codemate reset`

Restores source files recorded in the latest run state.

```bash
codemate reset
codemate reset --run-id 2026-06-26T10-15-00-123456
```

This is scoped to files recorded in the run state and excludes `.team/`
artifacts.

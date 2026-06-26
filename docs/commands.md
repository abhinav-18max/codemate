# Commands

All commands accept `--root` to operate on a specific project root:

```bash
team --root /path/to/repo status
```

## `team init`

Creates the default project contract and local harness files.

```bash
team init
team init --force
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

## `team doctor`

Checks that configured agent commands exist and that simple command-group
executables can be found.

```bash
team doctor
team doctor --flow plan_implement_review_test
```

Empty command groups are warnings, not failures. This allows a project to
bootstrap before test commands are configured.

## `team run`

Runs a task through the configured workflow.

```bash
team run "Add rate limiting to login"
team run --file task.md
team run --flow codex_heavy "Fix auth tests"
```

The default config requires a clean worktree before starting. This prevents a
run from mixing agent changes with unrelated user edits.

## `team status`

Shows the latest run status or a specific run.

```bash
team status
team status --run-id 2026-06-26T10-15-00-123456
```

## `team logs`

Prints logs or outputs recorded for a run.

```bash
team logs
team logs --step implement
team logs --run-id 2026-06-26T10-15-00-123456
```

Agent steps prefer raw logs. Command steps print their command log.

## `team diff`

Prints the current git diff.

```bash
team diff
```

This uses git directly. It does not trust agent summaries.

## `team accept`

Accepts the latest run.

```bash
team accept
team accept --commit
team accept --commit --message "Fix checkout test"
```

Without `--commit`, this only acknowledges the run and leaves changes in the
working tree. With `--commit`, it commits non-`.team/` changed files.

## `team reset`

Restores source files recorded in the latest run state.

```bash
team reset
team reset --run-id 2026-06-26T10-15-00-123456
```

This is scoped to files recorded in the run state and excludes `.team/`
artifacts.

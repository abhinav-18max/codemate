# Commands

All commands accept `--root` to operate on a specific project root:

```bash
codemate --root /path/to/repo status
```

## `codemate` (interactive session)

Running `codemate` with no command (or `codemate chat`) starts an interactive
session, like a REPL. Type a task at the prompt to run it through the active
flow; each step streams live. Slash commands inspect and manage the result
without leaving the session:

```text
codemate› Add rate limiting to login
● plan  (claude · read_only)
  │ ...
  ✓ DONE · 3 file(s) changed

codemate› /diff
codemate› /accept commit "Add login rate limiting"
codemate› /exit
```

Available slash commands: `/help`, `/status`, `/diff`, `/logs [step]`,
`/agents`, `/steps`, `/set`, `/unset`, `/accept [commit <msg>]`, `/reset`,
`/flow [name]`, `/clear`, `/exit`.

`/agents` and `/steps` show the provider/model/effort each agent and step will
use. `/set <target> <key> <value>` tunes them on the fly, where `<target>` is
an agent name (affects every step using it) or a step id (an override for just
that step):

```text
codemate› /set review model sonnet     # cheaper model for the review step only
codemate› /set codex effort low        # lower effort for all codex steps
codemate› /steps                       # confirm the effective settings
codemate› /unset review model          # drop the per-step override
```

Settable keys: `model`, `effort` (alias `reasoning_effort`), `provider`,
`sandbox`, `output_format`, `command`, `timeout_seconds`. Changes apply to
subsequent runs in this session; they are not written back to `team.yml`.

`chat` accepts `--flow`, `--quiet`, and `--no-color`. Because each task runs on
its own branch and leaves changes in the working tree, run `/accept` or `/reset`
before starting the next task (the clean-worktree guard will remind you).

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

While a run executes, each step is announced with a banner and the agent's (or
test command's) output is streamed live to the terminal, so you can see what is
happening as it happens:

```text
● plan  (claude · read_only)
  │ reading repository...
● implement  (codex · write)
  │ editing app.py
  ✓ implement · 1 file(s) touched
● review  (claude · review_only)
  ✓ review: pass
● test  (command group: test)
  ✓ tests passed
  ✓ DONE · 1 file(s) changed
```

Flags:

- `--quiet` suppresses the live progress/streaming (the run still records full
  artifacts under `.team/runs/<run-id>/`).
- `--no-color` disables ANSI color. Color is also disabled automatically when
  stdout is not a TTY or when `NO_COLOR` is set.

`codemate run` exits non-zero when the run does not reach `DONE`, so CI and
scripts can detect a failed or `NEEDS_HUMAN` run.

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

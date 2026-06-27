# codemate

`codemate` is a sequential AI development team runner.

It does not replace Codex CLI or Claude Code. It supervises them:

```text
Plan -> Implement -> Review -> Test
```

The CLI owns sequencing, git state, run artifacts, local test execution, and
policy checks. Agent CLIs only receive one bounded role at a time.

## Install

The PyPI distribution is `codemate-team`; it installs a `codemate` command.

As a global CLI tool (recommended):

```bash
uv tool install codemate-team
# or: pipx install codemate-team
codemate --help
```

Run once without installing:

```bash
uvx --from codemate-team codemate --help
```

For local development from a checkout:

```bash
uv run --with-editable . codemate --help
```

## Quick Start

Initialize a repo:

```bash
codemate init
```

Review and edit `team.yml`, then check local prerequisites:

```bash
codemate doctor
```

Start an interactive session (run `codemate` with no arguments):

```bash
codemate
```

```text
codemate · interactive session
repo: my-project   flow: plan_implement_review_test
type a task and press enter · /help for commands · /exit to quit

codemate› Fix the flaky checkout test
● plan  (claude · read_only)
  │ ...streamed agent output...
● implement  (codex · write)
  ✓ implement · 2 file(s) touched
● review  (claude · review_only)
  ✓ review: pass
● test  (command group: test)
  ✓ tests passed
  ✓ DONE · 2 file(s) changed
```

Inside the session you type tasks to run them, and use slash commands to inspect
and manage the result:

```text
/status            show the latest run status
/diff              show the current git diff
/logs [step]       show logs for the latest run
/accept            keep changes (or: /accept commit "message")
/reset             revert files changed by the latest run
/flow [name]       show or switch the active flow
/help              list all commands
/exit              quit
```

For scripts and CI, run a single task non-interactively:

```bash
codemate run "Fix the flaky checkout test"
codemate status
codemate logs --step implement
codemate diff
codemate accept --commit --message "Fix flaky checkout test"
codemate reset
```

## Generated Project Files

`codemate init` creates:

```text
team.yml
.team/
  prompts/
  schemas/
  runs/
docs/
  team.md
```

`.team/runs/` and `.team/lock.json` are ignored so run artifacts do not pollute
normal source control status.

## Safety Model

- The default config requires a clean worktree before a run starts.
- A run uses a branch under `ai/team/<run-id>`.
- Agent writes are checked against `policies.allow_paths` and
  `policies.deny_paths`.
- Local command output is recorded by the CLI.
- Agent claims about tests are ignored; configured commands are the authority.
- Fix loops are bounded by `limits.max_fix_retries`.
- The CLI never pushes or merges by default.

## Documentation

- [Overview](docs/README.md)
- [Architecture](docs/architecture.md)
- [Commands](docs/commands.md)
- [Configuration](docs/configuration.md)
- [Safety](docs/safety.md)

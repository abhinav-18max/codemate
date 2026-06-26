# codemate

`codemate` is a sequential AI development team runner.

It does not replace Codex CLI or Claude Code. It supervises them:

```text
Plan -> Implement -> Review -> Test
```

The CLI owns sequencing, git state, run artifacts, local test execution, and
policy checks. Agent CLIs only receive one bounded role at a time.

## Install for Local Development

```bash
uv run --with-editable . team --help
```

After packaging or installing normally, the command is:

```bash
team --help
```

## Quick Start

Initialize a repo:

```bash
team init
```

Review and edit `team.yml`, then check local prerequisites:

```bash
team doctor
```

Run a task:

```bash
team run "Fix the flaky checkout test"
```

Inspect results:

```bash
team status
team logs --step implement
team diff
```

Accept or reset:

```bash
team accept --commit --message "Fix flaky checkout test"
team reset
```

## Generated Project Files

`team init` creates:

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

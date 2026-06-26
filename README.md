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

Run a task:

```bash
codemate run "Fix the flaky checkout test"
```

Inspect results:

```bash
codemate status
codemate logs --step implement
codemate diff
```

Accept or reset:

```bash
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

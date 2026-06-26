# codemate Documentation

`codemate` is a deterministic supervisor for sequential AI-assisted development.

The intended model is:

```text
team CLI = supervisor
Claude Code = agent harness
Codex CLI = agent harness
Local commands = deterministic harness
Git = source of truth
team.yml = project contract
```

The default flow is:

```text
plan -> implement -> review -> test
```

There is no parallelism in the MVP. One step is active at a time, every step
gets a focused prompt, and every run writes neutral artifacts under
`.team/runs/<run-id>/`.

## Read Next

- [Architecture](architecture.md): internal modules and run lifecycle.
- [Commands](commands.md): CLI command reference.
- [Configuration](configuration.md): `team.yml` structure and examples.
- [Safety](safety.md): git, path policy, locks, retries, and operational rules.

## MVP Scope

Included:

- Project initialization.
- Config parsing and validation.
- Codex CLI and Claude Code adapters.
- Sequential plan/implement/review/test execution.
- Bounded fix loop.
- Run state and logs.
- Git diff and changed-file tracking.
- Path policy checks.

Intentionally excluded for now:

- Parallel agents.
- Background daemon execution.
- Multi-repo tasks.
- Cloud runners.
- Automatic pull requests.
- Auto-push or auto-merge behavior.

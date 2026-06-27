# Configuration

`team.yml` is the project contract. It controls workflows, agents, local
commands, git behavior, limits, and path policy.

## Minimal Shape

```yaml
version: 1

workflow:
  default: plan_implement_review_test
  flows:
    plan_implement_review_test:
      steps:
        - id: plan
          type: agent
          agent: claude
          mode: read_only
          output: plan
        - id: implement
          type: agent
          agent: codex
          mode: write
          output: implementation
        - id: review
          type: agent
          agent: claude
          mode: review_only
          output: review
        - id: test
          type: command
          command_group: test

agents:
  claude:
    provider: claude-code
    command: claude
  codex:
    provider: codex-cli
    command: codex

commands:
  test:
    - npm test
```

## Agents

Supported providers:

- `codex-cli`
- `claude-code`

### Model and effort

Each agent can pin a model and a reasoning/effort level. These map to the
underlying CLI flags, so the agent in a given step uses exactly the model you
choose for it:

| Key | Claude Code | Codex CLI |
|---|---|---|
| `model` | `--model` (`opus`, `sonnet`, `haiku`, `fable`, or a full id) | `-m` (e.g. `gpt-5-codex`) |
| `effort` (alias `reasoning_effort`) | `--effort` (`low`..`max`) | `-c model_reasoning_effort=...` (`low`/`medium`/`high`) |
| `extra_args` | passed through verbatim | passed through verbatim |

Use a cheaper, faster model for planning/review and a stronger one for
implementation, for example:

```yaml
agents:
  claude:
    provider: claude-code
    command: claude
    model: sonnet
    effort: medium
  codex:
    provider: codex-cli
    command: codex
    sandbox: workspace-write
    model: gpt-5-codex
    reasoning_effort: high
```

The same keys (`model`, `effort`/`reasoning_effort`, `provider`, `sandbox`,
`output_format`, `extra_args`, `timeout_seconds`) can also be set directly on a
workflow step, where they override the agent's value for that step only. This is
how you give one step a different model without defining a second agent:

```yaml
- id: review
  type: agent
  agent: claude
  mode: review_only
  model: sonnet      # review uses sonnet even though the claude agent is opus
  effort: medium
```

The interactive session can set these live with `/set <step|agent> <key>
<value>` (see the Commands doc).

`extra_args` is an escape hatch for any flag not modeled here:

```yaml
codex:
  provider: codex-cli
  command: codex
  extra_args:
    - "-c"
    - "model_reasoning_summary=concise"
```

Codex config example:

```yaml
codex:
  provider: codex-cli
  command: codex
  timeout_seconds: 900
  sandbox: workspace-write
  approval: never
```

Claude config example:

```yaml
claude:
  provider: claude-code
  command: claude
  timeout_seconds: 900
  default_mode: plan
  write_permission_mode: acceptEdits
  output_format: text   # set to "json" to capture only the final message
```

When `output_format: json` is set, the adapter passes `--output-format json` to
the Claude CLI and extracts the `result` field, so the recorded step output is
the final answer without surrounding tool/log noise. It falls back to the raw
captured text if the envelope cannot be parsed.

## Commands

Command groups are lists of shell commands:

```yaml
commands:
  test:
    - npm run lint
    - npm run typecheck
    - npm test
```

The CLI stops on the first failing command and records the output in
`.team/runs/<run-id>/test.log`.

## Git

```yaml
git:
  strategy: branch
  branch_prefix: ai/team
  checkpoint_commits: false
  require_clean_worktree: true
```

The MVP supports branch-based runs. Checkpoint commits are parsed from config
but not implemented yet.

## Limits

```yaml
limits:
  max_fix_retries: 2
  max_changed_files: 25
  max_diff_lines: 1500
  command_timeout_seconds: 900
```

Write-capable agent steps are checked against file and diff limits after they
finish.

## Path Policy

```yaml
policies:
  allow_paths:
    - src/**
    - tests/**
    - package.json
  deny_paths:
    - .env
    - .env.*
    - secrets/**
    - .git/**
    - node_modules/**
```

Policies are enforced from git status after write-capable steps. They are not
merely prompt instructions.

## YAML Support

The MVP uses a small built-in YAML parser to avoid a runtime dependency. It is
intended for the generated `team.yml` style:

- mappings
- nested mappings
- lists
- strings
- integers
- booleans
- simple inline lists

Advanced YAML features such as anchors, multiline scalars, tags, and complex
quoted escaping are not supported.

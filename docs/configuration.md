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
```

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

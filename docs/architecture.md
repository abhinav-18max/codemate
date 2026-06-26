# Architecture

`codemate` is organized around a small set of responsibilities:

```text
codemate/
  cli.py          command parsing and user-facing output
  config.py       team.yml defaults, validation, and init files
  workflow.py     sequential state machine
  agents.py       Codex CLI and Claude Code adapters
  commands.py     deterministic local command runner
  git_tools.py    git status, branch, diff, and commit helpers
  policy.py       changed-file allow/deny checks
  artifacts.py    run ids, run state, run directories, and locks
  yaml_lite.py    small YAML subset parser used by team.yml
```

## Run Lifecycle

`codemate run "task"` does this:

1. Load and validate `team.yml`.
2. Verify the current directory is a git repo.
3. Require a clean worktree when configured.
4. Create a run id and `.team/runs/<run-id>/`.
5. Acquire `.team/lock.json`.
6. Create a run branch when `git.strategy: branch`.
7. Run the plan step.
8. Run the implement step.
9. Run the review step.
10. Run configured local commands.
11. Run bounded fix cycles when review or commands fail.
12. Write `final.md` and `state.json`.

## State File

Each run writes:

```text
.team/runs/<run-id>/state.json
```

The state file records:

- run id
- task
- flow name
- current status
- branch
- base branch and base commit
- step results
- changed files
- failure reason, if any

The status values are intentionally simple:

```text
CREATED
PLANNING
PLANNED
IMPLEMENTING
IMPLEMENTED
REVIEWING
REVIEWED
REVIEW_PASSED
REVIEW_FAILED
TESTING
TEST_PASSED
TEST_FAILED
FIXING
DONE
NEEDS_HUMAN
AGENT_FAILED
```

## Adapter Boundary

Agents are called through `AgentAdapter`.

The workflow does not depend on Claude or Codex internals beyond their command
line interface. The adapters receive:

- run id
- step id
- project root
- rendered prompt
- mode
- output path
- raw log path
- optional schema path
- agent-specific config

The workflow derives changed files and diffs from git, not from agent output.

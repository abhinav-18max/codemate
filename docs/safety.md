# Safety Model

`codemate` treats agent output as untrusted and git/local command state as
authoritative.

## Clean Worktree

The default config has:

```yaml
git:
  require_clean_worktree: true
```

This prevents a run from mixing agent edits with unrelated local changes.

## Run Branches

Each run creates a branch:

```text
ai/team/<run-id>
```

The run state records the original branch and base commit.

## Locks

During a run, the CLI writes:

```text
.team/lock.json
```

This prevents two `team run` processes from mutating the same repo at once. The
lock records the process id and creation time. If the process no longer exists,
the next run can clear the stale lock.

## Agent Modes

Read-only and review-only steps are checked by comparing git state before and
after the step. If those steps change repository files, the run fails.

Write-capable steps are checked after completion:

- changed files must match `allow_paths`
- changed files must not match `deny_paths`
- changed file count must be under `limits.max_changed_files`
- diff line count must be under `limits.max_diff_lines`

## Tests

Agents can summarize work, but they do not decide whether tests passed. The CLI
runs the configured command group and records the output.

## Failure Handling

When a workflow failure occurs, the run state is marked:

```text
NEEDS_HUMAN
```

The failure reason is written to:

```text
.team/runs/<run-id>/state.json
.team/runs/<run-id>/final.md
```

The CLI still exits non-zero so scripts and CI can detect the failure.

## What the MVP Does Not Do

- It does not push branches.
- It does not merge branches.
- It does not open pull requests.
- It does not bypass agent sandboxing.
- It does not run agents in parallel.

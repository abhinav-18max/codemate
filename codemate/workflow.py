from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agents import AgentRunInput, adapter_for
from .artifacts import RunArtifacts, RunLock, RunState, new_run_id
from .commands import run_command_group
from .config import TeamConfig
from .git_tools import (
    changed_files,
    create_branch,
    current_branch,
    current_head,
    diff,
    ensure_repo,
    is_clean,
)
from .policy import enforce_path_policy


class WorkflowError(RuntimeError):
    pass


def run_task(config: TeamConfig, task: str, flow_name: str | None = None) -> RunState:
    root = config.root
    ensure_repo(root)
    if config.git_value("require_clean_worktree", True) and not is_clean(root):
        raise WorkflowError("Working tree must be clean before starting a run.")

    run_id = new_run_id()
    artifacts = RunArtifacts(root, run_id)
    flow = flow_name or config.default_flow_name
    base_branch = current_branch(root)
    base_head = current_head(root)
    branch = f"{config.git_value('branch_prefix', 'ai/team')}/{run_id}"
    state = RunState(
        run_id=run_id,
        task=task,
        flow=flow,
        status="CREATED",
        branch=branch,
        base_branch=base_branch,
        base_head=base_head,
    )
    artifacts.write_text("task.md", task + "\n")
    artifacts.write_state(state)

    with RunLock(root, run_id):
        try:
            if config.git_value("strategy", "branch") == "branch":
                create_branch(root, branch)
            steps = config.flow_steps(flow)
            _run_main_flow(config, artifacts, state, steps)
        except Exception as exc:
            try:
                state.changed_files = _source_changed_files(config)
            except Exception:
                pass
            _finish_needs_human(artifacts, state, str(exc))
            raise
    return state


def _run_main_flow(
    config: TeamConfig, artifacts: RunArtifacts, state: RunState, steps: list[dict[str, Any]]
) -> None:
    plan = _require_step(steps, "plan")
    implement = _require_step(steps, "implement")
    review = _require_step(steps, "review")
    test = _require_step(steps, "test")
    fix = _find_step(steps, "fix_if_needed") or implement
    max_retries = int(fix.get("max_retries", config.limit("max_fix_retries", 2)))

    _agent_step(config, artifacts, state, plan, "PLANNING", "PLANNED")
    _agent_step(config, artifacts, state, implement, "IMPLEMENTING", "IMPLEMENTED")

    attempts = 0
    while True:
        review_passed = _review_step(config, artifacts, state, review)
        if review_passed:
            break
        if attempts >= max_retries:
            _finish_needs_human(artifacts, state, "Review failed after max fix attempts")
            return
        attempts += 1
        _fix_step(config, artifacts, state, fix, attempts)

    attempts = 0
    while True:
        tests_passed = _test_step(config, artifacts, state, test)
        if tests_passed:
            state.status = "DONE"
            state.current_step = None
            state.reason = None
            state.changed_files = _source_changed_files(config)
            artifacts.write_text("final.md", _final_report(state))
            artifacts.write_state(state)
            return
        if attempts >= max_retries:
            _finish_needs_human(artifacts, state, "Tests failed after max fix attempts")
            return
        attempts += 1
        _fix_step(config, artifacts, state, fix, attempts)
        review_passed = _review_step(config, artifacts, state, review)
        if not review_passed and attempts >= max_retries:
            _finish_needs_human(artifacts, state, "Review failed during test fix loop")
            return


def _agent_step(
    config: TeamConfig,
    artifacts: RunArtifacts,
    state: RunState,
    step: dict[str, Any],
    running_status: str,
    success_status: str,
) -> Path:
    state.status = running_status
    state.current_step = str(step["id"])
    artifacts.write_state(state)
    before_source_files = _source_changed_files(config)
    before_diff = diff(config.root)

    output_name = str(step.get("output", step["id"]))
    prompt = _render_prompt(config, artifacts, state.task, str(step["id"]))
    prompt_path = artifacts.write_text(f"{step['id']}.prompt.md", prompt)
    output_path = artifacts.dir / f"{output_name}.output.md"
    raw_log_path = artifacts.dir / f"{step['id']}.raw.log"
    schema_path = config.root / ".team" / "schemas" / f"{output_name}.schema.json"

    agent_name = str(step["agent"])
    agent_config = config.agent(agent_name)
    adapter = adapter_for(agent_config)
    result = adapter.run(
        AgentRunInput(
            run_id=state.run_id,
            step_id=str(step["id"]),
            cwd=config.root,
            prompt=prompt_path.read_text(),
            mode=str(step.get("mode", "read_only")),
            expected_output=output_name,
            output_path=output_path,
            raw_log_path=raw_log_path,
            schema_path=schema_path,
            config=agent_config,
        )
    )

    source_files = _source_changed_files(config)
    if step.get("mode") != "write":
        if source_files != before_source_files or diff(config.root) != before_diff:
            raise WorkflowError(
                f"Read-only step changed repository files: {step['id']}"
            )
    else:
        enforce_path_policy(
            source_files,
            config.policy_paths("allow_paths"),
            config.policy_paths("deny_paths"),
        )
        _enforce_limits(config, source_files)
        artifacts.write_text(f"{step['id']}.diff", diff(config.root))

    state.status = success_status if result.ok else "AGENT_FAILED"
    state.current_step = None
    state.changed_files = source_files
    state.steps.append(
        {
            "id": step["id"],
            "type": "agent",
            "agent": agent_name,
            "status": "success" if result.ok else "failed",
            "output": str(output_path.relative_to(config.root)),
            "raw_log": str(raw_log_path.relative_to(config.root)),
            "exit_code": result.exit_code,
        }
    )
    artifacts.write_state(state)
    if not result.ok:
        raise WorkflowError(f"Agent step failed: {step['id']}")
    return output_path


def _review_step(
    config: TeamConfig, artifacts: RunArtifacts, state: RunState, step: dict[str, Any]
) -> bool:
    output_path = _agent_step(config, artifacts, state, step, "REVIEWING", "REVIEWED")
    output = output_path.read_text(errors="replace")
    passed = _review_passed(output)
    state.status = "REVIEW_PASSED" if passed else "REVIEW_FAILED"
    artifacts.write_state(state)
    return passed


def _test_step(
    config: TeamConfig, artifacts: RunArtifacts, state: RunState, step: dict[str, Any]
) -> bool:
    state.status = "TESTING"
    state.current_step = str(step["id"])
    artifacts.write_state(state)
    group = str(step.get("command_group", "test"))
    commands = config.command_group(group)
    log_path = artifacts.dir / "test.log"
    ok, failed_command, exit_code = run_command_group(
        config.root, commands, log_path, timeout_seconds=config.limit("command_timeout_seconds", 900)
    )
    state.status = "TEST_PASSED" if ok else "TEST_FAILED"
    state.current_step = None
    state.steps.append(
        {
            "id": step["id"],
            "type": "command",
            "command_group": group,
            "status": "success" if ok else "failed",
            "failed_command": failed_command,
            "exit_code": exit_code,
            "log": str(log_path.relative_to(config.root)),
        }
    )
    state.changed_files = _source_changed_files(config)
    artifacts.write_state(state)
    return ok


def _fix_step(
    config: TeamConfig,
    artifacts: RunArtifacts,
    state: RunState,
    step: dict[str, Any],
    attempt: int,
) -> None:
    fix_step = dict(step)
    fix_step["id"] = f"fix_{attempt}"
    fix_step["output"] = f"fix_{attempt}"
    fix_step["mode"] = "write"
    _agent_step(config, artifacts, state, fix_step, "FIXING", "IMPLEMENTED")


def _render_prompt(
    config: TeamConfig, artifacts: RunArtifacts, task: str, step_id: str
) -> str:
    prompt_name = "fix.md" if step_id.startswith("fix") else f"{step_id}.md"
    template_path = config.root / ".team" / "prompts" / prompt_name
    template = template_path.read_text() if template_path.exists() else "{{task}}"
    values = {
        "task": task,
        "plan": artifacts.read_text("plan.output.md"),
        "implementation": artifacts.read_text("implementation.output.md"),
        "review": artifacts.read_text("review.output.md"),
        "test_log": artifacts.read_text("test.log"),
        "git_diff": diff(config.root),
        "allow_paths": "\n".join(config.policy_paths("allow_paths")),
        "deny_paths": "\n".join(config.policy_paths("deny_paths")),
    }
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def _review_passed(output: str) -> bool:
    stripped = output.strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            data = {}
        decision = str(data.get("decision", data.get("status", ""))).lower()
        if decision in {"pass", "passed", "approved", "success"}:
            return True
        if decision in {"fail", "failed", "changes_requested", "blocking"}:
            return False
    lowered = output.lower()
    pass_markers = [
        "decision: pass",
        "decision: passed",
        "status: pass",
        "status: passed",
    ]
    if any(marker in lowered for marker in pass_markers):
        return True
    failure_markers = [
        "decision: fail",
        "decision: failed",
        "status: changes_requested",
        "changes_requested",
        "blocking",
    ]
    return not any(marker in lowered for marker in failure_markers)


def _source_changed_files(config: TeamConfig) -> list[str]:
    return [
        path
        for path in changed_files(config.root)
        if path != ".team/"
        and not path.startswith(".team/runs/")
        and path != ".team/lock.json"
    ]


def _enforce_limits(config: TeamConfig, source_files: list[str]) -> None:
    max_changed_files = config.limit("max_changed_files", 25)
    if len(source_files) > max_changed_files:
        raise WorkflowError(
            f"Changed file limit exceeded: {len(source_files)} > {max_changed_files}"
        )
    max_diff_lines = config.limit("max_diff_lines", 1500)
    diff_lines = len(diff(config.root).splitlines())
    if diff_lines > max_diff_lines:
        raise WorkflowError(f"Diff line limit exceeded: {diff_lines} > {max_diff_lines}")


def _finish_needs_human(artifacts: RunArtifacts, state: RunState, reason: str) -> None:
    state.status = "NEEDS_HUMAN"
    state.current_step = None
    state.reason = reason
    artifacts.write_text("final.md", _final_report(state))
    artifacts.write_state(state)


def _final_report(state: RunState) -> str:
    changed = "\n".join(f"- {path}" for path in state.changed_files) or "- none"
    reason = f"\nReason: {state.reason}\n" if state.reason else ""
    return f"""Run: {state.run_id}
Status: {state.status}
Flow: {state.flow}
Branch: {state.branch}
{reason}
Changed files:
{changed}
"""


def _find_step(steps: list[dict[str, Any]], step_id: str) -> dict[str, Any] | None:
    return next((step for step in steps if step.get("id") == step_id), None)


def _require_step(steps: list[dict[str, Any]], step_id: str) -> dict[str, Any]:
    step = _find_step(steps, step_id)
    if step is None:
        raise WorkflowError(f"Required step missing from flow: {step_id}")
    return step

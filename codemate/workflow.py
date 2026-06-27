from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agents import AgentRunInput, adapter_for
from .artifacts import RunArtifacts, RunLock, RunState, new_run_id
from .commands import run_command_group
from .config import TeamConfig
from .reporter import Reporter
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


def run_task(
    config: TeamConfig,
    task: str,
    flow_name: str | None = None,
    reporter: Reporter | None = None,
) -> RunState:
    root = config.root
    reporter = reporter or Reporter(enabled=False)
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
    reporter.run_header(run_id, flow, task)

    with RunLock(root, run_id):
        try:
            if config.git_value("strategy", "branch") == "branch":
                create_branch(root, branch)
                reporter.info(f"branch {branch}")
            steps = config.flow_steps(flow)
            _run_main_flow(config, artifacts, state, steps, reporter)
        except Exception as exc:
            try:
                state.changed_files = _source_changed_files(config)
            except Exception:
                pass
            _finish_needs_human(artifacts, state, str(exc))
            reporter.failure(str(exc))
            raise
    return state


def _run_main_flow(
    config: TeamConfig,
    artifacts: RunArtifacts,
    state: RunState,
    steps: list[dict[str, Any]],
    reporter: Reporter,
) -> None:
    plan = _require_step(steps, "plan")
    implement = _require_step(steps, "implement")
    review = _require_step(steps, "review")
    test = _require_step(steps, "test")
    fix = _find_step(steps, "fix_if_needed") or implement
    max_retries = int(fix.get("max_retries", config.limit("max_fix_retries", 2)))

    _agent_step(config, artifacts, state, plan, "PLANNING", "PLANNED", reporter)
    _agent_step(config, artifacts, state, implement, "IMPLEMENTING", "IMPLEMENTED", reporter)

    attempts = 0
    while True:
        review_passed, review_reason = _review_step(config, artifacts, state, review, reporter)
        if review_passed:
            break
        if attempts >= max_retries:
            _finish_needs_human(
                artifacts, state, review_reason or "Review failed after max fix attempts"
            )
            reporter.failure(review_reason or "Review failed after max fix attempts")
            return
        attempts += 1
        _fix_step(config, artifacts, state, fix, attempts, reporter)

    attempts = 0
    while True:
        tests_passed = _test_step(config, artifacts, state, test, reporter)
        if tests_passed:
            state.status = "DONE"
            state.current_step = None
            state.reason = None
            state.changed_files = _source_changed_files(config)
            artifacts.write_text("final.md", _final_report(state))
            artifacts.write_state(state)
            reporter.success(f"DONE · {len(state.changed_files)} file(s) changed")
            return
        if attempts >= max_retries:
            _finish_needs_human(artifacts, state, "Tests failed after max fix attempts")
            reporter.failure("Tests failed after max fix attempts")
            return
        attempts += 1
        _fix_step(config, artifacts, state, fix, attempts, reporter)
        review_passed, review_reason = _review_step(config, artifacts, state, review, reporter)
        if not review_passed and attempts >= max_retries:
            _finish_needs_human(
                artifacts, state, review_reason or "Review failed during test fix loop"
            )
            reporter.failure(review_reason or "Review failed during test fix loop")
            return


def _agent_step(
    config: TeamConfig,
    artifacts: RunArtifacts,
    state: RunState,
    step: dict[str, Any],
    running_status: str,
    success_status: str,
    reporter: Reporter,
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
    mode = str(step.get("mode", "read_only"))
    reporter.step(str(step["id"]), f"{agent_name} · {mode}")
    adapter = adapter_for(agent_config)
    result = adapter.run(
        AgentRunInput(
            run_id=state.run_id,
            step_id=str(step["id"]),
            cwd=config.root,
            prompt=prompt_path.read_text(),
            mode=mode,
            expected_output=output_name,
            output_path=output_path,
            raw_log_path=raw_log_path,
            schema_path=schema_path,
            config=agent_config,
            on_output=reporter.stream_line,
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
        reporter.failure(f"{step['id']} failed (exit {result.exit_code})")
        raise WorkflowError(f"Agent step failed: {step['id']}")
    if step.get("mode") == "write":
        reporter.success(f"{step['id']} · {len(source_files)} file(s) touched")
    else:
        reporter.success(f"{step['id']} complete")
    return output_path


def _review_step(
    config: TeamConfig,
    artifacts: RunArtifacts,
    state: RunState,
    step: dict[str, Any],
    reporter: Reporter,
) -> tuple[bool, str | None]:
    output_path = _agent_step(
        config, artifacts, state, step, "REVIEWING", "REVIEWED", reporter
    )
    output = output_path.read_text(errors="replace")
    passed, reason = _review_verdict(output)
    state.status = "REVIEW_PASSED" if passed else "REVIEW_FAILED"
    artifacts.write_state(state)
    if passed:
        reporter.success("review: pass")
    else:
        reporter.note(f"review: fail — {reason}")
    return passed, reason


def _test_step(
    config: TeamConfig,
    artifacts: RunArtifacts,
    state: RunState,
    step: dict[str, Any],
    reporter: Reporter,
) -> bool:
    state.status = "TESTING"
    state.current_step = str(step["id"])
    artifacts.write_state(state)
    group = str(step.get("command_group", "test"))
    commands = config.command_group(group)
    reporter.step("test", f"command group: {group}")
    log_path = artifacts.dir / "test.log"
    ok, failed_command, exit_code = run_command_group(
        config.root,
        commands,
        log_path,
        timeout_seconds=config.limit("command_timeout_seconds", 900),
        on_output=reporter.stream_line,
    )
    if ok:
        reporter.success("tests passed")
    else:
        reporter.note(f"tests failed: {failed_command} (exit {exit_code})")
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
    reporter: Reporter,
) -> None:
    fix_step = dict(step)
    fix_step["id"] = f"fix_{attempt}"
    fix_step["output"] = f"fix_{attempt}"
    fix_step["mode"] = "write"
    _agent_step(config, artifacts, state, fix_step, "FIXING", "IMPLEMENTED", reporter)


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


_PASS_DECISIONS = {"pass", "passed", "approve", "approved", "success", "lgtm"}
_FAIL_DECISIONS = {
    "fail",
    "failed",
    "reject",
    "rejected",
    "changes_requested",
    "blocking",
    "block",
}


def _review_verdict(output: str) -> tuple[bool, str | None]:
    """Decide whether a review passed, failing closed when undetermined.

    A review only passes on an explicit, machine-parseable pass decision. Empty,
    truncated, or ambiguous output is treated as a failure so it surfaces to a
    human instead of silently approving unreviewed changes.
    """
    decision = _extract_decision(output)
    if decision == "pass":
        return True, None
    if decision == "fail":
        return False, "Review returned a blocking decision"
    return False, "Review decision could not be determined (failing closed)"


def _extract_decision(output: str) -> str | None:
    text = output.strip()
    if not text:
        return None
    for candidate in _json_candidates(text):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            mapped = _map_decision(str(data.get("decision", data.get("status", ""))))
            if mapped:
                return mapped
    # Fall back to an explicit marker line; the last stated decision wins.
    for line in reversed(text.splitlines()):
        lowered = line.strip().lower()
        for key in ("decision:", "status:", "verdict:"):
            if lowered.startswith(key):
                mapped = _map_decision(lowered[len(key):])
                if mapped:
                    return mapped
    return None


def _json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    if text.startswith("{") and text.endswith("}"):
        candidates.append(text)
    depth = 0
    start = -1
    for index, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start != -1:
                candidates.append(text[start : index + 1])
                start = -1
    # Prefer the last balanced object (closest to the agent's final answer).
    candidates.reverse()
    return candidates


def _map_decision(value: str) -> str | None:
    token = value.strip().strip(".\"'").lower()
    if not token:
        return None
    first = token.replace("-", "_").split()[0]
    if first in _PASS_DECISIONS or token in _PASS_DECISIONS:
        return "pass"
    if first in _FAIL_DECISIONS or token in _FAIL_DECISIONS:
        return "fail"
    return None


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

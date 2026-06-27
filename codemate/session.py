from __future__ import annotations

import atexit
import sys
from pathlib import Path

from . import interactive
from .config import ConfigError, TeamConfig, load_config, validate_config
from .git_tools import diff, ensure_repo
from .reporter import Reporter
from .workflow import STEP_OVERRIDE_KEYS, WorkflowError, _agent_config_for_step, run_task

COMMANDS = [
    "/help",
    "/status",
    "/diff",
    "/logs",
    "/agents",
    "/steps",
    "/model",
    "/effort",
    "/set",
    "/unset",
    "/accept",
    "/reset",
    "/flow",
    "/clear",
    "/exit",
]

PROMPT = "\ncodemate› "

_SETTABLE_KEYS = {
    "model",
    "effort",
    "reasoning_effort",
    "provider",
    "sandbox",
    "output_format",
    "command",
    "timeout_seconds",
    "write_permission_mode",
    "approval_policy",
}

_MISSING = object()

HELP = """commands:
  /help              show this help
  /status            show the latest run status
  /diff              show the current git diff
  /logs [step]       show logs for the latest run (optionally one step)
  /agents            show agents and their provider/model/effort
  /steps             show each step and the model/effort it will use
  /model             pick a step/agent and model from a menu
  /effort            pick a step/agent and effort level from a menu
  /set <t> <k> <v>   set key k on a step id or agent name (model, effort, ...)
  /unset <t> <k>     remove a key from a step id or agent name
  /accept            keep changes in the working tree
  /accept commit msg commit the changes with a message
  /reset             revert files changed by the latest run
  /flow [name]       show or switch the active flow
  /clear             clear the screen
  /exit              quit the session

Type anything else and it runs as a task through the active flow.
Tip: press TAB to complete a command, or type just "/" for a menu.
Examples: /set review model sonnet · /set codex effort high · /unset review model"""


def run_session(
    root: Path,
    *,
    flow: str | None = None,
    quiet: bool = False,
    no_color: bool = False,
) -> int:
    config = load_config(root)
    ensure_repo(root)
    reporter = Reporter(enabled=not quiet, color=False if no_color else None)
    flow_name = flow or config.default_flow_name
    _enable_readline(root)
    interactive.install_completion(COMMANDS)
    _print_banner(root, flow_name)

    while True:
        try:
            line = input(PROMPT)
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("  (use /exit to quit)")
            continue
        line = line.strip()
        if not line:
            continue
        if line == "/":
            chosen = _palette()
            if not chosen:
                continue
            line = chosen
        if line.startswith("/"):
            stop, flow_name = _handle_command(root, config, line, flow_name)
            if stop:
                return 0
            continue
        _run_one(config, line, flow_name, reporter)


def _run_one(config: TeamConfig, task: str, flow_name: str, reporter: Reporter) -> None:
    from .cli import _format_state

    try:
        state = run_task(config, task, flow_name, reporter=reporter)
        print()
        print(_format_state(state))
    except WorkflowError as exc:
        message = str(exc)
        # In-flow failures already streamed a failure line via the reporter; only
        # the pre-flight clean-worktree guard needs surfacing here.
        if "clean" in message.lower():
            reporter.failure(message)
            reporter.note('next: /accept commit "msg" or /reset, then retry')
    except Exception as exc:  # pragma: no cover - defensive
        print(f"codemate: error: {exc}", file=sys.stderr)


def _handle_command(
    root: Path, config: TeamConfig, line: str, flow_name: str
) -> tuple[bool, str]:
    from . import cli

    parts = line[1:].split()
    cmd = parts[0].lower() if parts else ""
    rest = parts[1:]

    if cmd in {"exit", "quit", "q"}:
        print("bye")
        return True, flow_name
    if cmd in {"help", "h", "?"}:
        print(HELP)
    elif cmd == "status":
        try:
            print(cli._format_state(cli._load_state(root, None)))
        except Exception as exc:
            print(f"codemate: error: {exc}", file=sys.stderr)
    elif cmd == "diff":
        print(diff(root), end="")
    elif cmd == "logs":
        cli._logs(root, None, rest[0] if rest else None)
    elif cmd == "agents":
        _print_agents(config)
    elif cmd == "steps":
        _print_steps(config, flow_name)
    elif cmd == "model":
        _cmd_pick(config, flow_name, "model")
    elif cmd == "effort":
        _cmd_pick(config, flow_name, "effort")
    elif cmd == "set":
        if len(rest) < 3:
            print("usage: /set <step-id|agent> <key> <value>")
        else:
            _set_config(config, flow_name, rest[0], rest[1], " ".join(rest[2:]))
    elif cmd == "unset":
        if len(rest) < 2:
            print("usage: /unset <step-id|agent> <key>")
        else:
            _unset_config(config, flow_name, rest[0], rest[1])
    elif cmd == "accept":
        commit = bool(rest) and rest[0] == "commit"
        message = " ".join(rest[1:]) if commit and len(rest) > 1 else None
        cli._accept(root, commit, message)
    elif cmd == "reset":
        cli._reset(root, None)
    elif cmd == "flow":
        target = rest[0] if rest else _pick_flow(config)
        if target:
            try:
                config.flow_steps(target)
                flow_name = target
                print(f"flow set to {flow_name}")
            except Exception as exc:
                print(f"codemate: error: {exc}", file=sys.stderr)
        else:
            print(f"flow: {flow_name}")
    elif cmd == "clear":
        print("\033[2J\033[H", end="")
    else:
        print(f"unknown command: /{cmd} (try /help)")
    return False, flow_name


def _effort_of(config_map: dict) -> str:
    return config_map.get("effort") or config_map.get("reasoning_effort") or "(cli default)"


def _print_agents(config: TeamConfig) -> None:
    print("agents:")
    for name, agent in config.raw.get("agents", {}).items():
        if not isinstance(agent, dict):
            continue
        provider = agent.get("provider", "?")
        model = agent.get("model", "(cli default)")
        print(f"  {name:<10} {provider:<12} model={model}  effort={_effort_of(agent)}")


def _print_steps(config: TeamConfig, flow_name: str) -> None:
    print(f"steps (flow: {flow_name}):")
    for step in config.flow_steps(flow_name):
        sid = str(step.get("id"))
        if step.get("type") == "command":
            print(f"  {sid:<10} command group: {step.get('command_group')}")
            continue
        merged = _agent_config_for_step(config, step)
        model = merged.get("model", "(cli default)")
        overrides = [key for key in STEP_OVERRIDE_KEYS if key in step]
        suffix = f"  [override: {', '.join(overrides)}]" if overrides else ""
        print(
            f"  {sid:<10} {step.get('agent')} ({merged.get('provider')})  "
            f"model={model}  effort={_effort_of(merged)}{suffix}"
        )


def _resolve_target(config: TeamConfig, flow_name: str, target: str) -> tuple[str | None, dict | None]:
    for step in config.flow_steps(flow_name):
        if str(step.get("id")) == target and step.get("type") == "agent":
            return "step", step
    agents = config.raw.get("agents", {})
    if isinstance(agents.get(target), dict):
        return "agent", agents[target]
    return None, None


def _set_config(config: TeamConfig, flow_name: str, target: str, key: str, value: str) -> None:
    key = key.lower()
    if key not in _SETTABLE_KEYS:
        print(
            f"codemate: error: cannot set '{key}' "
            f"(allowed: {', '.join(sorted(_SETTABLE_KEYS))})",
            file=sys.stderr,
        )
        return
    kind, obj = _resolve_target(config, flow_name, target)
    if kind is None or obj is None:
        print(f"codemate: error: no step or agent named '{target}'", file=sys.stderr)
        return
    if kind == "step" and key not in STEP_OVERRIDE_KEYS:
        print(f"codemate: error: '{key}' cannot be set per step", file=sys.stderr)
        return
    if key == "provider" and value not in {"codex-cli", "claude-code"}:
        print("codemate: error: provider must be codex-cli or claude-code", file=sys.stderr)
        return
    coerced: object = int(value) if key == "timeout_seconds" and value.isdigit() else value

    previous = obj.get(key, _MISSING)
    obj[key] = coerced
    try:
        validate_config(config.raw)
    except ConfigError as exc:
        if previous is _MISSING:
            obj.pop(key, None)
        else:
            obj[key] = previous
        print(f"codemate: error: {exc}", file=sys.stderr)
        return
    where = f"step {target}" if kind == "step" else f"agent {target}"
    print(f"set {where}.{key} = {coerced}")


def _unset_config(config: TeamConfig, flow_name: str, target: str, key: str) -> None:
    kind, obj = _resolve_target(config, flow_name, target)
    if kind is None or obj is None:
        print(f"codemate: error: no step or agent named '{target}'", file=sys.stderr)
        return
    if key in obj:
        del obj[key]
        print(f"unset {target}.{key}")
    else:
        print(f"{target} has no '{key}' set")


def _palette() -> str | None:
    options = [
        ("status   — latest run status", "/status"),
        ("diff     — current git diff", "/diff"),
        ("steps    — steps and their models", "/steps"),
        ("agents   — agent settings", "/agents"),
        ("model    — set a model", "/model"),
        ("effort   — set effort level", "/effort"),
        ("flow     — switch the active flow", "/flow"),
        ("logs     — latest run logs", "/logs"),
        ("accept   — keep changes", "/accept"),
        ("reset    — revert changes", "/reset"),
        ("help     — all commands", "/help"),
        ("exit     — quit", "/exit"),
    ]
    return interactive.select("commands", options)


def _pick_flow(config: TeamConfig) -> str | None:
    flows = list(config.raw.get("workflow", {}).get("flows", {}).keys())
    return interactive.select("flow", [(name, name) for name in flows])


def _pick_target(config: TeamConfig, flow_name: str) -> str | None:
    options: list[tuple[str, str]] = []
    for name in config.raw.get("agents", {}):
        options.append((f"agent: {name}", name))
    for step in config.flow_steps(flow_name):
        if step.get("type") == "agent":
            options.append((f"step:  {step['id']}", str(step["id"])))
    return interactive.select("apply to", options)


def _model_presets(config: TeamConfig, flow_name: str, target: str) -> list[tuple[str, str]]:
    kind, obj = _resolve_target(config, flow_name, target)
    if kind == "agent" and obj is not None:
        provider = str(obj.get("provider", ""))
    elif kind == "step" and obj is not None:
        provider = str(_agent_config_for_step(config, obj).get("provider", ""))
    else:
        provider = ""
    if provider == "claude-code":
        models = ["claude-opus-4-8", "opus", "sonnet", "haiku", "fable"]
    elif provider == "codex-cli":
        models = ["gpt-5.5", "gpt-5-codex", "o3"]
    else:
        models = []
    return [(model, model) for model in models]


def _cmd_pick(config: TeamConfig, flow_name: str, key: str) -> None:
    if not interactive.supports_menus():
        print(f"interactive menus need a terminal; use /set <target> {key} <value>")
        return
    target = _pick_target(config, flow_name)
    if not target:
        return
    if key == "model":
        options = _model_presets(config, flow_name, target) + [("custom…", "__custom__")]
    else:
        options = [(level, level) for level in ("low", "medium", "high", "xhigh", "max")]
    choice = interactive.select(f"{key} · {target}", options)
    if choice is None:
        return
    value = interactive.prompt_text(f"{key}: ") if choice == "__custom__" else choice
    if value:
        _set_config(config, flow_name, target, key, value)


def _print_banner(root: Path, flow_name: str) -> None:
    print("codemate · interactive session")
    print(f"repo: {root.name}   flow: {flow_name}")
    print("type a task and press enter · /help for commands · /exit to quit")


def _enable_readline(root: Path) -> None:
    try:
        import readline
    except ImportError:  # pragma: no cover - platform dependent
        return
    histfile = root / ".team" / "history"
    try:
        histfile.parent.mkdir(parents=True, exist_ok=True)
        if histfile.exists():
            readline.read_history_file(str(histfile))
    except OSError:  # pragma: no cover - best effort
        pass

    def _save() -> None:
        try:
            readline.set_history_length(1000)
            readline.write_history_file(str(histfile))
        except OSError:  # pragma: no cover - best effort
            pass

    atexit.register(_save)

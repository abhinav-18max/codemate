from __future__ import annotations

import os
import sys
from typing import Sequence

Option = tuple[str, str]  # (label, value)

_ARROWS = {b"[A": "up", b"[B": "down", b"OA": "up", b"OB": "down"}


def supports_menus() -> bool:
    """True when we can drive an arrow-key menu on this terminal."""
    if os.environ.get("CODEMATE_NO_MENU"):
        return False
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    try:
        import termios  # noqa: F401
        import tty  # noqa: F401
    except ImportError:
        return False
    return True


def _color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def render_menu(title: str, options: Sequence[Option], index: int, color: bool) -> str:
    def paint(code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if color else text

    lines: list[str] = []
    if title:
        lines.append(paint("1", title))
    for i, (label, _value) in enumerate(options):
        if i == index:
            lines.append(paint("36", f"❯ {label}"))
        else:
            lines.append(f"  {label}")
    lines.append(paint("2", "↑/↓ move · enter select · esc cancel"))
    return "\n".join(lines)


def decode_key(first: bytes, more: bytes = b"") -> str:
    """Map raw bytes to a key token. `more` holds bytes read after ESC."""
    if first in (b"\r", b"\n"):
        return "enter"
    if first in (b"\x03", b"q", b"Q"):
        return "cancel"
    if first in (b"k", b"K"):
        return "up"
    if first in (b"j", b"J"):
        return "down"
    if first == b"\x1b":
        return _ARROWS.get(more, "cancel" if more == b"" else "other")
    return "other"


def _read_key(fd: int) -> str:
    import select

    ch = os.read(fd, 1)
    if ch == b"\x1b":
        ready, _, _ = select.select([fd], [], [], 0.05)
        more = os.read(fd, 2) if ready else b""
        return decode_key(ch, more)
    return decode_key(ch)


def _draw(text: str, previous_lines: int) -> int:
    out = sys.stdout
    if previous_lines:
        out.write("\r")
        if previous_lines > 1:
            out.write(f"\033[{previous_lines - 1}A")
        out.write("\033[J")
    out.write(text.replace("\n", "\r\n"))
    out.flush()
    return text.count("\n") + 1


def select(title: str, options: Sequence[Option]) -> str | None:
    """Arrow-key menu. Returns the chosen value, or None if cancelled or when the
    terminal cannot host a menu (caller should fall back to typed input)."""
    if not options or not supports_menus():
        return None
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    color = _color()
    index = 0
    count = len(options)
    drawn = 0
    result: str | None = None
    try:
        tty.setraw(fd)
        while True:
            drawn = _draw(render_menu(title, options, index, color), drawn)
            key = _read_key(fd)
            if key == "up":
                index = (index - 1) % count
            elif key == "down":
                index = (index + 1) % count
            elif key == "enter":
                result = options[index][1]
                break
            elif key == "cancel":
                result = None
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        sys.stdout.write("\r\n")
        sys.stdout.flush()
    return result


def prompt_text(message: str) -> str:
    try:
        return input(message).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def install_completion(commands: Sequence[str]) -> None:
    """Enable readline TAB completion for slash commands."""
    try:
        import readline
    except ImportError:  # pragma: no cover - platform dependent
        return

    ordered = sorted(commands)

    def complete(text: str, state: int) -> str | None:
        if not text.startswith("/"):
            return None
        matches = [c for c in ordered if c.startswith(text)]
        return matches[state] + " " if state < len(matches) else None

    readline.set_completer(complete)
    readline.parse_and_bind("tab: complete")
    # Only break the line on whitespace so "/fl" completes as a unit.
    readline.set_completer_delims(" \t\n")

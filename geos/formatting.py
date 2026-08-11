"""GEOS CLI formatting utilities — colors, icons, and pretty output.

Zero dependencies; uses only ANSI escape codes. Gracefully degrades
when stdout is not a TTY (e.g. piped output).
"""

from __future__ import annotations

import sys
from typing import Any


def _is_tty() -> bool:
    """Check if stdout is a terminal."""
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


_TTY = _is_tty()


# ── ANSI Colors ───────────────────────────────────────────────────────────────

class Color:
    """ANSI color codes."""

    # Reset
    RESET = "\033[0m"

    # Regular
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    # Bold
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Bold colors
    BOLD_RED = "\033[1;31m"
    BOLD_GREEN = "\033[1;32m"
    BOLD_YELLOW = "\033[1;33m"
    BOLD_BLUE = "\033[1;34m"
    BOLD_MAGENTA = "\033[1;35m"
    BOLD_CYAN = "\033[1;36m"
    BOLD_WHITE = "\033[1;37m"

    # Background
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"


def _c(text: str, color: str) -> str:
    """Wrap text in color if TTY, otherwise return plain text."""
    if not _TTY:
        return text
    try:
        return f"{color}{text}{Color.RESET}"
    except UnicodeEncodeError:
        return text


# ── Icons (Unicode) ──────────────────────────────────────────────────────────

class Icon:
    """Unicode icons for CLI output."""

    CHECK = "✓"
    CROSS = "✗"
    WARN = "⚠"
    INFO = "●"
    ARROW = "→"
    DOT = "•"
    STAR = "★"
    GEAR = "⚙"
    ROCKET = "🚀"
    BOOK = "📚"
    MAGNIFIER = "🔍"
    CHART = "📊"
    LINK = "🔗"
    BULB = "💡"
    LOCK = "🔒"
    UNLOCK = "🔓"
    PACKAGE = "📦"
    FOLDER = "📁"
    FILE = "📄"
    TRASH = "🗑️"
    CHECKMARK = "✅"
    CROSSMARK = "❌"
    WARNING = "⚠️"
    INFO_ICON = "ℹ️"


# ── Badges ────────────────────────────────────────────────────────────────────

def badge_ok(text: str) -> str:
    """Green OK badge."""
    if not _TTY:
        return f"[{text}]"
    return _c(f" {text} ", Color.BG_GREEN + Color.BOLD + Color.WHITE)


def badge_warn(text: str) -> str:
    """Yellow warning badge."""
    if not _TTY:
        return f"[{text}]"
    return _c(f" {text} ", Color.BG_YELLOW + Color.BOLD + Color.WHITE)


def badge_error(text: str) -> str:
    """Red error badge."""
    if not _TTY:
        return f"[{text}]"
    return _c(f" {text} ", Color.BG_RED + Color.BOLD + Color.WHITE)


def badge_info(text: str) -> str:
    """Blue info badge."""
    if not _TTY:
        return f"[{text}]"
    return _c(f" {text} ", Color.BG_BLUE + Color.BOLD + Color.WHITE)


def badge_version(text: str) -> str:
    """Cyan version badge."""
    if not _TTY:
        return f"[{text}]"
    return _c(f" {text} ", Color.BG_CYAN + Color.BOLD + Color.WHITE)


def badge_spec(text: str) -> str:
    """Magenta spec badge."""
    if not _TTY:
        return f"[{text}]"
    return _c(f" {text} ", Color.BG_MAGENTA + Color.BOLD + Color.WHITE)


# ── Status indicators ─────────────────────────────────────────────────────────

def status_ok(detail: str = "") -> str:
    """✓ OK status line."""
    icon = _c(Icon.CHECK, Color.GREEN + Color.BOLD) if _TTY else "+"
    return f"{icon} {detail}" if detail else icon


def status_warn(detail: str = "") -> str:
    """⚠ Warning status line."""
    icon = _c(Icon.WARN, Color.YELLOW + Color.BOLD) if _TTY else "!"
    return f"{icon} {detail}" if detail else icon


def status_error(detail: str = "") -> str:
    """✗ Error status line."""
    icon = _c(Icon.CROSS, Color.RED + Color.BOLD) if _TTY else "x"
    return f"{icon} {detail}" if detail else icon


def status_info(detail: str = "") -> str:
    """● Info status line."""
    icon = _c(Icon.INFO, Color.CYAN) if _TTY else "*"
    return f"{icon} {detail}" if detail else icon


def status_arrow(detail: str = "") -> str:
    """→ Arrow indicator."""
    icon = _c(Icon.ARROW, Color.BLUE) if _TTY else ">"
    return f"  {icon} {detail}" if detail else f"  {icon}"


# ── Heading / Section ─────────────────────────────────────────────────────────

def heading(text: str, level: int = 1) -> str:
    """Colored heading."""
    if level == 1:
        return _c(f"\n{'═' * 60}\n  {text}\n{'═' * 60}", Color.BOLD_CYAN)
    elif level == 2:
        return _c(f"\n── {text} {'─' * (55 - len(text))}", Color.BOLD_BLUE)
    else:
        return _c(f"  {text}", Color.BOLD)


def subheading(text: str) -> str:
    """Subheading with dim styling."""
    return _c(f"  {text}", Color.DIM)


# ── Formatted values ──────────────────────────────────────────────────────────

def value(text: Any) -> str:
    """Highlight a value (number, id, etc)."""
    return _c(str(text), Color.BOLD_CYAN)


def label(text: str) -> str:
    """Dim label."""
    return _c(text, Color.DIM)


def key(text: str) -> str:
    """Key name in key=value pairs."""
    return _c(text, Color.BOLD)


def dim(text: str) -> str:
    """Dimmed text."""
    return _c(text, Color.DIM)


def bold(text: str) -> str:
    """Bold text."""
    return _c(text, Color.BOLD)


def success(text: str) -> str:
    """Success message."""
    return _c(text, Color.GREEN)


def error(text: str) -> str:
    """Error message."""
    return _c(text, Color.RED)


def warning(text: str) -> str:
    """Warning message."""
    return _c(text, Color.YELLOW)


def info(text: str) -> str:
    """Info message."""
    return _c(text, Color.CYAN)


# ── Table helpers ─────────────────────────────────────────────────────────────

def table_row(*cols: str, widths: list[int] | None = None) -> str:
    """Format a table row with optional fixed widths."""
    if widths:
        parts = []
        for col, w in zip(cols, widths):
            parts.append(col.ljust(w))
        return "  ".join(parts)
    return "  ".join(cols)


def table_header(*cols: str, widths: list[int] | None = None) -> str:
    """Format a table header row."""
    return table_row(*[_c(c, Color.BOLD + Color.DIM) for c in cols], widths=widths)


def table_divider(width: int = 60) -> str:
    """Horizontal divider line."""
    return _c("─" * width, Color.DIM)


# ── Print helpers (with auto-newline) ────────────────────────────────────────

def print_ok(msg: str) -> None:
    """Print OK status."""
    print(f"  {status_ok(msg)}")


def print_warn(msg: str) -> None:
    """Print warning status."""
    print(f"  {status_warn(msg)}")


def print_error(msg: str) -> None:
    """Print error status."""
    print(f"  {status_error(msg)}")


def print_info(msg: str) -> None:
    """Print info status."""
    print(f"  {status_info(msg)}")


def print_arrow(msg: str) -> None:
    """Print arrow indicator."""
    print(f"  {status_arrow(msg)}")


def print_kv(key_str: str, value_str: str) -> None:
    """Print key: value pair."""
    print(f"  {key(key_str)}: {value(value_str)}")


def print_section(title: str) -> None:
    """Print section heading."""
    print(heading(title, level=2))


def print_banner() -> None:
    """Print GEOS ASCII banner."""
    banner = r"""
   _____ ______ ____  _____  
  / ____|  ____/ __ \|  __ \ 
 | |  __| |__ | |  | | |  | |
 | | |_ |  __|| |  | | |  | |
 | |__| | |___| |__| | |__| |
  \_____|______\____/|_____/ 
"""
    if _TTY:
        print(_c(banner, Color.BOLD_CYAN))
        print(_c("  Growth, Education & Organizational System", Color.DIM))
        print(_c("  Open-source · Local-first · AI Agent Framework", Color.DIM))
        print()
    else:
        print("GEOS — Growth, Education & Organizational System")

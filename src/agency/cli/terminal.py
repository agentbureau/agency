"""Three-layer terminal typography for Agency CLI (v1.2.4 Issue 20).

Layer 1: status() — dim/grey for system progress and confirmations
Layer 2: helper() — italic, indented for contextual guidance
Layer 3: prompt() — bold cyan for user decision points
"""
import sys

ANSI_BOLD = "\033[1m"
ANSI_DIM = "\033[2m"
ANSI_ITALIC = "\033[3m"
ANSI_RESET = "\033[0m"
ANSI_GREEN = "\033[32m"
ANSI_RED = "\033[31m"
ANSI_CYAN = "\033[36m"


def _is_tty() -> bool:
    return sys.stdout.isatty()


def status(msg: str) -> None:
    """System status — dim/grey. Progress, confirmations, non-interactive output."""
    if _is_tty():
        print(f"{ANSI_DIM}{msg}{ANSI_RESET}")
    else:
        print(msg)


def helper(msg: str) -> None:
    """Contextual guidance — italic, indented. Explains what a setting means."""
    if _is_tty():
        print(f"  {ANSI_ITALIC}{msg}{ANSI_RESET}")
    else:
        print(f"  {msg}")


def prompt(msg: str, default: str | None = None) -> str:
    """User decision point — bold, prefixed. Waits for input."""
    suffix = f" [{default}]" if default else ""
    if _is_tty():
        display = f"{ANSI_BOLD}{ANSI_CYAN}> {msg}{suffix}: {ANSI_RESET}"
    else:
        display = f"{msg}{suffix}: "
    return input(display) or (default or "")


def success(msg: str) -> None:
    """Success confirmation — green prefix."""
    if _is_tty():
        print(f"{ANSI_GREEN}OK: {msg}{ANSI_RESET}")
    else:
        print(f"OK: {msg}")


def error(msg: str) -> None:
    """Error — red prefix."""
    if _is_tty():
        print(f"{ANSI_RED}ERROR: {msg}{ANSI_RESET}")
    else:
        print(f"ERROR: {msg}")

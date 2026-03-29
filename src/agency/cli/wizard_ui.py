"""Three-layer typographic system for Agency setup wizards.

Shared by `agency init` and `agency client setup`.
"""
import sys
from typing import Optional

import click


# -- ANSI codes ---------------------------------------------------------------

_BOLD = "\033[1m"
_DIM = "\033[2m"
_ITALIC = "\033[3m"
_RESET = "\033[0m"
_GREEN = "\033[32m"
_RED = "\033[31m"
_CYAN = "\033[36m"


def _is_tty() -> bool:
    """Return True if stdout is a real terminal (not piped or redirected)."""
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


# -- Layer 1: System status ---------------------------------------------------

def status(msg: str, *, success: bool = True) -> None:
    """Print a system-status line. Dim, indented 2 spaces, prefixed with
    a green checkmark (success) or red cross (failure).

    Plain-text fallback when not a TTY: indentation and ASCII prefix only.
    """
    if _is_tty():
        prefix = f"{_GREEN}✓{_RESET}" if success else f"{_RED}✗{_RESET}"
        click.echo(f"  {_DIM}{prefix} {msg}{_RESET}")
    else:
        prefix = "[ok]" if success else "[FAIL]"
        click.echo(f"  {prefix} {msg}")


# -- Layer 2: Helper text -----------------------------------------------------

def helper(msg: str) -> None:
    """Print helper/explanation text. Italic+dim, indented 4 spaces.

    Accepts multi-line strings — each line is indented and styled independently.
    Plain-text fallback: 4-space indent only, no styling.
    """
    for line in msg.splitlines():
        if _is_tty():
            click.echo(f"    {_DIM}{_ITALIC}{line}{_RESET}")
        else:
            click.echo(f"    {line}")


# -- Layer 3: User prompt -----------------------------------------------------

def prompt(
    msg: str,
    default: Optional[str] = None,
    *,
    hide_input: bool = False,
    type: Optional[click.ParamType] = None,
) -> str:
    """Print a user prompt. Bold, cyan accent, prefixed with ▶, no indent.

    Returns the user's input (or the default if they press Enter).
    Plain-text fallback: ▶ prefix without colour.
    """
    if _is_tty():
        styled = f"{_BOLD}{_CYAN}▶ {msg}{_RESET}"
    else:
        styled = f"▶ {msg}"

    show_default = default is not None
    return click.prompt(
        styled,
        default=default,
        show_default=show_default,
        hide_input=hide_input,
        type=type,
    )


def prompt_bool(
    msg: str,
    default: bool = True,
) -> bool:
    """Yes/no prompt using the explicit format:
    'enter y(es) or N(o) [default: yes]'

    Returns True for yes, False for no.
    """
    default_word = "yes" if default else "no"
    suffix = f'enter y(es) or N(o) [default: {default_word}]'

    if _is_tty():
        styled = f"{_BOLD}{_CYAN}▶ {msg}{_RESET}\n  {suffix}"
    else:
        styled = f"▶ {msg}\n  {suffix}"

    while True:
        raw = click.prompt(styled, default="", show_default=False)
        raw = raw.strip().lower()
        if raw == "":
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        click.echo('  Please enter "y" for yes or "n" for no.')


def prompt_choice(
    msg: str,
    options: list[str],
    default: str,
) -> str:
    """Prompt with a numbered list of options. Returns the selected option string."""
    if _is_tty():
        click.echo(f"\n{_BOLD}{_CYAN}▶ {msg}{_RESET}")
    else:
        click.echo(f"\n▶ {msg}")

    for i, opt in enumerate(options, 1):
        click.echo(f"  ({i}) {opt}")

    default_idx = options.index(default) + 1 if default in options else 1
    while True:
        raw = click.prompt(f"  Select", default=str(default_idx))
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1]
        except ValueError:
            pass
        click.echo(f"  Please enter a number from 1 to {len(options)}.")


# -- Helper text for each wizard setting --------------------------------------
# Keys match the setting name. Values are multi-line strings displayed
# by helper() before the corresponding prompt.

SETTING_HELP = {
    "instance_credentials": (
        'Instance ID uniquely identifies this Agency installation.\n'
        'Signing keypair authenticates API tokens issued by this instance.'
    ),
    "server_settings": (
        'Local server address for the Agency API.\n'
        'Change with agency client setup if port 8000 is taken.'
    ),
    "oversight_preference": (
        'Controls whether Agency asks for clarification when a task\n'
        'description is ambiguous, or uses its own judgement.\n'
        '"discretion" = Agency decides on its own (faster, less interruption).\n'
        '"review" = Agency asks you before proceeding (safer for high-stakes work).\n'
        'Most users start with "discretion".\n'
        'Change later: agency client setup, or edit ~/.agency/agency.toml'
    ),
    "contact_email": (
        'Used for error notifications — if a task assignment fails and Agency\n'
        "can't recover, it sends an alert to this address. Optional.\n"
        'If you skip this, errors are logged but no email is sent.\n'
        'Change later: agency client setup, or edit ~/.agency/agency.toml'
    ),
    "attribution": (
        'Adds a one-line disclosure to every agent\'s output:\n'
        '"This output was produced by an AI agent configured via Agency."\n'
        'Useful for transparency when agent output is shared with others.\n'
        'Can be turned off per project with agency project create --attribution off.\n'
        'Change later: agency client setup, or edit ~/.agency/agency.toml'
    ),
    "error_notification_timeout": (
        'How long (in seconds) Agency waits before sending an error notification.\n'
        '1800 = 30 minutes. Shorter values mean faster alerts but more noise.\n'
        'Change later: agency client setup, or edit ~/.agency/agency.toml'
    ),
    "llm_backend": (
        'How Agency makes its internal LLM calls for primitive matching\n'
        'and agent composition. This is separate from the model you use\n'
        'in Claude Code — Agency needs its own LLM access.\n'
        'Change later: agency client setup, or edit ~/.agency/agency.toml [llm]'
    ),
    "register_mcp": (
        'This lets Claude Code call Agency tools directly. If you say no,\n'
        'you can register manually later with agency client setup.'
    ),
    "database_init": (
        'Agency stores task history and agent compositions in a local database.\n'
        'The server starts briefly to initialise the schema, then stops.'
    ),
    "embedding_model": (
        'Agency uses this model to match tasks to the right agent primitives.\n'
        'Downloaded once (~1.4GB). Runs locally — no API calls needed.'
    ),
    "integration_tokens": (
        'Tokens authenticate different integrations with the Agency server.\n'
        'MCP: used by Claude Code. CLI: used by terminal commands.\n'
        'Superpowers: used by the agent self-improvement loop.\n'
        'Workgraph: used by the task dependency engine.\n'
        'Revoke any token with: agency token revoke <name>\n'
        'Tokens are stored in ~/.agency-<name>-token files.'
    ),
    "project_name": (
        'An Agency project groups related tasks and their agent compositions.\n'
        'Think of it as a workspace for one initiative — e.g., "my-app backend"\n'
        'or "Q2 research". You can create more projects later with:\n'
        'agency project create'
    ),
    "default_project": (
        'The default project is used when you call agency_assign without\n'
        'specifying a project ID. If you only have one project, say yes.\n'
        'Change later: agency project pin <project-id>'
    ),
    "smtp": (
        'SMTP lets Agency send email notifications for errors and task events.\n'
        'If you skip this, errors are logged locally but no emails are sent.\n'
        'Configure later: agency client setup'
    ),
}

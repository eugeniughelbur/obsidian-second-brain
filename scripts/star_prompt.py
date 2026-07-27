"""A one-time, earned ask for a GitHub star.

The README carries the same ask to every stranger who lands on the repo. This
one runs in the terminal, after the tool has just done something measurable for
the person reading it, and quotes the number they are already looking at.

Everything about this is designed so it can only ever be seen once and can
always be turned off, because a growth prompt that fires twice is spam and one
that fires in CI is a bug:

- once per machine, ever, tracked by a marker file in the config directory
- never when OBSIDIAN_NO_STAR_PROMPT is set, or when CI is set
- only on a genuinely good outcome, decided by the caller, never unconditionally
- never on a machine-readable path, which is the caller's job: `--json` branches
  must not call this at all

Deliberately NOT gated on `stdout.isatty()`, which was the first attempt. In this
project the scripts are usually run by an agent on the user's behalf, so stdout is
a pipe almost every time and the person still reads every line of it. A tty check
would have made this look careful while guaranteeing it never fired for anyone.
CI is excluded by environment instead, which is what that check was really for.

If the marker cannot be written the prompt is skipped rather than shown, since a
prompt that cannot record itself is a prompt that will repeat forever.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_URL = "https://github.com/eugeniughelbur/obsidian-second-brain"

_MARKER_NAME = ".star-prompt-shown"


def _config_dir() -> Path:
    """Same directory install.sh uses, honouring XDG when it is set."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "obsidian-second-brain"


def _suppressed() -> bool:
    if os.environ.get("OBSIDIAN_NO_STAR_PROMPT"):
        return True
    # Most CI providers set CI=true. A build machine is not a person.
    if os.environ.get("CI"):
        return True
    return False


def _claim_once(marker: Path) -> bool:
    """True exactly once per machine. False on every later call, and on error.

    Uses exclusive create so two concurrent runs cannot both win the claim.
    """
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        with Path(marker).open("x", encoding="utf-8") as fh:
            fh.write("shown\n")
        return True
    except FileExistsError:
        return False
    except OSError:
        # No writable config dir means no way to remember this happened, and a
        # prompt that cannot be remembered would appear on every single run.
        return False


def maybe_ask(earned_line: str, *, marker_dir: Path | None = None) -> bool:
    """Print the ask if this run earned it and it has never been shown.

    `earned_line` is the specific thing that just happened, in the caller's own
    words, and must reference a real result the user can see above it. Returns
    whether anything was printed, which is what the tests assert on.
    """
    if _suppressed():
        return False
    marker = (marker_dir or _config_dir()) / _MARKER_NAME
    if not _claim_once(marker):
        return False

    print()
    print(f"  {earned_line}")
    print(f"  If it is useful, a star helps other people find it: {REPO_URL}")
    print("  (shown once; OBSIDIAN_NO_STAR_PROMPT=1 disables it)")
    return True

# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
"""One place that answers "where is the toolkit's config, and what does it say".

Every half of this toolkit needs the same two answers: which file holds the
config, and what a key in it is set to. Before this module the answer was
copied into four Python files and two bash ones, each a slightly different
spelling of the same six lines, and the copies drifted: `scripts/eval/
behavior_eval.py` stopped honouring OBSIDIAN_ENV_FILE at all, so pointing it at
a second config silently kept reading the first.

Copies also go missing, which is the more expensive failure. A caller that
reads only `os.environ` finds nothing when the install wrote the config to the
file and never exported it, and then does nothing and says nothing. That is
#124, #160, #269 and #285: four releases, one bug, four places to fix it.

There is now one place. `tests/test_osb_env.py` fails when a fifth spelling
appears.

Deliberately stdlib-only. The SessionStart hook imports this and must keep
running on a machine with no third-party packages installed, so nothing here
may reach for `dotenv`. Callers that want a full dotenv load still do it; they
just ask this module where the file is.

Precedence, everywhere: a real environment variable wins over the file. The
file is what an install writes; the environment is what an operator overrides
with for one run.
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = ["config_dir", "env_file", "env_value", "vault_path"]


def config_dir() -> Path:
    """The toolkit's config directory.

    `Path.home()` is correct on Windows too: it resolves to USERPROFILE there,
    which is the same directory `scripts/platform-home.sh` resolves OSB_HOME to
    for the bash half, so both halves read one config rather than two (#242).
    """
    return Path.home() / ".config" / "obsidian-second-brain"


def env_file() -> Path:
    """The config `.env`, honouring OBSIDIAN_ENV_FILE.

    OBSIDIAN_ENV_FILE points every half of the toolkit at one file. On Windows
    it may be a native path (`C:\\Users\\...`), which Python opens as happily as
    the forward-slash form, so it is passed through untouched.
    """
    override = os.environ.get("OBSIDIAN_ENV_FILE", "").strip()
    return Path(override or (config_dir() / ".env")).expanduser()


def _file_values() -> dict[str, str]:
    """Every assignment in the config file, last one wins.

    Parsed rather than sourced, because this runs inside a SessionStart hook: a
    config file is data, and executing it would make an edited `.env` a way to
    run code at the start of every session.

    Tolerates what the bash half writes and what a hand edit leaves behind:
    leading whitespace, a `export ` prefix, CRLF line endings, `#` comments,
    and a value wrapped in single or double quotes.
    """
    values: dict[str, str] = {}
    try:
        text = env_file().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key:
            continue
        value = value.strip().rstrip("\r")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def env_value(name: str, default: str = "") -> str:
    """A config key: the environment first, then the config file, then `default`.

    An empty environment variable counts as unset, so `OBSIDIAN_VAULT_PATH=`
    left behind by a half-finished shell profile does not shadow a working
    value in the file.
    """
    from_env = os.environ.get(name, "").strip()
    if from_env:
        return from_env
    return _file_values().get(name, "").strip() or default


def vault_path() -> str:
    """The configured vault path, or "" when there is none.

    The single most-read key in the toolkit, and the one whose absence used to
    be silent. Callers still decide what to do with "" - the hook stays quiet,
    the research toolkit exits with instructions - but they all ask the same
    question the same way.
    """
    return env_value("OBSIDIAN_VAULT_PATH")

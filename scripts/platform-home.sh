#!/bin/bash
# SPDX-FileCopyrightText: 2026 Eugeniu Ghelbur and contributors
# SPDX-License-Identifier: MIT
# Author: Eugeniu Ghelbur (AI Automation Engineer, AI Tooling Engineer, AI Educator), https://github.com/eugeniughelbur/obsidian-second-brain
# Questions or consulting: e.ghelbur@gmail.com | https://www.linkedin.com/in/eugeniu-ghelbur/ | More: https://theaioperator.io | https://x.com/eugeniu_ghelbur
# Shared home resolution for the bash half of the toolkit. `source` this file,
# then call osb_platform_home: it sets OSB_WIN (1 on a Windows shell: Git Bash,
# MSYS2, Cygwin; 0 elsewhere) and OSB_HOME.
#
# Home for config and Claude Code state. On Windows shells that is USERPROFILE,
# which is what Python's Path.home() and Claude Code resolve ~ to there; HOME can
# point at another drive (a corporate roaming home) and would split the config
# between the bash and Python halves (#242). Elsewhere HOME is the home.
#
# Sourced by install.sh, update.sh, scripts/setup.sh, scripts/run-command.sh and
# integrations/telegram-journal/setup.sh. Two files carry an inline copy of the
# case block on purpose, because they must stay standalone: hooks/validate-ai-first.sh
# (copied into other harnesses' hook systems by hand) and scripts/quick-install.sh
# (curl | bash, before any checkout exists). tests/test_platform_home.py fails
# when one of the three copies drifts. Uses bash 3.2 features only (macOS ships 3.2).
osb_platform_home() {
  case "$(uname -s 2>/dev/null)" in
    MINGW*|MSYS*|CYGWIN*)
      OSB_WIN=1
      OSB_HOME="${USERPROFILE:-$HOME}"
      OSB_HOME="$(cygpath -u "$OSB_HOME" 2>/dev/null || printf '%s' "${OSB_HOME//\\//}")" ;;
    *) OSB_WIN=0; OSB_HOME="$HOME" ;;
  esac
}

# Where the toolkit's config .env lives, for the bash half. Call after
# osb_platform_home; sets OSB_ENV_FILE. OBSIDIAN_ENV_FILE overrides it, and on a
# Windows shell the result is normalized to forward slashes so the same string
# opens in bash and in Python.
#
# The Python half asks scripts/osb_env.py the same question. The two must agree:
# an install writes the vault path here with bash and every command reads it back
# with Python, so a disagreement is a config that exists and is never found -
# #124, #160, #269 and #285, one bug, four releases. tests/test_osb_env.py checks
# that both halves resolve the same file, and fails when a new inline copy of
# this line appears.
osb_env_file() {
  # Called before osb_platform_home, $OSB_HOME is empty and the default becomes
  # a relative path that resolves against whatever the caller's cwd happens to
  # be: a config file found or not found depending on where you ran the script
  # from. Resolving home here instead is what this whole helper is for.
  [ -n "$OSB_HOME" ] || osb_platform_home
  OSB_ENV_FILE="${OBSIDIAN_ENV_FILE:-$OSB_HOME/.config/obsidian-second-brain/.env}"
  if [[ "$OSB_WIN" = 1 ]]; then OSB_ENV_FILE="${OSB_ENV_FILE//\\//}"; fi
}

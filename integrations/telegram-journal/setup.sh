#!/usr/bin/env bash
# setup.sh - one-command installer for the Telegram journal bot.
#
# Creates the locked config, installs the background poller (launchd on macOS,
# cron line printed on Linux), and does a test run. Re-runnable: it skips a config
# that already exists, so running it again just reinstalls/reloads the job.
#
#   cd integrations/telegram-journal && ./setup.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SCRIPT="$HERE/telegram_journal.py"
CONFIG_DIR="$HOME/.config/obsidian-second-brain"
CONFIG="$CONFIG_DIR/telegram_journal.env"
UV="$(command -v uv || true)"

echo "== Telegram journal bot setup =="

if [ -z "$UV" ]; then
  echo "uv not found - install it first (https://docs.astral.sh/uv/), then re-run." >&2
  exit 1
fi

# 1. Config (skip if it already exists).
mkdir -p "$CONFIG_DIR"
if [ -f "$CONFIG" ]; then
  echo "Config already exists at $CONFIG - leaving it (edit by hand to change values)."
else
  echo "Creating your config. Leave optional fields blank to skip."
  read -r -p "  Telegram bot token (from @BotFather): " BOT
  read -r -p "  Transcribe voice locally (on-box, no OpenAI key)? [y/N]: " LOCAL
  if [[ "$LOCAL" =~ ^[Yy] ]]; then
    BACKEND=local
    OAI=""
    echo "    Local Whisper: needs the 'whisper' CLI (pip install openai-whisper) and ffmpeg on PATH."
    read -r -p "    Whisper model size (tiny|base|small|medium|large) [base]: " WMODEL
    WMODEL="${WMODEL:-base}"
  else
    BACKEND=openai
    WMODEL=base
    read -r -p "  OpenAI API key (voice transcription): " OAI
  fi
  read -r -p "  Anthropic API key (text/image - needs billing): " ANT
  read -r -p "  Absolute path to your Obsidian vault: " VP
  read -r -p "  Your name (optional, routes self-notes to daily): " OWN
  read -r -p "  Transcription proper-noun hints (optional, comma-separated): " HINT
  read -r -p "  Path to your obsidian-second-brain clone (optional, for link routing) [$HOME/obsidian-second-brain]: " REPO
  REPO="${REPO:-$HOME/obsidian-second-brain}"
  ( umask 077; cat > "$CONFIG" <<EOF
TELEGRAM_JOURNAL_BOT_TOKEN=$BOT
OPENAI_API_KEY=$OAI
TRANSCRIBE_BACKEND=$BACKEND
WHISPER_LOCAL_MODEL=$WMODEL
ANTHROPIC_API_KEY=$ANT
VAULT_PATH=$VP
VAULT_OWNER=$OWN
WHISPER_HINT=$HINT
OBSIDIAN_SKILL_REPO=$REPO
UV_BIN=$UV
EOF
  )
  chmod 600 "$CONFIG"
  echo "Wrote $CONFIG (chmod 600 - readable only by you)."
fi

# 2. Test run (one poll). Send your bot a message first so it has something to reply to.
echo "Test run (send your bot any message first so it can reply)..."
if "$UV" run "$SCRIPT"; then echo "  test run OK"; else echo "  test run returned an error - check the config above"; fi

# 3. Scheduler.
if [ "$(uname -s)" = "Darwin" ]; then
  PLIST="$HOME/Library/LaunchAgents/com.user.telegram-journal.plist"
  sed -e "s#UV_PATH#$UV#g" -e "s#SCRIPT_PATH#$SCRIPT#g" -e "s#HOME_DIR#$HOME#g" \
      "$HERE/com.user.telegram-journal.plist.example" > "$PLIST"
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load -w "$PLIST"
  echo "Installed + loaded launchd job ($PLIST) - polls every 60s."
else
  echo "Linux: add this to your crontab (crontab -e) to poll every minute:"
  echo "  * * * * * $UV run $SCRIPT >> $HOME/telegram-journal.log 2>&1"
fi

echo "Done. Send your bot a voice note / photo / link and it lands in your vault."
echo "Back at your laptop, run /obsidian-catchup to process what you captured."

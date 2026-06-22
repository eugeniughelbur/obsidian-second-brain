# Telegram journal -> Obsidian

Capture into your vault from your phone, hands-free. Send a **voice note**, **text**, or
**image** to a private Telegram bot, and a small background poller on your computer turns
it into a clean, AI-first entry in your Obsidian vault - then replies to confirm.

It pairs with [obsidian-second-brain](../../README.md): the vault it writes into follows
the AI-first note rules, so future-Claude can read what you captured.

## What it does

- **Voice / audio** -> transcribed with Whisper -> tidied by Claude -> appended to today's
  daily note under `## Voice journal`. Transcription runs on the OpenAI Whisper API by
  default, or fully on-box with no API key - see [Local transcription](#local-transcription).
- **Text** -> tidied by Claude -> same daily note. (Bot commands like `/start` are ignored.)
- **Image** -> Claude vision reads it, decides where it belongs (a person note, a project
  note, finance, or today's note), saves the file into `wiki/attachments/`, embeds it, and
  replies where it went. Reply `move <where>` (e.g. `move daily`, `move Acme Corp`) to
  re-file the last image.
- **PDF / document** -> Claude reads the PDF, writes an AI-first literature note (summary,
  key points, why it matters) to `Research/Papers/`, saves + embeds the file, and links it
  from today's note.
- **Link** (YouTube / X / article) -> dispatched to the matching obsidian-second-brain
  research command (`/youtube`, `/x-read`, `/research`), which saves its own AI-first note.
  (Requires `OBSIDIAN_SKILL_REPO` set to your clone of this repo.)

Two behaviors worth knowing:
- **Fill-links:** when a capture references a `[[person/company/project]]` that has no note
  yet, the bot creates that note *filled with real content* (typed + filed; unknowns marked
  TBD, nothing fabricated) - never an empty link. It only ever creates new notes.
- **Catchup queue:** every capture is also logged to a `catchup.md` queue in the vault. Back
  at your laptop, run **`/obsidian-catchup`** to review and integrate the captures together
  (integrate / keep / discard), on your schedule. Pull, not push - nothing is processed
  autonomously.

It only ever reads your messages and writes notes. Nothing is deleted. If the computer is
off or offline, Telegram holds the message (up to ~24h) and it is processed when you are
back online.

## Requirements

- A Telegram bot token (free, from @BotFather)
- For voice: either an OpenAI API key (default), or a local Whisper setup with no key
  (`pip install openai-whisper` + ffmpeg) - see [Local transcription](#local-transcription)
- An Anthropic API key with billing (text tidy + image reading)
- [`uv`](https://docs.astral.sh/uv/) to run the script (handles the one dependency itself)
- A scheduler: macOS `launchd` (template included) or Linux `cron`

## Setup

**Fast path:** create the bot (step 1 below) to get a token, then run the installer - it prompts for your keys, writes the locked config, installs the background job (launchd on macOS / prints a cron line on Linux), and does a test run:

```bash
cd integrations/telegram-journal && ./setup.sh
```

Re-runnable (it skips an existing config). The manual steps below are the same thing by hand if you prefer.

**1. Create the bot.** In Telegram, message **@BotFather**, send `/newbot`, pick a name and a
username ending in `bot`. Copy the token it gives you.

**2. Fill the config.** Copy the template to the location the script reads, fill it in, and
lock its permissions so only you can read it:

```bash
mkdir -p ~/.config/obsidian-second-brain
cp telegram_journal.env.example ~/.config/obsidian-second-brain/telegram_journal.env
# edit the file: paste the bot token, your OPENAI_API_KEY, ANTHROPIC_API_KEY,
# your VAULT_PATH, and optionally VAULT_OWNER (your name)
chmod 600 ~/.config/obsidian-second-brain/telegram_journal.env
```

The script contains no secrets - it reads them from this file. **Never commit the
filled-in `telegram_journal.env`** (the included `.gitignore` blocks it).

**3. Test it.** Send your bot a message first (so it can reply to you), then run once:

```bash
uv run telegram_journal.py
```

You should see it process the message and reply on Telegram.

**4. Run it on a schedule.**

- **macOS (launchd):** edit `com.user.telegram-journal.plist.example` (replace `UV_PATH`,
  `SCRIPT_PATH`, `HOME_DIR` - see the comment inside), copy it to
  `~/Library/LaunchAgents/com.user.telegram-journal.plist`, then:

  ```bash
  launchctl load -w ~/Library/LaunchAgents/com.user.telegram-journal.plist
  ```

- **Linux (cron):** `crontab -e` and add a line that runs the script every minute (see the
  comment in the plist template for the exact form).

## Usage

- **Voice:** hold the mic, talk, release. (Great while walking.)
- **Text:** just type.
- **Image:** send a photo, optionally with a caption. It reads the image (including text
  inside it) and files it. If it guesses the wrong place, reply `move <where>`.

## Where things land

- Voice / text -> `wiki/daily/YYYY-MM-DD.md` under `## Voice journal`
- Images -> the chosen note (person/project/finance/daily) under `## Captured`, with the
  file in `wiki/attachments/`

Image routing targets only **notes that already exist**; if it is unsure it parks the entry
in today's note and tells you - so it never creates junk notes.

## Local transcription

Want voice notes to stay on your machine (no OpenAI key, nothing leaves the box)? Switch
the transcription backend to local Whisper - the same `openai-whisper` engine
`/obsidian-ingest` uses for audio. The installer asks; to set it by hand, add these to your
config and clear the OpenAI key:

```bash
TRANSCRIBE_BACKEND=local
WHISPER_LOCAL_MODEL=base   # tiny | base | small | medium | large
# OPENAI_API_KEY=          # not needed in local mode
```

One-time install of the engine (and ffmpeg, which Whisper uses to decode the audio):

```bash
pip install openai-whisper
# macOS:  brew install ffmpeg
# Debian/Ubuntu:  sudo apt-get install ffmpeg
```

Notes:
- First run with a given model downloads its weights (a few hundred MB for `base`), then
  it is cached. Bigger models are more accurate but slower; `base` is a good default, and
  on a CPU-only always-on server `tiny`/`base` keep each note fast.
- `WHISPER_HINT` still works (it is passed as Whisper's `--initial_prompt`).
- If the `whisper` binary is not on the poller's PATH (common under launchd/cron), set
  `WHISPER_BIN` to its absolute path.
- Anthropic is still used for the text tidy + image reading; only the voice step goes local.

## Cost

OpenAI backend: roughly per message, one Whisper transcription (voice only) plus one Claude
Haiku call (tidy or image read). Small - cents per day for normal personal use. You pay your
own API usage. Local backend: voice transcription is free (runs on your hardware); only the
Claude Haiku tidy/image call costs anything.

## Security

- Secrets live only in `~/.config/obsidian-second-brain/telegram_journal.env` (chmod 600),
  never in the script or this repo.
- Keep your bot private (do not share its username/token); it is a personal capture inbox.
- Treat the bot token like a password - if it leaks, revoke it in @BotFather and reissue.

## Notes / limits

- Image routing uses a vision model's best guess. The `move` reply is the correction path.
- It catches voice/text/image; other message types (stickers, files) get a "not supported
  yet" reply.
- Vault layout assumed: `wiki/daily/`, `wiki/entities/` (people/companies), `wiki/projects/`,
  `wiki/attachments/` - the obsidian-second-brain default. Adjust the paths in the script if
  your vault differs.

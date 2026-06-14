# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31"]
# ///
"""
telegram_journal.py - voice / text / image capture from Telegram into an Obsidian vault.

A small background poller (run by launchd/cron every ~60s). Each run polls a Telegram
bot for new messages (offset-tracked, so nothing is processed twice) and handles them:

  - voice / audio -> OpenAI Whisper transcription -> tidy -> today's daily note
  - text          -> tidy -> today's daily note (bot commands like /start are ignored)
  - image (photo) -> a vision model reads it, decides where it belongs (a person note,
                     a project note, finance, or today's note), saves the file into the
                     vault, embeds it, and replies where it went. Reply "move <where>"
                     to re-file the last image.

It only ever READS your messages and WRITES notes into your vault. Nothing is deleted.

Config/secrets live in a separate file (default
~/.config/obsidian-second-brain/telegram_journal.env), as KEY=VALUE lines:
  TELEGRAM_JOURNAL_BOT_TOKEN   - from @BotFather
  OPENAI_API_KEY               - used for Whisper voice transcription
  ANTHROPIC_API_KEY            - used to tidy text and read images (Claude)
  VAULT_PATH                   - absolute path to your Obsidian vault
  VAULT_OWNER                  - (optional) your name, so things about you route to "daily"
This script contains NO secrets and is safe to commit and share.
"""
import os
import re
import sys
import json
import base64
import datetime
import pathlib

import requests

CONFIG = pathlib.Path(
    os.environ.get("TELEGRAM_JOURNAL_CONFIG", "")
    or pathlib.Path.home() / ".config/obsidian-second-brain/telegram_journal.env"
)
STATE = pathlib.Path.home() / ".config/obsidian-second-brain/telegram_journal_offset"
LASTIMG = pathlib.Path.home() / ".config/obsidian-second-brain/telegram_journal_lastimage.json"


def load_config():
    if CONFIG.exists():
        for line in CONFIG.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()  # config file is the source of truth


load_config()
TOKEN = os.environ.get("TELEGRAM_JOURNAL_BOT_TOKEN", "")
OPENAI = os.environ.get("OPENAI_API_KEY", "")
ANTHROPIC = os.environ.get("ANTHROPIC_API_KEY", "")
OWNER = os.environ.get("VAULT_OWNER", "").strip()
VAULT = pathlib.Path(os.environ.get("VAULT_PATH", "")).expanduser()
API = f"https://api.telegram.org/bot{TOKEN}"
FILE_API = f"https://api.telegram.org/file/bot{TOKEN}"

MEDIA_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".webp": "image/webp", ".gif": "image/gif"}

TIDY_PROMPT = """You are turning a spoken/typed journal note into a clean entry for an \
AI-first Obsidian daily note (a future AI assistant will read it, not just a human).

Raw note:
\"\"\"{raw}\"\"\"

Write a tight markdown entry. Rules:
- Start with one short summary line.
- Then add short bullet lines ONLY for things actually mentioned, choosing from:
  sleep, energy/mood, health/exercise, faith/prayer, food, work done, decisions,
  people met (wrap names as [[Name]]), money, plans.
- Do NOT invent anything that was not said. Leave out what was not mentioned.
- Plain ASCII only: use ' - ' not a long dash, straight quotes, no emoji.
- No preamble, no "here is". Output only the entry."""

ROUTE_PROMPT = """You file an image a user sent into their personal Obsidian vault.
{owner_line}The user's caption (may be empty): "{caption}"

Look at the image and reply with ONLY a JSON object, nothing else:
{{
 "description": "1-2 sentence description; wrap notable real people, companies, and projects in [[double brackets]], e.g. [[Cisco]], [[Jane Doe]]",
 "extracted_text": "important readable text in the image, or empty string",
 "kind": "chat-screenshot | document | diagram | ui-screenshot | photo | receipt | other",
 "target": "daily | person:<Name> | project:<Name> | finance | idea",
 "why": "short reason for the target",
 "confidence": "high | medium | low"
}}
Rules: prefer "daily" when unsure. Use person:/project: ONLY if the image clearly
relates to one specific named person or project. Anything addressed TO the vault owner
or about them personally goes to "daily", never a person note for the owner.
ASCII only in your output."""


def tg(method, **params):
    r = requests.get(f"{API}/{method}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def reply(chat_id, text):
    if not chat_id:
        return
    try:
        tg("sendMessage", chat_id=chat_id, text=text)
    except Exception:
        pass


def download(file_id):
    info = tg("getFile", file_id=file_id)
    path = info["result"]["file_path"]
    data = requests.get(f"{FILE_API}/{path}", timeout=120).content
    return data, os.path.splitext(path)[1].lower()


def transcribe(file_id):
    audio, suffix = download(file_id)
    suffix = suffix or ".oga"
    files = {"file": (f"voice{suffix}", audio), "model": (None, "whisper-1")}
    r = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI}"},
        files=files,
        timeout=120,
    )
    r.raise_for_status()
    return r.json().get("text", "").strip()


def llm(content, max_tokens=700):
    """Claude (Anthropic) message. `content` is a string (text) or a list (vision)."""
    body = {"model": "claude-haiku-4-5", "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": content}]}
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": ANTHROPIC, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
        json=body, timeout=90,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()


def tidy(raw):
    return llm(TIDY_PROMPT.format(raw=raw))


def describe_and_route(img_bytes, media_type, caption):
    b64 = base64.b64encode(img_bytes).decode()
    owner_line = f"The vault owner is {OWNER}. " if OWNER else ""
    prompt = ROUTE_PROMPT.format(owner_line=owner_line, caption=caption or "")
    content = [
        {"type": "text", "text": prompt},
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
    ]
    text = llm(content, max_tokens=600)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON from vision model")
    return json.loads(m.group(0))


# ---------- vault writing ----------

def find_note(folder, name):
    d = VAULT / folder
    if not d.exists():
        return None
    name_l = name.strip().lower()
    cands = list(d.glob("*.md"))
    for p in cands:
        if p.stem.lower() == name_l:
            return p
    for p in cands:
        s = p.stem.lower()
        if name_l and (name_l in s or s in name_l):
            return p
    return None


def daily_note(when):
    return VAULT / "wiki" / "daily" / f"{when.strftime('%Y-%m-%d')}.md"


def resolve_target(target, when):
    """Return (note_path, human_label, fell_back). Routes to EXISTING notes only;
    anything unknown falls back to today's daily note."""
    t = (target or "daily").strip()
    low = t.lower()
    if low.startswith("person:"):
        p = find_note("wiki/entities", t.split(":", 1)[1])
        if p:
            return p, p.stem, False
    elif low.startswith("project:"):
        p = find_note("wiki/projects", t.split(":", 1)[1])
        if p:
            return p, p.stem, False
    elif low == "finance":
        p = find_note("wiki/projects", "Personal Finance")
        if p:
            return p, p.stem, False
    return daily_note(when), "today's note", (low not in ("daily", "idea"))


def ensure_daily(note, when):
    if note.exists():
        return
    note.parent.mkdir(parents=True, exist_ok=True)
    day = when.strftime("%Y-%m-%d")
    dow = when.strftime("%A")
    note.write_text(
        f"---\ntype: daily\ndate: {day}\nday-of-week: {dow}\ntags:\n  - daily\n"
        f"ai-first: true\n---\n\n## For future Claude\n\n"
        f"Daily note for {day} ({dow}). Journal entries captured via the Telegram journal bot.\n",
        encoding="utf-8",
    )


def append_under(note, header, block, when):
    """Insert block under `header` (newest first). Creates the daily note + section if needed."""
    if not note.exists():
        ensure_daily(note, when)
    text = note.read_text(encoding="utf-8")
    if header in text:
        idx = text.index(header) + len(header)
        nl = text.index("\n", idx)
        text = text[: nl + 1] + "\n" + block + text[nl + 1:]
        note.write_text(text, encoding="utf-8")
    else:
        note.write_text(text.rstrip() + f"\n\n{header}\n\n{block}", encoding="utf-8")


def remove_block(note, block):
    if not note.exists():
        return
    text = note.read_text(encoding="utf-8")
    if block in text:
        text = text.replace(block, "")
        text = re.sub(r"\n{3,}", "\n\n", text)
        note.write_text(text, encoding="utf-8")


def save_image(img_bytes, ext, when):
    folder = VAULT / "wiki" / "attachments"
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{when.strftime('%Y-%m-%d-%H%M%S')}-journal{ext or '.jpg'}"
    (folder / fname).write_bytes(img_bytes)
    return fname


def build_image_block(ts, caption, info, fname):
    parts = []
    if caption:
        parts.append(caption.strip())
    desc = (info.get("description") or "").strip()
    if desc:
        parts.append(desc)
    extracted = (info.get("extracted_text") or "").strip()
    if extracted:
        parts.append("> " + extracted.replace("\n", "\n> "))
    parts.append(f"![[{fname}]]")
    return f"### {ts} (image)\n\n" + "\n\n".join(parts) + "\n"


# ---------- last-image state (for "move") ----------

def load_lastimg():
    try:
        return json.loads(LASTIMG.read_text())
    except Exception:
        return {}


def save_lastimg(d):
    LASTIMG.write_text(json.dumps(d))


def handle_move(chat_id, dest_text, when):
    state = load_lastimg().get(str(chat_id))
    if not state:
        return False  # no recent image; treat as a normal journal note
    note_path = pathlib.Path(state["note_path"])
    block = state["block"]
    d = dest_text.strip().lower()
    if "financ" in d:
        target = "finance"
    elif "daily" in d or "today" in d:
        target = "daily"
    elif find_note("wiki/entities", dest_text):
        target = f"person:{dest_text}"
    elif find_note("wiki/projects", dest_text):
        target = f"project:{dest_text}"
    else:
        reply(chat_id, f"could not find a note called '{dest_text.strip()}' - left it where it is")
        return True
    new_note, label, _ = resolve_target(target, when)
    remove_block(note_path, block)
    append_under(new_note, "## Captured", block, when)
    st = load_lastimg()
    st[str(chat_id)]["note_path"] = str(new_note)
    save_lastimg(st)
    reply(chat_id, f"moved image to {label} ({new_note.name})")
    return True


def get_offset():
    try:
        return int(STATE.read_text().strip())
    except Exception:
        return 0


def set_offset(n):
    STATE.write_text(str(n))


def handle_photo(msg, chat_id, when):
    caption = (msg.get("caption") or "").strip()
    img_bytes, ext = download(msg["photo"][-1]["file_id"])
    media_type = MEDIA_TYPES.get(ext, "image/jpeg")
    reply(chat_id, "got the image, looking at it...")
    try:
        info = describe_and_route(img_bytes, media_type, caption)
    except Exception as e:
        print(f"vision failed: {e}", file=sys.stderr)
        info = {"description": caption or "image", "target": "daily", "confidence": "low"}
    fname = save_image(img_bytes, ext, when)
    note, label, fell_back = resolve_target(info.get("target", "daily"), when)
    block = build_image_block(when.strftime("%H:%M"), caption, info, fname)
    append_under(note, "## Captured", block, when)
    st = load_lastimg()
    st[str(chat_id)] = {"note_path": str(note), "block": block, "when": when.isoformat()}
    save_lastimg(st)
    note_word = note.name
    if fell_back:
        reply(chat_id, f"wasn't sure where this goes - parked it in {note_word}. "
                       f"reply: move <person/project/finance>")
    else:
        reply(chat_id, f"saved image to {label} ({note_word}). wrong place? reply: move <where>")


def main():
    if not (TOKEN and VAULT.exists()):
        print("missing TELEGRAM_JOURNAL_BOT_TOKEN or VAULT_PATH", file=sys.stderr)
        sys.exit(1)

    offset = get_offset()
    data = tg("getUpdates", offset=offset, timeout=0, allowed_updates=json.dumps(["message"]))
    updates = data.get("result", [])
    if not updates:
        return

    last = offset
    for u in updates:
        last = u["update_id"] + 1
        msg = u.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        when = datetime.datetime.now()
        try:
            if "photo" in msg:
                handle_photo(msg, chat_id, when)
                continue

            if "voice" in msg:
                reply(chat_id, "got it, transcribing...")
                raw = transcribe(msg["voice"]["file_id"])
                kind = "voice"
            elif "audio" in msg:
                raw = transcribe(msg["audio"]["file_id"])
                kind = "voice"
            elif "text" in msg:
                raw = msg["text"].strip()
                kind = "text"
                if raw.startswith("/"):
                    if raw.split()[0] in ("/start", "/help"):
                        reply(chat_id, "Send me a voice note, text, or image anytime and I'll save it.")
                    continue
                if raw.lower().startswith("move"):
                    dest = re.sub(r"^\s*move\b[:\s]*", "", raw, flags=re.IGNORECASE)
                    if handle_move(chat_id, dest, when):
                        continue
            else:
                reply(chat_id, "I can save voice notes, text, and images - that type isn't supported yet")
                continue

            if not raw:
                reply(chat_id, "could not read that one - try again")
                continue
            try:
                entry = tidy(raw)
            except Exception:
                entry = raw  # never lose the words, even if formatting fails
            note = daily_note(when)
            append_under(note, "## Voice journal",
                         f"### {when.strftime('%H:%M')} ({kind})\n\n{entry}\n", when)
            reply(chat_id, f"saved to {note.name}")
        except Exception as e:
            reply(chat_id, f"error: {e}")
            print(f"error on update {u['update_id']}: {e}", file=sys.stderr)

    set_offset(last)


if __name__ == "__main__":
    main()

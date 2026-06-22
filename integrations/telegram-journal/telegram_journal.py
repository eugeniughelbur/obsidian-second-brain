# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.31"]
# ///
"""
telegram_journal.py - voice / text / image journaling from Telegram into the Obsidian vault.

Run by launchd every 60s. Each run polls the journal bot for new messages
(offset-tracked, no reprocessing) and handles them:

  - voice / audio -> Whisper transcription (OpenAI API by default, or fully on-box
                     via local openai-whisper - set TRANSCRIBE_BACKEND=local) -> tidy
                     -> today's daily note
  - text          -> tidy -> today's daily note (bot commands like /start are ignored)
  - image (photo) -> Claude vision reads it, decides where it belongs (a person note,
                     a project note, finance, or today's note), saves the file into the
                     vault, embeds it, and replies where it went. Reply "move <where>"
                     to re-file the last image.

Config/secrets come from ~/.config/obsidian-second-brain/telegram_journal.env
(KEY=VALUE lines): TELEGRAM_JOURNAL_BOT_TOKEN, OPENAI_API_KEY (only when
TRANSCRIBE_BACKEND=openai, the default), ANTHROPIC_API_KEY, VAULT_PATH
This file holds no secrets and is safe to read or share.
"""
import os
import re
import sys
import json
import base64
import datetime
import pathlib
import subprocess

import requests

CONFIG = pathlib.Path.home() / ".config/obsidian-second-brain/telegram_journal.env"
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
OWNER = os.environ.get("VAULT_OWNER", "").strip()  # so notes about the owner route to daily
WHISPER_HINT = os.environ.get("WHISPER_HINT", "")  # proper nouns to bias transcription
# Voice transcription backend: "openai" (default, uses OPENAI_API_KEY) or "local"
# (on-box openai-whisper CLI, no key needed - needs `whisper` + ffmpeg on PATH).
TRANSCRIBE_BACKEND = os.environ.get("TRANSCRIBE_BACKEND", "openai").strip().lower()
WHISPER_LOCAL_MODEL = os.environ.get("WHISPER_LOCAL_MODEL", "base").strip()  # tiny|base|small|medium|large
WHISPER_BIN = os.environ.get("WHISPER_BIN", "whisper").strip()  # path to the whisper CLI if not on PATH
VAULT = pathlib.Path(os.environ.get("VAULT_PATH", "")).expanduser()
SKILL_REPO = pathlib.Path(os.environ.get(
    "OBSIDIAN_SKILL_REPO", "~/obsidian-second-brain")).expanduser()
UV_BIN = os.environ.get("UV_BIN", "uv")  # set to an absolute path if uv is not on the launchd/cron PATH
URL_RE = re.compile(r"https?://[^\s>]+")
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
The user's caption (may be empty): "{caption}"

Look at the image and reply with ONLY a JSON object, nothing else:
{{
 "description": "1-2 sentence description. Use [[double brackets]] ONLY for a specific named person or company that deserves its own note (e.g. [[Cisco]], [[Jane Doe]]); never link generic concepts or common terms - leave those plain.",
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
    if TRANSCRIBE_BACKEND == "local":
        return transcribe_local(audio, suffix)
    return transcribe_openai(audio, suffix)


def transcribe_openai(audio, suffix):
    """Transcribe via the OpenAI Whisper API (needs OPENAI_API_KEY)."""
    files = {"file": (f"voice{suffix}", audio), "model": (None, "whisper-1")}
    if WHISPER_HINT:
        files["prompt"] = (None, WHISPER_HINT)
    r = requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {OPENAI}"},
        files=files,
        timeout=120,
    )
    r.raise_for_status()
    return r.json().get("text", "").strip()


def transcribe_local(audio, suffix):
    """Transcribe on-box with the openai-whisper CLI - no API key, nothing leaves the
    machine. Needs `whisper` (pip install openai-whisper) and ffmpeg on PATH. Same engine
    /obsidian-ingest uses for local audio. WHISPER_LOCAL_MODEL picks the model size and
    WHISPER_HINT biases spelling of proper nouns."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src = pathlib.Path(tmp) / f"voice{suffix}"
        src.write_bytes(audio)
        cmd = [WHISPER_BIN, str(src), "--model", WHISPER_LOCAL_MODEL,
               "--output_format", "txt", "--output_dir", tmp, "--fp16", "False"]
        if WHISPER_HINT:
            cmd += ["--initial_prompt", WHISPER_HINT]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            raise RuntimeError(
                f"local transcription needs the '{WHISPER_BIN}' CLI - "
                "pip install openai-whisper (and install ffmpeg), or set WHISPER_BIN")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"whisper failed: {(e.stderr or '').strip()[-300:]}")
        out = pathlib.Path(tmp) / f"{src.stem}.txt"
        return out.read_text().strip() if out.exists() else ""


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
    content = [
        {"type": "text", "text": ROUTE_PROMPT.format(caption=caption or "")},
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
    """Append block at the END of the `header` section (newest last, chronological).
    Creates the daily note + section if needed."""
    if not note.exists():
        ensure_daily(note, when)
    text = note.read_text(encoding="utf-8")
    block = block.rstrip() + "\n"
    if header not in text:
        note.write_text(text.rstrip() + f"\n\n{header}\n\n{block}", encoding="utf-8")
        return
    nl = text.index("\n", text.index(header))   # end of the header line
    nxt = text.find("\n## ", nl)                 # start of the next top-level section
    if nxt == -1:
        new_text = text.rstrip() + "\n\n" + block
    else:
        new_text = text[:nxt].rstrip() + "\n\n" + block.rstrip() + "\n" + text[nxt:]
    note.write_text(new_text, encoding="utf-8")


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
    fill_links(block, when, caption or info.get("description", ""))
    queue_catchup("image", caption or info.get("description", ""), when, f"[[{note.stem}]]")
    st = load_lastimg()
    st[str(chat_id)] = {"note_path": str(note), "block": block, "when": when.isoformat()}
    save_lastimg(st)
    note_word = note.name
    if fell_back:
        reply(chat_id, f"wasn't sure where this goes - parked it in {note_word}. "
                       f"reply: move <person/project/finance>")
    else:
        reply(chat_id, f"saved image to {label} ({note_word}). wrong place? reply: move <where>")


PDF_PROMPT = """This PDF was saved by the user to their AI-first Obsidian vault. Write a note \
for future-Claude retrieval.

Output (plain ASCII, no emoji):
TITLE: <short descriptive title, max ~10 words>

## Summary

<one tight paragraph: what this document is and its core content/claim>

## Key points

- <the most important points, as bullets>

## Why it matters

<1-2 lines; omit this whole section if not clear>

Use [[double brackets]] VERY sparingly - ONLY for a specific named person or a specific company/product that clearly deserves its own note. Do NOT link generic concepts, techniques, methods, standards, or common terms (e.g. prompt engineering, Unix pipelines, multi-pass compilation, EU AI Act) - leave all of those as plain text. When in doubt, plain text. Output only the above, no preamble."""


def handle_link(url, chat_id, when):
    """Dispatch a shared link to the matching obsidian-second-brain research command,
    which reads its own config (keys + vault) and saves the AI-first note itself."""
    host = url.lower()
    if "youtube.com" in host or "youtu.be" in host:
        module, label = "scripts.research.youtube_extract", "youtube"
    elif "x.com/" in host or "twitter.com/" in host:
        module, label = "scripts.research.x_read", "x-read"
    else:
        module, label = "scripts.research.research", "research"
    reply(chat_id, f"got the link - running {label}...")
    try:
        proc = subprocess.run(
            [UV_BIN, "run", "-m", module, url],
            cwd=str(SKILL_REPO), capture_output=True, text=True, timeout=300, env=os.environ,
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        saved = re.search(r"(Research/[^\n]+\.md)", out)
        if proc.returncode == 0:
            reply(chat_id, f"{label} done" + (f" - saved {saved.group(1).strip()}" if saved else ""))
            queue_catchup(label, url, when, saved.group(1).strip() if saved else "")
        else:
            reply(chat_id, f"{label} failed: {out.strip()[-300:]}")
    except Exception as e:
        reply(chat_id, f"{label} error: {e}")


def handle_document(msg, chat_id, when):
    doc = msg["document"]
    name = doc.get("file_name", "document")
    mime = doc.get("mime_type", "")
    if not (mime == "application/pdf" or name.lower().endswith(".pdf")):
        reply(chat_id, "I can read PDFs - other document types aren't supported yet")
        return
    reply(chat_id, "got the PDF, reading it...")
    data, _ = download(doc["file_id"])

    # save the file into the vault
    att = VAULT / "wiki" / "attachments"
    att.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name) or "document.pdf"
    fname = f"{when.strftime('%Y-%m-%d-%H%M%S')}-{safe}"
    (att / fname).write_bytes(data)

    # read it with Claude
    try:
        b64 = base64.b64encode(data).decode()
        content = [
            {"type": "document",
             "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
            {"type": "text", "text": PDF_PROMPT},
        ]
        body = llm(content, max_tokens=1500)
    except Exception as e:
        print(f"pdf read failed: {e}", file=sys.stderr)
        body = f"TITLE: {name}\n\n(Could not read the PDF automatically - file saved for later.)"

    title = name
    mt = re.match(r"\s*TITLE:\s*(.+)", body)
    if mt:
        title = mt.group(1).strip()
        body = body[mt.end():].lstrip()

    notes_dir = VAULT / "Research" / "Papers"
    notes_dir.mkdir(parents=True, exist_ok=True)
    slug = (re.sub(r"[^A-Za-z0-9 ._-]+", "", title)[:80].strip() or "document")
    note = notes_dir / f"{when.strftime('%Y-%m-%d')} - {slug}.md"
    fm = (f"---\ntype: literature\ndate: {when.strftime('%Y-%m-%d')}\n"
          f"time: {when.strftime('%H:%M')}\nsource: \"{name}\"\n"
          f"tags:\n  - literature\n  - pdf\n  - telegram-capture\nai-first: true\n---\n\n")
    note.write_text(fm + body.rstrip() + f"\n\n![[{fname}]]\n", encoding="utf-8")
    # also leave a pointer in today's daily note so the day's timeline is complete
    pointer = f"### {when.strftime('%H:%M')} (pdf)\n\n[[{note.stem}|{title}]] - saved to Research/Papers.\n"
    append_under(daily_note(when), "## Captured", pointer, when)
    reply(chat_id, f"saved PDF note: {note.name} (linked in today's note)")
    fill_links(body, when, title)
    queue_catchup("pdf", title, when, f"[[{note.stem}]]")


# ---------- self-improving: fill the notes the bot links to ----------

STUB_PROMPT = """A note in an AI-first Obsidian vault links to [[{name}]] but that note does \
not exist yet. Write its content.

Context where it was mentioned:
\"\"\"{context}\"\"\"

Reply with ONLY a JSON object:
{{
 "type": "person | company | project | concept | stub",
 "body": "2-4 sentence note body for future-Claude: what or who {name} is, from the context plus what you reliably know. Mark anything uncertain as TBD. Do NOT invent specific facts (dates, numbers, titles, relationships) not supported by the context or common knowledge. Plain ASCII, no emoji."
}}"""

NONEMBED_LINK = re.compile(r"(?<!\!)\[\[([^\]]+)\]\]")
# the vault owner (from VAULT_OWNER) - skip making a note for them by full name or first name
OWNER_NAMES = {OWNER.lower(), OWNER.split()[0].lower()} if OWNER else set()
TYPE_FOLDER = {"person": "wiki/entities", "company": "wiki/entities",
               "project": "wiki/projects", "concept": "wiki/concepts"}
_ALL_STEMS = None


def all_stems():
    global _ALL_STEMS
    if _ALL_STEMS is None:
        _ALL_STEMS = {p.stem.lower() for p in VAULT.rglob("*.md")
                      if ".obsidian" not in p.parts and "_export" not in p.parts}
    return _ALL_STEMS


def stub_info(name, context):
    text = llm(STUB_PROMPT.format(name=name, context=context[:800]), max_tokens=400)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON from stub model")
    return json.loads(m.group(0))


def create_stub(name, context, when):
    try:
        info = stub_info(name, context)
    except Exception as e:
        print(f"stub fill failed for {name}: {e}", file=sys.stderr)
        info = {"type": "stub",
                "body": f"Referenced in a Telegram capture on {when.strftime('%Y-%m-%d')}. "
                        f"Context: {context[:200].strip()}"}
    ntype = str(info.get("type") or "stub").strip().lower()
    if ntype not in ("person", "company", "project", "concept"):
        ntype = "stub"
    folder = TYPE_FOLDER.get(ntype, "wiki/stubs")
    d = VAULT / folder
    d.mkdir(parents=True, exist_ok=True)
    note = d / f"{name}.md"
    if note.exists():
        return
    today = when.strftime("%Y-%m-%d")
    body = str(info.get("body") or "").strip() or f"Referenced in a capture on {today}. TBD."
    note.write_text(
        f"---\ntype: {ntype}\ndate: {today}\ntags: [{ntype}, telegram-capture]\nai-first: true\n---\n\n"
        f"## For future Claude\n\n{body}\n",
        encoding="utf-8")
    all_stems().add(name.lower())


def fill_links(text, when, context=""):
    """Create + fill a note for each [[link]] the bot just wrote that has no note yet.
    Safe: only ever CREATES new notes (never edits existing ones)."""
    stems = all_stems()
    seen = set()
    for m in NONEMBED_LINK.finditer(text):
        name = m.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        key = name.lower()
        if not name or key in seen or key in stems or key in OWNER_NAMES:
            continue
        seen.add(key)
        create_stub(name, context or text, when)


# ---------- catchup queue: a pull-based review list for /obsidian-catchup ----------

CATCHUP = None  # resolved from VAULT at first use


def queue_catchup(kind, summary, when, where=""):
    """Append one unprocessed line to the vault's catchup queue. Pulled later by
    /obsidian-catchup at the laptop - the bot never pushes/processes, it just queues."""
    global CATCHUP
    if CATCHUP is None:
        CATCHUP = VAULT / "catchup.md"
    if not CATCHUP.exists():
        CATCHUP.write_text(
            "---\ntype: catchup-queue\nai-first: true\n---\n\n"
            "## For future Claude\n\nUnprocessed captures from the Telegram journal bot, "
            "newest at the bottom. Each line is `- [ ] date time | kind | summary | -> where`. "
            "Run /obsidian-catchup to review the unchecked items together, then they get "
            "checked off. The bot only queues here - it never processes.\n\n## Queue\n\n",
            encoding="utf-8")
    summary = re.sub(r"\s+", " ", str(summary)).strip()[:100]
    line = f"- [ ] {when.strftime('%Y-%m-%d %H:%M')} | {kind} | {summary}"
    if where:
        line += f" | -> {where}"
    with CATCHUP.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


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
            if "document" in msg:
                handle_document(msg, chat_id, when)
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
                link = URL_RE.search(raw)
                if link:
                    handle_link(link.group(0), chat_id, when)
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
            append_under(note, "## Voice journal", f"### {when.strftime('%H:%M')} ({kind})\n\n{entry}\n", when)
            fill_links(entry, when, raw)
            queue_catchup(kind, entry, when, f"[[{note.stem}]]")
            reply(chat_id, f"saved to {note.name}")
        except Exception as e:
            reply(chat_id, f"error: {e}")
            print(f"error on update {u['update_id']}: {e}", file=sys.stderr)

    set_offset(last)


if __name__ == "__main__":
    main()

---
description: Turn a knowledge-sharing recording (talk, workshop, demo, walkthrough) into an AI-first vault note with timestamped sections, screenshots, and a local transcript, then publish it to a Confluence page you provide
category: research
exclude: [codex-cli, gemini-cli, opencode, hermes, pi, agent-skills, grok-bot]
triggers_en: ["capture this recording", "capture this workshop", "turn this recording into a knowledge note", "knowledge capture", "store this knowledge sharing session", "publish this session to confluence"]
triggers_es: ["captura esta grabacion", "convierte esta grabacion en una nota de conocimiento", "publica esta sesion en confluence"]
triggers_pt: ["capture esta gravacao", "transforme esta gravacao em uma nota de conhecimento", "publique esta sessao no confluence"]
triggers_zh: ["把这个录像整理成知识笔记", "记录这次分享会", "发布到 Confluence"]
---

Use the obsidian-second-brain skill. Execute `/knowledge-capture $ARGUMENTS`:

This command turns one recorded knowledge-sharing session into reusable team knowledge, in **two phases that always run in order**:

1. **Vault phase**: the recording and its companions (Gemini notes, slides, Jira tickets, Confluence pages shown on screen) become an AI-first knowledge note, a verbatim transcript note, and a set of screenshots in a topic folder.
2. **Confluence phase**: runs **only** when the user gives a Confluence page URL. The same knowledge is published as a reader-friendly page, with the screenshots attached.

Stop after phase 1 and report. Never create a Confluence page yourself, and never publish without a page URL from the user.

The why, the recording brief to hand presenters, and the full prerequisites list live in `references/knowledge-capture-playbook.md`. Read it before the first run in a session.

## Prerequisites (check before starting; stop with a clear setup message if one is missing)

- **Claude Code** (or Claude Desktop's Code tab) with this skill installed and `OBSIDIAN_VAULT_PATH` set.
- **Google Drive connector**, to read Gemini notes, slides, and file metadata. Large videos still have to be downloaded by the user; see step 3.
- **Atlassian MCP (`mcp-atlassian`) with a Personal Access Token**, needed for phase 2 (Confluence) and for reading any Jira tickets shown in the recording. Setup is in the playbook. Tokens live only in the local MCP config and are never written anywhere else.
- **Local tools on PATH**: `ffmpeg` / `ffprobe` (`brew install ffmpeg`), `uv`, and `mlx-whisper` (`uv tool install mlx-whisper`, Apple Silicon). `scripts/knowledge-capture/transcribe.sh` installs `mlx-whisper` on first use; the Whisper model (about 1.5 GB) downloads on the first run.

## Inputs (ask only for what is missing)

- Recording link. Optional: Gemini notes or transcript doc, slides, related Jira tickets and Confluence pages.
- **Scope**: whose content to keep (e.g. only one speaker's part) and the time range, if the recording covers more than the topic.
- **Topic folder**: where the note goes. Follow the vault's `_CLAUDE.md` folder map; if it has none, default to `Knowledge/<Topic>/`. Create the folder if it doesn't exist, and expect more sessions on the same topic to land there later.

## Phase 1: vault

1. **Read every non-video source first**: Drive file metadata (owner, size, duration), the Gemini notes, slides, Jira tickets, and Confluence pages. Search the vault for existing notes on the topic, so you extend and link them instead of duplicating.
2. **Get the video.** Connector downloads of large videos fail, so ask the user to download the recording to their Downloads folder (Drive: menu, then Download, default file name). Start a background watcher that waits until the file size stops changing, and keep working on the other sources in the meantime.
3. **Transcribe locally.** Always do this, even when Gemini notes exist, because they summarize rather than record what was said:
   ```bash
   bash "SKILL_ROOT/scripts/knowledge-capture/transcribe.sh" "<video>" "<scratch>/transcript"
   ```
   The script disables `condition_on_previous_text`, which prevents the repetition loops and the collapse into "..." that Whisper otherwise produces after long silences. Scan the output for repeated phrases anyway; if a stretch is broken, cut it out with `ffmpeg -ss/-t` and re-run just that part.
4. **Map the video**: `frames.sh sheets "<video>" "<scratch>/sheets" 30` (20 for recordings under 20 minutes). Read the contact sheets and line them up with the transcript minutes.
5. **Pick frames**: `frames.sh grab "<video>" "<scratch>/frames" <sec> <sec> ...`, then read the previews. Zoom into code and config frames to read exact values. Keep about 12 to 20 frames (one or two per section: code, config, UI steps, results). Skip frames that only show a speaker's face.
6. **Write to the vault**, following `references/ai-first-rules.md` for every note:
   - `<topic folder>/attachments/<prefix>-NNx-short-name.png`. Use a unique prefix per session so files never collide.
   - `<topic folder>/<Title>.md`: the knowledge note, shaped like `references/knowledge-capture-template.md`. It has the frontmatter, the `## For future agent` preamble, a Sources list, sections tagged `*Video MM:SS-MM:SS*` with their frames, exact code and config blocks, takeaways, and follow-ups.
   - `<topic folder>/<Title> - Transcript.md`: the transcript, with a preamble listing known mis-hearings.
   - Link related notes both ways; for a series, add Previous/Next lines.
7. **Report**: what's in the note, what the user should verify, anything you paraphrased rather than quoted, and the transcription fixes you made. Then wait for the Confluence URL.

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future agent` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. If that path does not resolve from your working directory, search upward for it; if you still cannot read it, say so before writing rather than producing a note that silently skips the rule.

### Content rules

- Capture **what someone needs to repeat the work**: steps, exact commands and config, and the "most important thing" gotchas. Drop small talk and discussion outside the requested scope.
- Fix transcription errors in the note; Gemini and Whisper both mangle product and personal names. Where it's cheap, check config and API claims against official docs, and flag every correction you made.
- If a frame shows only part of a file, say the content is paraphrased.
- **Never write secrets or personal identifiers** (tokens, passwords, password-manager links, national ID numbers) to the vault or to Confluence. Use placeholders such as `<your-jira-pat>`.

## Phase 2: Confluence (only with a page URL from the user)

1. Read the page with `confluence_get_page` in storage format. If it already has content, merge into it; don't overwrite without asking.
2. **Upload the screenshots from their vault paths** with `confluence_upload_attachments`. The Atlassian MCP rejects files outside its allowed root (the vault), so scratch paths fail.
3. Build the storage-format body with `source "SKILL_ROOT/scripts/knowledge-capture/confluence_helpers.sh"` and `PREFIX=<prefix>`:
   - an `info` box: who, what, when, and "The screenshots come from the recording."
   - a **Sources** line
   - a one-paragraph intro, then `toc`
   - `<h2>N. Section</h2>` with `<em>Video MM:SS-MM:SS</em>`, bullets, `code` blocks, and `img` frames at 900 px
   - a closing **Next steps** section
   Use plain wording for a wider audience, and spell out shorthand the vault note used.
4. **Leave out of Confluence**: the `## For future agent` preamble, the machine transcript, wikilinks, and any personal or management context (goals, backlog tasks, notes about who owns a recording). Tell the user what you left out instead.
5. Write the body to a temporary file **inside the vault** (the `content_file` path has the same allowed-root rule), call `confluence_update_page` with `content_format: storage`, then delete the temporary file.
6. Add `- Confluence: [<title>](<url>)` to the note's Sources list, and tell the user the page version and that the downloaded video can be deleted.

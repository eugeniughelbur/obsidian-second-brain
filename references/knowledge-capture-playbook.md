# Knowledge capture playbook

Companion to `commands/knowledge-capture.md`. It explains why this habit is worth building, what presenters should record, and exactly what has to be set up before the command works.

## Why: scaling knowledge beyond the room

Knowledge-sharing sessions are one of the cheapest ways a team levels up. Someone who figured out Playwright, load testing, or an AI QA workflow spends an hour showing the rest. The problem is what happens afterwards: the recording sits in one person's Drive, the Gemini notes summarize without the exact commands, and six months later the next person to hit the same problem can't find any of it.

As an engineering manager, the habit to promote is: **every knowledge-sharing session becomes a searchable, reusable asset within a day**. One recording feeds two outputs:

| Output | Audience | What it gives them |
|---|---|---|
| Vault knowledge note + transcript | You, and any future agent working in your vault | Retrievable context: who knows what, exact steps, links to tickets and follow-ups, frames to verify against |
| Confluence page | The whole team and new joiners | A readable guide with screenshots, code blocks, and timestamps back into the recording |

What this does for scaling:

- **Presenters get visible credit.** Their session becomes the team's reference page, not a forgotten calendar event. That's a concrete example of the "share knowledge" behavior you want to recognize in reviews.
- **Onboarding gets faster.** New joiners read the page and jump to the right minute of the video, instead of booking an hour with the expert.
- **Knowledge survives people moving on.** When a presenter changes team or leaves, what they showed stays.
- **Learning goals get concrete material.** When a direct report wants to grow in an area (for example moving from manual QA to test automation), you can point them to an ordered set of pages rather than "ask around".
- **The marginal cost is low.** Recording is already happening, and the command does the transcription, screenshot selection, and page formatting. The human work is a quick accuracy review, ideally by the presenter.

## The recording brief (hand this to presenters)

Recordings work best when presenters know they'll become a guide:

1. **Record in Google Meet with Recording, Transcripts, and Gemini notes turned on.** A solo walkthrough works too: start a Meet with just yourself, share your screen, and talk through the work. A plain screen recording is fine as a fallback, because the command transcribes locally.
2. **Keep it focused**: 10 to 20 minutes per topic is ideal. Split long workshops into parts.
3. **Follow a simple shape**: the problem in one sentence, the setup (tools, access, config), a live demo on a real example, gotchas and what didn't work, and how someone else starts tomorrow.
4. **Make the screen readable**: use a large editor font, say out loud what you click, and pause briefly on important config.
5. **Share exact artifacts as text** next to the video: prompts, config, commands, templates. A video carries the flow well but is a poor source for exact strings.
6. **Drop the files in one shared folder** with a naming convention such as `YYYY-MM-DD - Topic - Presenter`, so recordings don't stay stranded in personal Drives.
7. **Review the draft.** The presenter checks the generated page before it's published; this catches most mistakes in a few minutes.

Recording as a pair works well: an expert walking a colleague through their workflow gives you the knowledge transfer and the recording in one meeting, and the colleague's questions show up in the transcript as exactly what newcomers need to know.

## Prerequisites

Every item below has to be in place before the command runs end to end. Nothing in this list involves storing personal data in the repo. Each person configures their own machine.

### 1. Claude Code with this skill

- Claude Code, or Claude Desktop's Code tab, with obsidian-second-brain installed (see the README install section).
- `OBSIDIAN_VAULT_PATH` set in `~/.claude/settings.json` (`env` section) to your own vault.
- The command is **Claude Code only**, because it depends on MCP connectors and local media tools; the other platform builds don't ship it.

### 2. Google Drive connector

- Connect Google Drive in Claude (Settings, then Connectors) using your own work account.
- It's used to read Gemini notes, slides, and recording metadata.
- **Large video files can't be downloaded through the connector.** The command asks you to download the recording to your Downloads folder yourself, and waits for it.

### 3. Atlassian MCP (`mcp-atlassian`) with a Personal Access Token

This one is required for publishing to Confluence and for reading Jira tickets that appear in a session.

1. Install `uv`: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Check that the server runs: `uvx mcp-atlassian --help`
3. Create **Personal Access Tokens** in your Jira and Confluence profiles (Profile picture, then Personal Access Tokens, then Create token). Self-hosted Jira and Confluence (Server / Data Center) use PATs. Atlassian Cloud uses an email plus API token instead; check which your instance runs.
4. Add the server to your Claude config. That's `claude_desktop_config.json` for Claude Desktop (macOS: `~/Library/Application Support/Claude/`), or your global Claude Code settings:

   ```json
   {
     "mcpServers": {
       "mcp-atlassian": {
         "command": "uvx",
         "args": ["mcp-atlassian"],
         "env": {
           "JIRA_URL": "https://jira.example.com",
           "JIRA_PERSONAL_TOKEN": "<your-jira-pat>",
           "CONFLUENCE_URL": "https://confluence.example.com",
           "CONFLUENCE_PERSONAL_TOKEN": "<your-confluence-pat>"
         }
       }
     }
   }
   ```

5. Fully restart Claude. `mcp-atlassian` should show under Connectors.

Rules for the token:

- **Never commit it, never paste it into a note, a Confluence page, or a chat log.** It lives only in your local MCP config. If a token shows up in a recording, blur it or leave that frame out.
- You can limit what the server reaches with `JIRA_PROJECTS_FILTER` / `CONFLUENCE_SPACES_FILTER`, which take comma-separated keys.
- A `401` means the token has expired or is wrong; regenerate it and update the config.

Known limits:

- **The server only reads and uploads files inside its allowed root, which is your vault.** Screenshots and the temporary page body therefore have to sit under the vault path, not in a scratch directory. The command handles this.
- **Write calls can return `403` on some self-hosted instances** even with a valid token. Reads keep working. The workaround is calling the REST API directly with `curl` and the same token read from your local config, never hard-coded.

### 4. Local media tools

- `ffmpeg` and `ffprobe` (`brew install ffmpeg`), for audio extraction, contact sheets, and frames.
- `mlx-whisper` for local transcription on Apple Silicon (`uv tool install mlx-whisper`; `transcribe.sh` installs it if it's missing). The first run downloads the `whisper-large-v3-turbo` model, about 1.5 GB. After that it's fully offline, so recordings never leave your machine. On an M-series Mac, an hour of audio takes about 2 minutes.
- On non-Apple hardware, swap in `openai-whisper` or `faster-whisper` with the same idea: disable conditioning on previous text to avoid repetition loops.

## Known pitfalls (already handled by the command)

| Pitfall | What happens | How the command avoids it |
|---|---|---|
| Whisper repetition loops | Long silences produce "I forgot. I forgot..." or pages of "..." | `transcribe.sh` runs with `--condition-on-previous-text False`; broken stretches are re-run |
| Name mis-hearings | Product and people names come out garbled | Corrected in the note, listed in the transcript preamble |
| Gemini notes are summaries | Exact commands and config values are missing | Local transcript plus zoomed frames are the source of truth |
| Frames cut off long lines | Rules or config only partly visible | The note says the content is paraphrased; the user is asked to get the original file |
| Personal context leaking to Confluence | Goals, backlog, or ownership notes end up on a team page | Phase 2 has an explicit leave-out list |

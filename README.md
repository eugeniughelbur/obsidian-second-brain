# obsidian-ai-brain

A focused fork of [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) — stripped down to project tracking and knowledge capture for developers running 4-ish active projects.

The original skill has 31 commands covering scheduling, thinking tools, content creation, and social media research. This fork keeps 16 and adds one new core command: `/projects`.

---

## What this does differently

The primary surface is a persistent Obsidian dashboard (`Projects/Dashboard.md`) that synthesizes your current state across all tracked projects by reading three sources in parallel:

1. Your vault's project notes
2. Recent git history from each repo
3. Any `NOTES.md` or `TODO.md` in the repo root

Run `/projects` at session start. The dashboard rewrites itself and prints to the conversation. Your projects list is configured once in `_CLAUDE.md` inside your vault.

---

## Commands (16)

### Project tracking

| Command | What it does |
|---|---|
| `/projects [name]` | Live overview of all projects - reads vault + git + docs, rewrites dashboard. Pass a name for single-project deep context. |
| `/obsidian-project [name]` | Create or update a project note |
| `/obsidian-log` | Log a dev session - what was worked on, decisions, next steps |
| `/obsidian-adr [topic]` | Decision record - the vault knows why things are the way they are |
| `/obsidian-task [description]` | Add a task linked to a project |

### Vault operations

| Command | What it does |
|---|---|
| `/obsidian-save` | Extracts everything from the conversation and saves it where it belongs |
| `/obsidian-capture [idea]` | Zero-friction idea capture |
| `/obsidian-find [query]` | Smart vault search with context |
| `/obsidian-person [name]` | Create or update a person note |
| `/obsidian-reconcile` | Find and resolve contradictions across the vault |
| `/obsidian-health` | Vault audit - broken links, orphans, stale claims, missing frontmatter |
| `/obsidian-init` | Bootstrap `_CLAUDE.md` for a new vault |

### Research

| Command | What it does |
|---|---|
| `/youtube [url]` | Digest a YouTube video - transcript + summary + key points saved as AI-first note |
| `/research [topic]` | Web research with citations via Perplexity Sonar |
| `/research-deep [topic]` | Vault-first deep research - scans what you already know, fills only the gaps |
| `/x-read [url]` | Read and save a web page or X post to the vault |

---

## Setup

### 1. Install the skill

```bash
git clone https://github.com/MPZ-00/obsidian-ai-brain ~/.claude/skills/obsidian-ai-brain
ln -s ~/.claude/skills/obsidian-ai-brain/commands/* ~/.claude/commands/
```

Restart Claude Code.

### 2. Bootstrap your vault

If you have an existing vault, run `/obsidian-init` inside it. Claude will generate `_CLAUDE.md` with your vault's actual structure.

For a new vault:

```bash
python scripts/bootstrap_vault.py --path ~/path/to/vault --name "Your Name" --preset builder
```

### 3. Configure your projects

Add a `projects:` block to `_CLAUDE.md` in your vault root:

```yaml
projects:
  - name: My Project
    repo: C:\Users\you\Documents\Codeing\GitHub\my-project
    vault_note: Projects/My Project.md
  - name: Another Project
    repo: C:\Users\you\Documents\Codeing\GitHub\another-project
    vault_note: Projects/Another Project.md
```

Run `/projects` - it will create `Projects/Dashboard.md` and print the current state for all projects.

### 4. Research toolkit (optional)

The `/research`, `/research-deep`, `/youtube`, and `/x-read` commands need API keys:

```bash
cp .env.example ~/.config/obsidian-second-brain/.env
# add your keys, then:
uv sync
```

| Key | Source | Used by |
|---|---|---|
| `XAI_API_KEY` | [console.x.ai](https://console.x.ai) | `/x-read`, `/youtube` summary, `/research-deep` X phase |
| `PERPLEXITY_API_KEY` | [perplexity.ai/settings/api](https://perplexity.ai/settings/api) | `/research`, `/research-deep` |
| `YOUTUBE_API_KEY` | [console.cloud.google.com](https://console.cloud.google.com) | `/youtube` metadata + comments (optional - transcripts work free) |

---

## The AI-first rule

Every note Claude writes follows `references/ai-first-rules.md`. Notes are designed for future-Claude to retrieve and reason over, not for human reading:

- `## For future Claude` preamble at the top
- Rich frontmatter: `type`, `date`, `tags`, `ai-first: true`
- `[[wikilinks]]` for every person, project, and concept referenced
- Recency markers on external claims: `(as of 2026-05, source.com)`
- Source URLs preserved verbatim

---

## The `_CLAUDE.md` file

Lives at your vault root. Tells Claude your folder structure, naming conventions, and project list. Without it, Claude re-learns your vault every session. Run `/obsidian-init` to generate one.

See `references/claude-md-template.md` for the full schema.

---

## What was removed from the original

Cut: `/obsidian-daily`, `/obsidian-board`, `/obsidian-recap`, `/obsidian-review`, `/obsidian-decide`, `/obsidian-export`, `/obsidian-ingest`, `/obsidian-visualize`, `/obsidian-synthesize`, `/obsidian-connect`, `/obsidian-emerge`, `/obsidian-graduate`, `/obsidian-challenge`, `/obsidian-learn`, `/obsidian-world`, `/x-pulse`

The scheduled agent system (morning/nightly/weekly/health) was also removed. This fork is for working with AI, not running autonomous vault agents.

---

## Credits

Based on [obsidian-second-brain](https://github.com/eugeniughelbur/obsidian-second-brain) by Eugeniu Ghelbur. AI-first vault principle and core architecture from that project.

---

## License

MIT

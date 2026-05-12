<p align="center">
  <a href="https://github.com/eugeniughelbur/obsidian-second-brain">
    <img src="media/banner.png" alt="obsidian-second-brain: a Claude Code skill for Obsidian that turns your vault into a living AI-first second brain" width="100%" />
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Claude_Code-555555?style=for-the-badge" alt="Claude Code" />
  <img src="https://img.shields.io/badge/Codex_CLI-555555?style=for-the-badge" alt="Codex CLI" />
  <img src="https://img.shields.io/badge/Gemini_CLI-555555?style=for-the-badge" alt="Gemini CLI" />
  <img src="https://img.shields.io/badge/OpenCode-555555?style=for-the-badge" alt="OpenCode" />
</p>

<p align="center">
  <em>One codebase. Four platforms. Same brain.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Obsidian-Vault-7C3AED?style=for-the-badge&logo=obsidian&logoColor=white" alt="Obsidian Vault" />
  <img src="https://img.shields.io/github/v/release/eugeniughelbur/obsidian-second-brain?style=for-the-badge&color=green" alt="Release" />
  <img src="https://img.shields.io/badge/license-MIT-blue?style=for-the-badge" alt="License: MIT" />
  <img src="https://img.shields.io/github/stars/eugeniughelbur/obsidian-second-brain?style=for-the-badge&color=yellow" alt="Stars" />
  <a href="https://github.com/sponsors/eugeniughelbur"><img src="https://img.shields.io/badge/Sponsor-EA4AAA?style=for-the-badge&logo=github-sponsors&logoColor=white" alt="Sponsor" /></a>
</p>

<p align="center">
  <a href="https://oosmetrics.com/repo/eugeniughelbur/obsidian-second-brain"><img src="https://img.shields.io/badge/oosmetrics-%F0%9F%8F%86%20Trending%20repo-DAA520?style=for-the-badge&labelColor=2C2C2C" alt="oosmetrics: trending repo" /></a>
</p>

<h1 align="center">obsidian-second-brain</h1>

<p align="center">
  <strong>An evolution of <a href="https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f">Karpathy's LLM Wiki pattern</a>: a vault that rewrites itself.</strong>
  <br /><br />
  <em>Every source updates existing pages instead of just appending new ones. Contradictions reconcile automatically. Your vault compounds while you sleep.</em>
  <br /><br />
  <em>31 commands &middot; auto-synthesis &middot; thinking tools that argue with you</em>
  <br /><br />
  <em>live research from X, the web, and YouTube &middot; 4 scheduled agents &middot; 4 role presets</em>
  <br /><br />
  <a href="#what-happens-when-you-install-this">See it in action</a> &middot;
  <a href="#31-commands">All commands</a> &middot;
  <a href="#install">Install</a> &middot;
  <a href="#choose-your-preset">Presets</a> &middot;
  <a href="https://github.com/eugeniughelbur/obsidian-second-brain/discussions">Discussions</a>
</p>

<p align="center">
  <strong>From the blog</strong>
</p>

<p align="center">
  <strong>Origin story:</strong> <a href="https://theaioperator.io/p/i-built-this-for-myself-then-1374">"I built this for myself. Then 1,374 strangers cloned it."</a><br />
  <em>Two disconnected tools &middot; the institutional-amnesia problem &middot; 1,000+ stars in 7 weeks</em>
</p>

<p align="center">
  <strong>Deep dive:</strong> <a href="https://theaioperator.io/p/i-rebuilt-karpathys-llm-wiki-heres">"I rebuilt Karpathy's LLM Wiki. Here's what's missing from the original."</a><br />
  <em>Why append-only breaks at scale &middot; the AI-First Vault Principle &middot; three bugs in v1</em>
</p>

<p align="center">
  <strong>One post per Tuesday on Obsidian + AI workflows, agent patterns, and bringing AI into real work.</strong><br />
  <a href="https://theaioperator.io">Subscribe to The AI Operator &rarr;</a>
</p>

<p align="center">
  <strong>Research toolkit</strong> — <code>/x-read</code> · <code>/x-pulse</code> · <code>/research</code> · <code>/research-deep</code> · <code>/youtube</code><br/>
  <em>Pull live X posts, web research with citations, and YouTube transcripts straight into your vault as AI-first notes. <br/>
  Vault-first synthesis knows what you already know and fills only the gaps.</em>
</p>

<p align="center">
  <a href="https://github.com/eugeniughelbur">
    <img src="https://github.com/eugeniughelbur.png" width="72" height="72" alt="Eugeniu Ghelbur" style="border-radius: 50%;" />
  </a>
</p>

<p align="center">
  Built by <strong>Eugeniu Ghelbur</strong> · AI Automation Engineer @ Single Grain<br />
  <em>building in public · sharing what works</em>
</p>

<div align="center">

<table>
<tr>
<td align="center" width="700">

### Follow along

*Weekly posts on AI second-brain systems, vault patterns, and what actually works.*

<a href="https://x.com/eugeniu_ghelbur"><img src="https://img.shields.io/badge/Follow_on_X-000?style=for-the-badge&logo=x&logoColor=white" alt="Follow on X" /></a>
<a href="https://www.linkedin.com/in/eugeniu-ghelbur/"><img src="https://img.shields.io/badge/Connect_on_LinkedIn-0A66C2?style=for-the-badge&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0yMC40NDcgMjAuNDUyaC0zLjU1NHYtNS41NjljMC0xLjMyOC0uMDI3LTMuMDM3LTEuODUyLTMuMDM3LTEuODUzIDAtMi4xMzYgMS40NDUtMi4xMzYgMi45Mzl2NS42NjdIOS4zNTFWOWgzLjQxNHYxLjU2MWguMDQ2Yy40NzctLjkgMS42MzctMS44NSAzLjM3LTEuODUgMy42MDEgMCA0LjI2NyAyLjM3IDQuMjY3IDUuNDU1djYuMjg2ek01LjMzNyA3LjQzM2MtMS4xNDQgMC0yLjA2My0uOTI2LTIuMDYzLTIuMDY1IDAtMS4xMzguOTItMi4wNjMgMi4wNjMtMi4wNjMgMS4xNCAwIDIuMDY0LjkyNSAyLjA2NCAyLjA2MyAwIDEuMTM5LS45MjUgMi4wNjUtMi4wNjQgMi4wNjV6bTEuNzgyIDEzLjAxOUgzLjU1NVY5aDMuNTY0djExLjQ1MnpNMjIuMjI1IDBIMS43NzFDLjc5MiAwIDAgLjc3NCAwIDEuNzI5djIwLjU0MkMwIDIzLjIyNy43OTIgMjQgMS43NzEgMjRoMjAuNDUxQzIzLjIgMjQgMjQgMjMuMjI3IDI0IDIyLjI3MVYxLjcyOUMyNCAuNzc0IDIzLjIgMCAyMi4yMjIgMGguMDAzeiIvPjwvc3ZnPg%3D%3D" alt="Connect on LinkedIn" /></a>
<a href="https://theaioperator.io"><img src="https://img.shields.io/badge/Subscribe_on_Substack-FF6719?style=for-the-badge&logo=substack&logoColor=white" alt="Subscribe on Substack" /></a>
<a href="https://github.com/eugeniughelbur"><img src="https://img.shields.io/badge/Follow_on_GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="Follow on GitHub" /></a>

</td>
</tr>
</table>

</div>

---

## The Problem

You use Claude every day. Every session starts from scratch. You re-explain everything. The conversation ends. Everything disappears.

You take notes in Obsidian. Hundreds of files. They just sit there. You make the same decision twice because you forgot you made it six months ago. Ideas rot in daily notes. Nobody connects the dots.

**Two powerful tools. Completely disconnected.**

---

## How this extends Karpathy's LLM Wiki

Karpathy's pattern is brilliant. Drop sources, LLM creates wiki pages, ask questions. This skill takes it further:

| | Karpathy's LLM Wiki | obsidian-second-brain |
|---|---|---|
| **New sources** | Append new pages, cross-reference | **Rewrite existing pages.** People get updated, claims revised, stale facts replaced. |
| **Contradictions** | Flagged, you resolve manually | `/obsidian-reconcile` resolves them automatically |
| **Patterns** | Surface when you ask | `/obsidian-synthesize` finds unnamed patterns and writes synthesis pages on its own |
| **When it runs** | On demand, when you prompt | 4 scheduled agents: nightly close, weekly review, contradiction sweep, vault-health check |
| **Note format** | Human-readable wiki pages | AI-first: `## For future Claude` preamble + frontmatter for LLM retrieval, not human review |

If Karpathy's wiki is a knowledge base you maintain with an LLM, this is a knowledge base that maintains itself.

---

## What Happens When You Install This

**After a meeting:** `/obsidian-save`
Claude pulls out every decision, person, task, and idea and saves each one to the right note. You do nothing.

**You recorded a voice memo:** `/obsidian-ingest meeting.m4a`
Claude transcribes it with Whisper, identifies speakers, extracts every promise and action item, and distributes across entity pages, task boards, and the daily note.

**You screenshot a whiteboard:** `/obsidian-ingest photo.png`
Claude reads the image, extracts text and structure, creates concept notes, links to related projects. A photo becomes knowledge.

**You find a great video:** `/obsidian-ingest https://youtube.com/...`
Claude doesn't summarize into one note. It REWRITES your existing pages. People get updated. Contradictions get resolved. Patterns trigger new synthesis pages. One URL in. The vault is smarter.

**Before a big decision:** `/obsidian-challenge`
Claude searches your vault for past failures and reversed decisions on the same topic. Pushes back with your own words. Your vault holds you accountable.

**You want to see the big picture:** `/obsidian-visualize`
Claude generates a visual canvas of your entire vault. Hub nodes centered, color-coded by type, orphans highlighted. Open it in Obsidian and see the shape of your knowledge.

**You go to sleep:** The nightly agent runs 5 phases — closes the day, reconciles contradictions, synthesizes cross-source patterns, heals orphan notes, and rebuilds the index. You wake up to a smarter vault.

**You start a new day:** `/obsidian-daily`
Claude pulls your calendar events, overdue tasks, and overnight changes into today's note. Your morning starts informed.

**Someone shares an X post:** `/x-read https://x.com/...`
Grok with live X access fetches the post, the thread, and the replies. Returns verbatim text + TL;DR + key claims + reply sentiment + voices to watch. No more screenshots.

**You're planning today's content:** `/x-pulse "AI automation"`
Grok scans X for what's trending in your topic right now. Returns 3-5 emerging themes (with rep posts + key voices), gaps nobody is filling, hook formats that are working, and 3 specific post ideas you could write today.

**You need real research:** `/research "AI memory tools"`
Perplexity Sonar Pro pulls a deep dossier with citations: summary, key facts (every claim with a recency marker and source domain), timeline, key players, contrarian views, recommended further reading, open questions. Saved to your vault, auto-opens in Obsidian.

**You want vault-first deep research:** `/research-deep "AI memory tools"`
Scans your vault for what you already know. Identifies gaps. Spawns 3-5 targeted searches via Perplexity (web) and Grok (X discourse). Synthesizes a delta report — what's new, what's confirmed, contradictions to resolve, recommended vault updates. Vault baseline doesn't get re-researched. Only gaps get filled.

**You hit a great YouTube video:** `/youtube https://youtu.be/...`
Free transcript via youtube-transcript-api. Optional metadata + top comments via YouTube Data API v3. Grok summarizes into TL;DR, Key Points, Notable Quotes (verbatim), Themes, Comment Sentiment, and Worth Following Up On. Saved as an AI-first note in your vault.

**You never open Obsidian.** Everything happens through Claude.

---

## Before & After

| | Without this skill | With this skill |
|---|---|---|
| Saving decisions | Copy-paste or lose them | Auto-saved to the right project note |
| Daily notes | Write it yourself, forget half the time | Created automatically |
| Finding patterns | Re-read dozens of notes | `/emerge` finds them for you |
| Challenging yourself | Nobody pushes back | `/challenge` uses your own history against you |
| Session continuity | Re-explain every time | `/world` loads full context in 10 seconds |
| Ingesting content | Read it, forget it | `/ingest` rewrites 5-15 vault pages from 1 source (URLs, PDFs, audio, screenshots) |
| Contradictions | You don't know they exist | `/reconcile` resolves them automatically |
| Synthesis | You connect dots manually | `/synthesize` finds patterns across sources on its own |
| Sharing vault data | Only Claude can read it | `/export` gives any AI tool a clean snapshot |
| Facts change over time | Old info gets overwritten | Bi-temporal facts track when it was true AND when the vault learned it |
| Starting a new session | Re-explain who you are | `CRITICAL_FACTS.md` loads your identity in ~120 tokens |
| Reading an X thread | Open X, scroll, screenshot, paste | `/x-read [url]` returns post + thread + sentiment + voices |
| Knowing what to post | Guess what's trending | `/x-pulse` scans X and returns hot themes + gaps + hooks + post ideas |
| Web research | Open 12 tabs, copy quotes manually | `/research [topic]` returns a sourced dossier with recency markers |
| Researching what you already know | Re-research from scratch | `/research-deep` scans vault first, fills only the gaps, flags contradictions |
| YouTube videos | Watch passively, forget | `/youtube [url]` transcript + summary + quotes saved to vault |
| Vault notes for future-Claude | Notes for human reading | AI-first rule: every note has "For future Claude" preamble + recency markers + citations |

---

## How It Works

```
  +------------------------------------------+
  |                                          |
  |   LAYER 1: Operations (21 commands)      |
  |   Claude remembers everything            |
  |                                          |
  +------------------------------------------+
  |                                          |
  |   LAYER 2: Thinking Tools (4 commands)   |
  |   Claude thinks with you                 |
  |                                          |
  +------------------------------------------+
  |                                          |
  |   LAYER 3: Context Engine (1 command)    |
  |   Claude knows who you are               |
  |                                          |
  +------------------------------------------+
  |                                          |
  |   LAYER 4: Research Toolkit (5 commands) |
  |   Claude pulls knowledge in              |
  |                                          |
  +------------------------------------------+
  |                                          |
  |   ALWAYS ON                              |
  |   Background agent + 4 scheduled agents  |
  |   Auto-synthesis + save reminders        |
  |                                          |
  +------------------------------------------+
```

**Layer 1** saves, organizes, ingests, reconciles, exports, and maintains your vault.
**Layer 2** challenges your ideas, surfaces hidden patterns, bridges unrelated domains, and graduates ideas into projects.
**Layer 3** loads your identity and current state so every session picks up where the last one ended.
**Layer 4** pulls live external knowledge into the vault: X posts, X trends, web research with citations, YouTube transcripts. Vault-first synthesis knows what you already know.
**Always On** keeps the vault alive without you lifting a finger.

---

## 31 Commands

### Operations -- Claude remembers

| Command | What it does |
|---|---|
| `/obsidian-save` | Saves everything from the conversation -- decisions, tasks, people, ideas |
| `/obsidian-ingest` | Drop a URL, PDF, audio file, or screenshot. The vault REWRITES itself. 5-15 pages touched per source. |
| `/obsidian-synthesize` | Auto-finds patterns across sources and writes synthesis pages |
| `/obsidian-reconcile` | Finds contradictions and resolves them. The vault maintains its own truth. |
| `/obsidian-export` | Clean JSON/markdown snapshot any AI tool can read |
| `/obsidian-daily` | Creates or updates today's daily note |
| `/obsidian-log` | Logs a work session, links it everywhere |
| `/obsidian-task` | Adds task to the right board with priority and due date |
| `/obsidian-person` | Creates or updates a person note |
| `/obsidian-decide` | Logs decisions to the right project note |
| `/obsidian-capture` | Zero-friction idea capture |
| `/obsidian-find` | Smart search with context |
| `/obsidian-recap` | Summary of a day, week, or month |
| `/obsidian-review` | Structured weekly or monthly review |
| `/obsidian-board` | Kanban board view and updates |
| `/obsidian-project` | Project note with board and daily links |
| `/obsidian-health` | Vault audit -- contradictions, gaps, stale claims, orphans |
| `/obsidian-adr` | Decision records -- the vault knows why it's structured this way |
| `/obsidian-visualize` | Generates a visual canvas map — see the shape of your second brain |
| `/obsidian-learn` | Reviews vault learnings, prunes stale ones, surfaces patterns to promote into rules |
| `/obsidian-init` | Generates `_CLAUDE.md`, `index.md`, `log.md` |

### Thinking -- Claude thinks with you

| Command | What it does |
|---|---|
| `/obsidian-challenge` | Your vault argues against your idea using your own history |
| `/obsidian-emerge` | Surfaces patterns from 30 days of notes you never named |
| `/obsidian-connect [A] [B]` | Bridges two unrelated domains to spark new ideas |
| `/obsidian-graduate` | Turns an idea fragment into a full project with tasks |

### Context -- Claude knows you

| Command | What it does |
|---|---|
| `/obsidian-world` | Loads identity + state with progressive token budgets (L0-L3) |

### Research -- Claude pulls knowledge in

Powered by xAI Grok (live X access) + Perplexity Sonar (web research) + YouTube. Findings save to `Research/` as AI-first notes (preamble, frontmatter, recency markers, sources verbatim).

| Command | What it does |
|---|---|
| `/x-read [url]` | Deep-read an X post — verbatim post + thread + TL;DR + claims + reply sentiment + voices |
| `/x-pulse [topic]` | Scan X for what's trending — themes, voices, hooks, post ideas |
| `/research [topic]` | Web research with citations — full dossier with recency markers and open questions |
| `/research-deep [topic]` | Vault-first synthesis — scans your vault, finds gaps, fills them, propagates updates across people/projects/ideas |
| `/youtube [url]` | Extract transcript + metadata + top comments → AI-first summary |

**Setup:** copy `.env.example` to `~/.config/obsidian-second-brain/.env`, add your keys (xAI, Perplexity, YouTube optional). Run `install.sh` and answer "y" to the research prompt to do this automatically.

<details>
<summary><strong>See the thinking tools in action</strong></summary>

<br />

**`/obsidian-challenge`**

You: *"I want to rewrite the API in Rust."*

Claude finds your 2025 post-mortem where the Rust rewrite failed. Finds your decision log committing to TypeScript for 2 years. Says: *"Your own notes say this failed. Still want to proceed?"*

---

**`/obsidian-emerge`**

Claude scans 30 daily notes. You mentioned "onboarding friction" in 4 unrelated projects.

*"Onboarding is your bottleneck across projects. You never named it."*

---

**`/obsidian-connect "distributed systems" "cooking"`**

Traces both clusters in your link graph. Finds shared concepts: preparation and load distribution. Generates 3 actionable ideas at the intersection.

---

**`/obsidian-graduate`**

An idea from 3 weeks ago. Claude reads it, finds related projects and people, generates a full spec with goals, phases, tasks, and board entries. The idea gets tagged `graduated`.

</details>

<details>
<summary><strong>See /obsidian-ingest in action</strong></summary>

<br />

```
/obsidian-ingest https://youtube.com/watch?v=example
```

1. Saves original to `raw/videos/` (immutable)
2. REWRITES entity pages with new context
3. REWRITES concept pages if the source adds depth or contradicts them
4. Creates synthesis pages when patterns emerge
5. Resolves contradictions and documents why
6. Updates `index.md`, `log.md`, daily note

**One URL in. The vault rewrites itself.**

</details>

<details>
<summary><strong>See the research toolkit in action</strong></summary>

<br />

**`/x-read https://x.com/garrytan/status/2048121438914154664`**

Grok with live X access fetches the post and replies. You get verbatim text, TL;DR, key claims, reply sentiment (~70% positive, 20% skeptical, 10% off-topic), notable counter-arguments with the @ handles of who said them, and "voices to watch" — replies that added real signal. ~$0.05/call.

---

**`/x-pulse "AI automation"`**

```
WHAT'S HOT (last 24-72h)
  1. Agentic AI vs Basic Automation — voices: @NVIDIAAP, @woisau1
  2. Self-Improving Sovereign Agents — voices: @tom_doerr, @AIDailyGems
  3. Control Layers & Execution Gaps — voices: @ZIQING_JP

WHAT'S UNDEREXPLORED
  - ROI numbers for non-developer small business users
  - Integration of digital agents with physical robotics

HOOKS THAT ARE WORKING
  - "Automation executes. Autonomy reasons." — @NVIDIAAP

POST IDEAS FOR YOU TODAY
  1. Thread: "I gave an open-source agent its own GitHub repo and watched it self-improve"
  2. Single: "Automation executes. Autonomy reasons. Here's the control layer..."
```

What you'd spend 2 hours scrolling X to find. Returned in 30 seconds for ~$0.13.

---

**`/research "AI memory tools"`**

Returns a structured dossier: Summary, Key Facts (each with `(as of YYYY-MM, source.com)`), Timeline, Key Players, Contrarian Views, Recommended Further Reading, Open Questions, full citations. Saved to `Research/Web/` as an AI-first note. ~$0.05/call.

---

**`/research-deep "AI memory tools"`** — the killer

```
Phase 1: Vault scan
  Found 8 relevant notes (e.g. Knowledge/2026-02-15 — Mem0 vs Letta.md)

Phase 2: Gap analysis (Perplexity sonar-pro)
  Identified 5 targeted queries to fill what vault is silent or stale on

Phase 3: Targeted research
  [web] Anthropic Claude memory tool 2026 features
  [web] Mem0 Series A reactions and concerns
  [x]   developer reactions to Letta vs Mem0
  ...

Phase 4: Synthesis (sonar-reasoning-pro)
  → What's New Since Vault Baseline
  → What's Confirmed
  → Contradictions / Updates Needed (with [[wikilinks]] to specific vault files)
  → Synthesis bullets
  → Recommended Vault Updates (instructions for /obsidian-save)
  → Open Questions
```

Vault-first means it doesn't waste tokens re-researching what you already knew. ~$0.40/call.

---

**`/youtube https://youtu.be/...`**

Free transcript via youtube-transcript-api + optional metadata + comments via YouTube Data API v3 (free tier). Grok summarizes into TL;DR, Key Points, Notable Quotes (verbatim), Themes, Comment Sentiment, and Worth Following Up On. ~$0.04 for the Grok call. Frontmatter includes view count, channel, published date, like count for Dataview queries.

---

**Auto-open after every save** — Obsidian pops open at the new note. Disable with `RESEARCH_AUTOOPEN=0` if you're running batch saves.

</details>

---

## The Vault is Alive

Traditional vaults are filing cabinets. You put things in. They sit there.

This vault rewrites itself with every input:

- **Ingest a source** -- existing pages get rewritten, contradictions resolved, patterns synthesized
- **Save a conversation** -- entities, concepts, and decisions distribute across the vault
- **Ask a question** -- the Two-Output Rule means every answer also updates pages
- **A fact changes** -- bi-temporal facts track when it was true AND when the vault learned it. "You believed X on Tuesday. After ingesting Y on Wednesday, you shifted to Z." Full audit trail.
- **Do nothing** -- background agent and scheduled agents maintain it while you sleep
- **Wait a week** -- auto-synthesis finds cross-source patterns and writes connection pages

The vault after a week is fundamentally different from the vault you started with.

---

## Choose Your Preset

Pick your role at bootstrap. Each preset creates tailored folder structures, templates, and kanban boards.

| Preset | Who it's for | Kanban style |
|---|---|---|
| **executive** | Founders, operators, managers | OKRs / Quarterly / Weekly |
| **builder** | Developers, engineers, architects | Backlog / Sprint / Done |
| **creator** | Writers, YouTubers, marketers | Ideas / Drafts / Published |
| **researcher** | Academics, analysts, deep-divers | Reading / Processing / Synthesized |

```bash
python bootstrap_vault.py --path ~/my-vault --name "Your Name" --preset builder
```

No preset? You get a general-purpose vault that works for everyone.

---

## Background Agent & Scheduled Agents

**Background:** fires after every context compaction. You keep working. The vault updates itself.

```
PostCompact -> obsidian-bg-agent.sh -> claude -p (headless) -> vault updated
```

**Scheduled:**

| Agent | When | What |
|---|---|---|
| `morning` | 8 AM | Daily note + overdue tasks |
| `nightly` | 10 PM | Sleeptime consolidation: close day + reconcile + synthesize + heal orphans |
| `weekly` | Fridays 6 PM | Weekly review |
| `health` | Sundays 9 PM | Vault health audit |

**Save reminders:** Claude nudges you to `/obsidian-save` after 10+ exchanges or when you say "done" or "thanks". No lost conversations.

---

## Vault Architecture

### Wiki-style (default) -- LLM-first

Claude is the reader and writer. The vault is a database.

```
vault/
+-- _CLAUDE.md          # Operating manual
+-- index.md            # Page catalog (Claude reads FIRST)
+-- log.md              # Activity timeline
+-- SOUL.md             # Your identity
+-- CRITICAL_FACTS.md   # ~120 tokens, always loaded (timezone, manager, location)
+-- raw/                # IMMUTABLE source material
+-- wiki/               # Claude's workspace
|   +-- entities/       # People, companies, tools
|   +-- concepts/       # Ideas, frameworks, synthesis
|   +-- projects/       # Project notes
|   +-- daily/          # Daily notes
|   +-- logs/           # Work session logs
|   +-- reviews/        # Weekly/monthly reviews
|   +-- tasks/          # Task notes
|   +-- decisions/      # ADRs
+-- boards/             # Kanban boards
+-- templates/          # Note templates
```

<details>
<summary><strong>Obsidian-style (alternative) -- for daily browsers</strong></summary>

```
vault/
+-- Daily/, Projects/, People/, Ideas/, Knowledge/
+-- Dev Logs/, Tasks/, Reviews/, Boards/, Templates/
```

```bash
python bootstrap_vault.py --path ~/my-vault --name "Your Name" --style obsidian
```

</details>

---

## Install

> **One codebase, four platforms.** Pick yours below. The vault behavior is identical across all four — only the install path and the dispatcher file (`CLAUDE.md` / `AGENTS.md` / `GEMINI.md`) differ.

### Claude Code (default)

One line:

```bash
curl -fsSL https://raw.githubusercontent.com/eugeniughelbur/obsidian-second-brain/main/scripts/quick-install.sh | bash
```

Or two commands:

```bash
git clone https://github.com/eugeniughelbur/obsidian-second-brain ~/.claude/skills/obsidian-second-brain
bash ~/.claude/skills/obsidian-second-brain/scripts/setup.sh "/path/to/your/vault"
```

Then: `/obsidian-init`

### Codex CLI / Gemini CLI / OpenCode

```bash
git clone https://github.com/eugeniughelbur/obsidian-second-brain
cd obsidian-second-brain
bash scripts/build.sh --platform codex-cli   # or gemini-cli, or opencode
cp -R dist/codex-cli/. /path/to/your/vault/   # or .gemini-cli / .opencode/
```

Then start your CLI from the vault root. Each build produces a platform-specific dispatcher (`AGENTS.md` for Codex / OpenCode, `GEMINI.md` for Gemini) with an **auto-generated routing table** mapping natural-language triggers to command files under `.codex/commands/` (or `.gemini/`, `.opencode/`).

Run `bash scripts/build.sh` with no arguments to build all four platforms at once. See [`dist/<platform>/INSTALL.md`](scripts/build.sh) after building for platform-specific notes.

### Research toolkit (optional)

The 5 research commands need API keys. Run `install.sh` and answer "y" to the research prompt — it'll set up `~/.config/obsidian-second-brain/.env`. Or do it manually:

```bash
mkdir -p ~/.config/obsidian-second-brain
cp .env.example ~/.config/obsidian-second-brain/.env
chmod 600 ~/.config/obsidian-second-brain/.env
# then paste keys into the file
uv sync   # installs Python deps
```

Keys you need:

| Key | Where | Required for | Cost |
|---|---|---|---|
| `XAI_API_KEY` | [console.x.ai](https://console.x.ai) | `/x-read`, `/x-pulse`, `/research-deep` X pulse, `/youtube` summary | Pay-per-use, ~$0.05/call |
| `PERPLEXITY_API_KEY` | [perplexity.ai/settings/api](https://perplexity.ai/settings/api) | `/research`, `/research-deep` | Pay-per-use, ~$0.02-$0.50/call |
| `YOUTUBE_API_KEY` | [console.cloud.google.com](https://console.cloud.google.com) | `/youtube` metadata + comments (optional — transcripts free without) | Free tier 10k units/day |

Without keys, the existing 26 vault commands still work fine. Research toolkit just degrades gracefully.

---

## FAQ

### What is a Claude Code skill?
A Claude Code skill is a reusable behavior package for Anthropic's Claude Code CLI. It bundles slash commands, scripts, references, and operating instructions that Claude loads automatically. Skills give Claude domain expertise without prompt-engineering each session.

### Is this an Obsidian plugin or a Claude Code skill?
This is a Claude Code skill, not an Obsidian plugin. An Obsidian plugin lives inside Obsidian and adds UI features there. A Claude Code skill lives inside Claude Code (Anthropic's terminal AI coding agent) and gives Claude the ability to read, write, and reason over your Obsidian vault from outside Obsidian. You install this skill into Claude Code, not into Obsidian. Your vault is unchanged, just better-leveraged.

### What's the difference between an Obsidian Claude Code skill and a regular Obsidian plugin?
An Obsidian plugin runs inside Obsidian and is written in TypeScript against Obsidian's plugin API. A Claude Code skill for Obsidian runs inside Claude Code and is written as a set of markdown command files plus optional Python scripts. Plugins are constrained to what Obsidian's API exposes. Skills are constrained only by what Claude can do in your shell, which is why this skill can do things plugins can't: pull live web research into vault notes, run scheduled agents that update your vault while you sleep, and synthesize knowledge across years of notes using Anthropic's Claude.

### How do I add this Obsidian Claude skill to Claude Code?
Run the one-line installer from the Install section below. It clones the repo to `~/.claude/skills/obsidian-second-brain` and symlinks the slash commands into `~/.claude/commands/` so Claude Code picks them up automatically. Restart Claude Code after install. The skill loads on every session that touches an Obsidian vault.

### Does this work with Codex CLI, Gemini CLI, or OpenCode?
Yes. The repo ships a build script that compiles the platform-neutral source into four platform-specific outputs: Claude Code (slash commands + `CLAUDE.md`), Codex CLI (`AGENTS.md` + `.codex/commands/`), Gemini CLI (`GEMINI.md` + `.gemini/commands/`), and OpenCode (`AGENTS.md` + `.opencode/commands/`). Run `bash scripts/build.sh --platform codex-cli` (or another platform name), then copy the resulting `dist/<platform>/` tree into your vault. The non-Claude builds auto-generate a routing table that maps natural-language triggers to command files, so the same 31 commands work no matter which CLI you use. The vault rules (AI-first notes, frontmatter, wikilinks, recency markers) are identical across all four platforms.

### Does this work with Obsidian Sync?
Yes. The skill writes to your vault as standard markdown files. Obsidian Sync, iCloud, Syncthing, and Git-based sync all work without modification.

### Do I need API keys to use this?
No. The original 26 vault commands (`/obsidian-save`, `/obsidian-daily`, etc.) work without any API keys. Only the 5 research commands (`/x-read`, `/x-pulse`, `/research`, `/research-deep`, `/youtube`) require API keys for xAI Grok, Perplexity, and optionally YouTube Data API v3. Without keys, those commands degrade gracefully — they exit with a clear setup message.

### How is this different from Notion AI or Mem?
Notion AI and Mem are closed-source SaaS products that own your data. This skill stores everything as plain markdown in your local Obsidian vault, with no vendor lock-in. The AI is on top of your data, not behind it. You can switch tools or stop using the skill at any point and still have your full vault.

### What is the AI-first vault rule?
The principle that vault notes are written for future-Claude to retrieve and reason over, not for human reading. Notes have machine-readable structure, recency markers per claim, mandatory `[[wikilinks]]`, source URLs preserved verbatim, and confidence levels. See [`references/ai-first-rules.md`](references/ai-first-rules.md) for the full specification with frontmatter schemas per note type.

### Is this safe to run on my existing vault?
Yes. The skill never deletes or modifies notes destructively without explicit confirmation. Existing notes stay as-is. New notes follow the AI-first rule. `/obsidian-health` flags pre-AI-first notes so you can update them on your own schedule.

### What does `/research-deep` do that `/research` doesn't?
`/research` runs a single Perplexity query and returns a dossier with citations. `/research-deep` is vault-first: it scans your existing notes, identifies what you already know about the topic, spawns 3-5 targeted follow-up searches to fill only the gaps, and produces a delta report (what's new, what's confirmed, contradictions to resolve, recommended vault updates). Vault-first means you stop re-researching what's already in your notes.

### What do the research commands cost?
Approximate per-call costs as of 2026-04: `/x-read` ~$0.05, `/x-pulse` ~$0.13, `/research` ~$0.04, `/research-deep` ~$0.40-$0.80, `/youtube` ~$0.04. Costs for Grok calls are logged to `~/.research-toolkit/usage.log` for visibility. No hard caps — you're trusted to monitor your own spend.

### Can I use this on Windows or Linux?
The core vault commands work anywhere Claude Code runs. The research toolkit was tested on macOS — `install.sh` and the auto-open behavior assume macOS conventions (`~/.config`, `open` command). Pull requests welcome to add Windows and Linux paths.

### How do I update to the latest version?
```bash
cd ~/.claude/skills/obsidian-second-brain && git pull
```
Nothing to re-run. Commands pick up the new instructions automatically. See [CHANGELOG.md](CHANGELOG.md) for what's in each release.

### Where do I file issues or feature requests?
GitHub Issues: https://github.com/eugeniughelbur/obsidian-second-brain/issues. PRs welcome — see Contributing below.

---

## Philosophy

Most second brain tools make you the janitor.

This skill inverts that. You think, work, and talk. Claude handles the memory. Then it uses that memory to make you think better -- surfacing what you'd miss, challenging what you'd assume, connecting what you'd never link, and synthesizing patterns you didn't ask for.

The vault doesn't grow. It evolves.

**Your notes are the moat.**

Inspired by [Andrey Karpathy's LLM-Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

---

## Contributing

PRs welcome:
- New thinking tools
- Note type schemas (habits, books, investments)
- MCP integrations (Calendar, Linear, Slack)
- Alternative vault structures
- VS Code / Cursor setup guides

---

## Sponsors

Sponsorships help fund ongoing development of obsidian-second-brain — new commands, research-toolkit API costs, and ongoing maintenance.

[![Sponsor on GitHub](https://img.shields.io/badge/Sponsor-eugeniughelbur-EA4AAA?style=for-the-badge&logo=github-sponsors&logoColor=white)](https://github.com/sponsors/eugeniughelbur)

---

## Author

<div align="center">

<table>
<tr>
<td align="center" width="700">

Built by **Eugeniu Ghelbur** — AI Automation Engineer @ Single Grain

*If this skill helped you, the best thanks is following along.*

<a href="https://x.com/eugeniu_ghelbur"><img src="https://img.shields.io/badge/Follow_on_X-000?style=for-the-badge&logo=x&logoColor=white" alt="Follow on X" /></a>
<a href="https://www.linkedin.com/in/eugeniu-ghelbur/"><img src="https://img.shields.io/badge/Connect_on_LinkedIn-0A66C2?style=for-the-badge&logo=data:image/svg%2Bxml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0yMC40NDcgMjAuNDUyaC0zLjU1NHYtNS41NjljMC0xLjMyOC0uMDI3LTMuMDM3LTEuODUyLTMuMDM3LTEuODUzIDAtMi4xMzYgMS40NDUtMi4xMzYgMi45Mzl2NS42NjdIOS4zNTFWOWgzLjQxNHYxLjU2MWguMDQ2Yy40NzctLjkgMS42MzctMS44NSAzLjM3LTEuODUgMy42MDEgMCA0LjI2NyAyLjM3IDQuMjY3IDUuNDU1djYuMjg2ek01LjMzNyA3LjQzM2MtMS4xNDQgMC0yLjA2My0uOTI2LTIuMDYzLTIuMDY1IDAtMS4xMzguOTItMi4wNjMgMi4wNjMtMi4wNjMgMS4xNCAwIDIuMDY0LjkyNSAyLjA2NCAyLjA2MyAwIDEuMTM5LS45MjUgMi4wNjUtMi4wNjQgMi4wNjV6bTEuNzgyIDEzLjAxOUgzLjU1NVY5aDMuNTY0djExLjQ1MnpNMjIuMjI1IDBIMS43NzFDLjc5MiAwIDAgLjc3NCAwIDEuNzI5djIwLjU0MkMwIDIzLjIyNy43OTIgMjQgMS43NzEgMjRoMjAuNDUxQzIzLjIgMjQgMjQgMjMuMjI3IDI0IDIyLjI3MVYxLjcyOUMyNCAuNzc0IDIzLjIgMCAyMi4yMjIgMGguMDAzeiIvPjwvc3ZnPg%3D%3D" alt="Connect on LinkedIn" /></a>
<a href="https://theaioperator.io"><img src="https://img.shields.io/badge/Subscribe_on_Substack-FF6719?style=for-the-badge&logo=substack&logoColor=white" alt="Subscribe on Substack" /></a>
<a href="https://github.com/eugeniughelbur"><img src="https://img.shields.io/badge/Follow_on_GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="Follow on GitHub" /></a>

</td>
</tr>
</table>

</div>

---

## License

MIT

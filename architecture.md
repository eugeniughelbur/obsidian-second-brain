# obsidian-second-brain - Complete Architecture Document

## Purpose
Generate a visual architecture diagram (Mind Map, Infographic, or Slide Deck) of this system. This document describes every component, how they connect, and how data flows through the system.

---

## System Overview

obsidian-second-brain is a Claude Code skill that turns an Obsidian vault into a personal AI operating system. As of v0.5: 6 layers, 31 slash commands, 4 scheduled agents, 1 background agent, a research toolkit (Grok + Perplexity + YouTube), and a central config file (_CLAUDE.md) that ties everything together. Section 0 of `_CLAUDE.md` enforces the AI-first vault rule - every note is designed for future-Claude retrieval, not human reading.

---

## Core Architecture

### Entry Point: _CLAUDE.md
- Lives at the vault root
- Read by every Claude surface on session start (Claude Desktop, Claude Code, VS Code, terminal)
- Contains: folder structure map, naming conventions, frontmatter schemas, propagation rules, active context, kanban format rules
- Acts as the operating manual - no memory needed between sessions
- Updated by user or by /obsidian-init command

### Connection Layer: MCP Server (mcp-obsidian)
- Bridges Claude to the Obsidian vault
- Provides tools: get_file_contents, list_files_in_vault, search, append_content, write_file
- Fallback: direct filesystem read/write if MCP unavailable

---

## Layer 1: Vault Operations (14 commands)

Purpose: Automated vault management - saving, organizing, searching, maintaining.

### Commands and Data Flow:

1. **/obsidian-save** - Master save command
   - INPUT: Entire conversation
   - PROCESS: Spawns 5 parallel subagents (People, Projects, Tasks, Decisions, Ideas)
   - OUTPUT: Creates/updates notes in People/, Projects/, Tasks/, Ideas/, Boards/, Daily/
   - PROPAGATION: Updates kanban boards + today's daily note

2. **/obsidian-daily** - Daily note management
   - INPUT: Today's date + conversation context
   - PROCESS: Reads Templates/Daily Note.md, fills in sections
   - OUTPUT: Creates/updates Daily/YYYY-MM-DD.md

3. **/obsidian-log** - Dev/work session logging
   - INPUT: Conversation context (infers project)
   - PROCESS: Reads Templates/Dev Log.md, fills in work done, problems, decisions, next steps
   - OUTPUT: Creates Dev Logs/YYYY-MM-DD - Project Name.md
   - PROPAGATION: Links from project note (Recent Activity) + daily note

4. **/obsidian-task [desc]** - Task creation
   - INPUT: Task description (or inferred from conversation)
   - PROCESS: Infers priority (red/yellow/green), due date, linked project
   - OUTPUT: Adds card to correct kanban board column + optional Tasks/ note
   - PROPAGATION: Links from project note + daily note

5. **/obsidian-person [name]** - People notes
   - INPUT: Person name (fuzzy matched)
   - PROCESS: Searches vault for existing person, creates or updates
   - OUTPUT: Creates/updates People/Full Name.md with frontmatter
   - PROPAGATION: Logs interaction in daily note + People index

6. **/obsidian-decide [topic]** - Decision logging
   - INPUT: Conversation decisions (or filtered by topic)
   - PROCESS: Finds relevant project notes
   - OUTPUT: Appends to project note's Key Decisions section with date
   - PROPAGATION: Logs in daily note, cross-links if multiple projects

7. **/obsidian-capture [idea]** - Idea capture
   - INPUT: Idea text (or pulled from conversation)
   - PROCESS: Searches Ideas/ for related existing note
   - OUTPUT: Creates/updates Ideas/Title.md
   - PROPAGATION: Mentions in daily note

8. **/obsidian-find [query]** - Smart search
   - INPUT: Search query
   - PROCESS: Runs vault search + synonym variations
   - OUTPUT: Results with context (title, folder, excerpt, note type)

9. **/obsidian-recap [today|week|month]** - Time period summary
   - INPUT: Date range
   - PROCESS: Spawns parallel subagents (one per daily note in range) + dev logs + kanban tasks
   - OUTPUT: Narrative summary of the period

10. **/obsidian-review** - Structured review generation
    - INPUT: Weekly or monthly (inferred)
    - PROCESS: Reads daily notes, dev logs, active projects, completed tasks
    - OUTPUT: Creates Reviews/YYYY-MM-DD - Weekly Review.md
    - PROPAGATION: Links from last daily note of period

11. **/obsidian-board [name]** - Kanban board management
    - INPUT: Board name (fuzzy matched)
    - PROCESS: Reads board state, identifies overdue items
    - OUTPUT: Displays board + applies updates from conversation

12. **/obsidian-project [name]** - Project note management
    - INPUT: Project name (fuzzy matched)
    - PROCESS: Searches vault, creates or updates
    - OUTPUT: Creates/updates Projects/Project Name.md
    - PROPAGATION: Adds card to kanban board + links from daily note

13. **/obsidian-health** - Vault health audit
    - INPUT: Vault path
    - PROCESS: Runs vault_health.py, spawns 5 parallel subagents (Links, Duplicates, Frontmatter, Staleness, Orphans)
    - OUTPUT: Report grouped by severity (critical/warning/info)

14. **/obsidian-init** - Bootstrap _CLAUDE.md
    - INPUT: Existing vault
    - PROCESS: Spawns 4 parallel subagents (Dashboard, Templates, Boards, Samples)
    - OUTPUT: Generates _CLAUDE.md at vault root

---

## Layer 2: Thinking Tools (4 commands)

Purpose: Use vault history to generate insight, challenge assumptions, and surface hidden patterns.

### Commands and Data Flow:

15. **/obsidian-challenge** - Red-team ideas
    - INPUT: User's current claim/plan/assumption
    - PROCESS: Spawns 3 parallel subagents:
      - Decisions agent: searches Key Decisions sections for contradictions
      - Failures agent: searches dev logs, daily notes, archives for past failures
      - Contradictions agent: searches for notes where user held opposite position
    - OUTPUT: Structured "Red Team" analysis with cited vault evidence
    - PROPAGATION: Logs in daily note under Thinking section

16. **/obsidian-emerge** - Pattern detection
    - INPUT: Date range (default: last 30 days)
    - PROCESS: Spawns 4 parallel subagents:
      - Daily notes agent: extracts recurring topics, complaints, energy patterns
      - Dev logs agent: extracts repeated blockers, tools, architectural patterns
      - Decisions agent: looks for directional trends
      - Ideas agent: looks for thematic clusters
    - OUTPUT: Pattern Report - each pattern with evidence, interpretation, suggested action
    - PROPAGATION: Offers to save to Ideas/ + logs in daily note

17. **/obsidian-connect [A] [B]** - Cross-domain bridging
    - INPUT: Two topics/domains
    - PROCESS: For each domain, maps vault cluster (notes, backlinks, outgoing links). Finds shared links, tags, people, or semantic overlap between clusters.
    - OUTPUT: 3-5 concrete connections (structural analogies, transfer opportunities, collision ideas)
    - PROPAGATION: Offers to save to Ideas/ + logs in daily note

18. **/obsidian-graduate** - Idea to project pipeline
    - INPUT: Idea title/tag/keyword
    - PROCESS: Finds idea note, reads linked notes, researches vault for related projects/people/decisions
    - OUTPUT: Full project spec in Projects/ (goals, tasks, phases, open questions, related notes) + kanban board entries
    - PROPAGATION: Updates original idea note (status: graduated) + links from daily note

---

## Layer 3: Context Engine (1 command)

Purpose: Solve the "starting from zero" problem - full session continuity.

### Commands and Data Flow:

19. **/obsidian-world** - Identity and state loader
    - INPUT: None
    - PROCESS: Reads in order:
      1. Identity layer: SOUL.md, CORE_VALUES.md, Home.md/Dashboard.md
      2. Current state: Today's daily note + last 3 daily notes + active kanban boards + previous session digests
      3. Context: Active project notes (status: active) + recently mentioned people (last 7 days)
    - OUTPUT: Concise boot-up status (persona, priorities, open threads, overdue items, today so far)

---

## Layer 4: Scheduled Agents (4 agents, cron-based)

Purpose: Autonomous vault maintenance with zero user intervention.

### Agents:

- **obsidian-morning** - Daily at 8:00 AM
  - Creates today's daily note
  - Pulls overdue/due-today tasks from boards
  - Lists stale active projects (no activity in 7 days)

- **obsidian-nightly** - Daily at 10:00 PM
  - Reads today's daily note
  - Appends End of Day section (3-5 bullet summary)
  - Moves completed kanban tasks to Done column

- **obsidian-weekly** - Fridays at 6:00 PM
  - Runs /obsidian-recap week internally
  - Generates Reviews/YYYY-MM-DD - Weekly Review.md
  - Links from last daily note of the week

- **obsidian-health-check** - Sundays at 9:00 PM
  - Runs vault_health.py
  - Writes health report to Knowledge/
  - Never auto-fixes - report only

---

## Layer 5: Background Agent (PostCompact hook)

Purpose: Silent vault updates during active sessions.

### Flow:
1. User works in Claude Code normally
2. Context compaction occurs (automatic)
3. PostCompact hook fires → obsidian-bg-agent.sh
4. Shell script reads JSON summary from stdin
5. Spawns headless `claude -p` subprocess in vault directory
6. Agent reads _CLAUDE.md, scans session summary
7. Writes vault updates (people, projects, decisions, tasks, ideas)
8. Exits silently - user sees nothing
9. Log file: /tmp/obsidian-bg-agent.log

Safety: Never deletes, archives, or merges. Only adds or updates.

---

## Vault Folder Structure

```
Your Vault/
├── _CLAUDE.md              # Claude's operating manual
├── Home.md                 # Dashboard with Dataview queries
├── Daily/                  # Daily notes (YYYY-MM-DD.md)
├── Projects/               # Project notes
├── People/                 # Person notes
├── Ideas/                  # Captured ideas
├── Tasks/                  # Substantial task notes
├── Dev Logs/               # Work session logs
├── Reviews/                # Weekly/monthly reviews
├── Boards/                 # Kanban boards
├── Templates/              # Note templates
├── Knowledge/              # Health reports, references
└── SOUL.md                 # Identity file (optional)
```

---

## Data Flow Summary

```
User Conversation
       |
       v
  /obsidian-save ──> [5 parallel agents] ──> People/, Projects/, Tasks/, Ideas/, Boards/
       |                                              |
       v                                              v
  Daily/YYYY-MM-DD.md  <──── propagation ────  All created/updated notes
       ^
       |
  /obsidian-world (reads vault state at session start)
       ^
       |
  _CLAUDE.md (read by every Claude surface on boot)


Background:
  PostCompact hook ──> headless claude -p ──> vault updated silently

Scheduled:
  8 AM  ──> morning agent  ──> daily note + overdue tasks
  10 PM ──> nightly agent  ──> end of day summary + board cleanup
  Fri   ──> weekly agent   ──> review note
  Sun   ──> health agent   ──> audit report
```

---

## Parallel Subagent Map

| Command | Subagents spawned |
|---|---|
| /obsidian-save | People, Projects, Tasks, Decisions, Ideas |
| /obsidian-challenge | Decisions, Failures, Contradictions |
| /obsidian-emerge | Daily notes, Dev logs, Decisions, Ideas |
| /obsidian-health | Links, Duplicates, Frontmatter, Staleness, Orphans |
| /obsidian-recap | One agent per daily note in date range |
| /obsidian-init | Dashboard, Templates, Boards, Samples |

---

## Key Design Principles

1. **Search before create** - Never create duplicate notes
2. **Propagate everything** - Every write updates all linked notes (boards, daily note, project notes)
3. **No orphans** - Every note must be linked from somewhere
4. **Fuzzy matching** - All name arguments handle typos
5. **_CLAUDE.md is the source of truth** - Overrides all defaults
6. **Agents read, humans decide** - Thinking tools present evidence, user makes the call
7. **Vault compounds** - More writing = more context = more powerful AI partner

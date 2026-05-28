# Vault Schema Reference

## Default: Wiki-Style (LLM-First)

Optimized for vaults where Claude does most or all of the writing. The primary reader is the LLM, not the human. Obsidian is the storage engine; Claude is the interface.

```
Your Vault/
├── _CLAUDE.md                  ← Claude's operating manual
├── index.md                    ← Catalog of all pages (Claude reads this FIRST)
├── log.md                      ← Chronological log of every vault operation
├── SOUL.md                     ← Identity, values, communication style
├── CRITICAL_FACTS.md           ← ~120 tokens, always loaded: timezone, manager, location, company
│
├── raw/                        ← IMMUTABLE. Claude reads, never writes.
│   ├── articles/               ← Clipped articles, web pages
│   ├── transcripts/            ← Meeting notes, podcast transcripts
│   ├── pdfs/                   ← Documents, reports
│   └── videos/                 ← YouTube metadata + transcripts
│
├── wiki/                       ← Claude's workspace. Claude maintains everything here.
│   ├── entities/               ← People, companies, tools (flat, one file per entity)
│   ├── concepts/               ← Ideas, frameworks, methodologies
│   ├── projects/               ← Project notes
│   ├── daily/                  ← Daily notes (one per day)
│   ├── logs/                   ← Dev logs, work logs
│   ├── reviews/                ← Weekly / monthly reviews
│   ├── tasks/                  ← Standalone task notes
│   └── decisions/              ← ADRs (architectural decision records)
│
├── boards/                     ← Kanban boards (Personal, Work, etc.)
├── templates/                  ← Note templates (Templater plugin)
└── _trash/                     ← Soft-deleted notes
```

### Key principles:
- **raw/ is immutable** - original sources go here. Claude reads them but never modifies them. If a wiki page gets corrupted, re-derive from raw.
- **wiki/ is Claude's workspace** - Claude is the sole writer. Every entity, concept, and project lives here.
- **index.md is the front door** - Claude reads this first to navigate. Cheaper and faster than searching.
- **Flat folders over nested** - `wiki/entities/` is a flat list. Harder for humans to browse, perfect for Claude to grep and index.

---

## Alternative: Obsidian-Style (Human-First)

For users who browse their vault daily in Obsidian. Folders are organized for human spatial memory.

```
Your Vault/
├── _CLAUDE.md
├── index.md
├── log.md
├── Home.md                     ← Dashboard with dataview queries
│
├── Daily/                      ← Daily notes
├── Dev Logs/                   ← Technical work logs
├── Tasks/                      ← Standalone task notes
├── Projects/                   ← Project notes
├── People/                     ← One note per person
├── Boards/                     ← Kanban boards
│
├── Knowledge/                  ← Reference material, things learned
├── Learning/                   ← Books, courses, content consumed
├── Ideas/                      ← Idea captures
├── Content/                    ← Content calendar, drafts
│
├── Goals/                      ← Annual and life goals
├── Health/                     ← Health tracking
├── Finances/                   ← Monthly finance notes
├── Jobs/                       ← Employment / contract roles
├── Businesses/                 ← Companies you own
├── Mentions/                   ← Recognition log
├── Reviews/                    ← Weekly / monthly reviews
│
├── Templates/                  ← Note templates
└── _trash/                     ← Soft-deleted notes
```

---

## Folder Mapping (Wiki ↔ Obsidian)

| Wiki-style | Obsidian-style | What lives here |
|---|---|---|
| `raw/articles/` | `Knowledge/` | Original source material |
| `wiki/entities/` | `People/` + `Jobs/` + `Businesses/` | People, companies, tools |
| `wiki/concepts/` | `Ideas/` + `Learning/` | Ideas, frameworks, methodologies |
| `wiki/projects/` | `Projects/` | Active and archived projects |
| `wiki/daily/` | `Daily/` | Daily notes |
| `wiki/logs/` | `Dev Logs/` | Work session logs |
| `wiki/reviews/` | `Reviews/` | Weekly/monthly reviews |
| `wiki/tasks/` | `Tasks/` | Standalone task notes |
| `wiki/decisions/` | (in project notes) | ADRs |
| `boards/` | `Boards/` | Kanban boards |

---

## Frontmatter Schemas

### Daily Note
```yaml
---
date: 2026-03-24
tags:
  - daily
mood: 4          # 1-5 scale
energy: 3        # 1-5 scale
---
```

### Project Note
```yaml
---
date: 2026-03-24
tags:
  - project
status: active   # active | planning | completed | archived | on-hold
job: "[[Acme Corp]]"   # or Personal, [[Company Name]]
timeline:                # bi-temporal facts — status changes over time
  - fact: "status: planning"
    from: 2026-03-01
    until: 2026-03-15
    learned: 2026-03-01
  - fact: "status: active"
    from: 2026-03-15
    until: present
    learned: 2026-03-15
---
```

### Task Note
```yaml
---
date: 2026-03-24
tags:
  - task
status: in-progress   # in-progress | done | waiting | cancelled
project: "[[Project Name]]"
job: "[[Company]]"    # or Personal
requested_by: "[[Person Name]]"
due: 2026-03-28
---
```

### Entity Note (Person / Company / Tool)
```yaml
---
date: 2026-03-24
tags:
  - entity
  - person       # or: company, tool
role: "Senior Engineer"        # current role
company: "[[Acme Corp]]"       # current company
last_interaction: 2026-03-24
timeline:                       # bi-temporal facts — never delete, only append
  - fact: "CTO at Acme Corp"
    from: 2024-01-01            # event time: when the fact was true
    until: 2026-04-07
    learned: 2026-02-23         # transaction time: when the vault learned it
  - fact: "Architect at Acme Corp"
    from: 2026-04-07
    until: present
    learned: 2026-04-07
    source: "[[2026-04-07]]"    # where the vault learned it from
---
```

**Bi-temporal facts rule:** never overwrite a role, company, status, or location. Add a new entry to `timeline:` with:
- `from` / `until` - **event time**: when the fact was true in reality
- `learned` - **transaction time**: when the vault first recorded this fact
- `source` (optional) - where the vault learned it from (daily note, ingested source, etc.)

The `role:` and `company:` top-level fields always reflect the CURRENT state. The `timeline:` preserves full history.

This enables:
- Historical queries ("who was CTO in January?")
- Reflective thinking ("you believed X on Tuesday, but after ingesting Y on Wednesday, your understanding shifted to Z")
- Smart reconciliation (different roles at different times = not a contradiction)
- Audit trail (when did the vault learn each fact, and from what source?)

### Source Note (raw/)
```yaml
---
date: 2026-03-24
tags:
  - source
source_type: article   # article | transcript | pdf | video
source_url: "https://..."
content_hash: ""       # for drift detection
---
```

### Concept Note
```yaml
---
date: 2026-03-24
tags:
  - concept
status: active   # active | graduated | archived
related_projects: []
---
```

### Dev Log
```yaml
---
date: 2026-03-24
tags:
  - devlog
project: "[[Project Name]]"
job: "[[Company]]"
---
```

### Decision Record (ADR)
```yaml
---
date: 2026-03-24
tags:
  - decision-record
status: accepted   # accepted | superseded | deprecated
---
```

### Kanban Board
```yaml
---
kanban-plugin: board
---
```

### Goal
```yaml
---
date: 2026-01-01
tags:
  - goal
category: "career"   # career | health | financial | personal | relationship
status: active       # active | completed | paused | abandoned
progress: 35         # 0-100 integer
target_date: 2026-12-31
---
```

---

## Naming Conventions

| Type | Pattern | Example |
|---|---|---|
| Daily note | `YYYY-MM-DD.md` | `2026-03-24.md` |
| Dev log | `YYYY-MM-DD — Description.md` | `2026-03-24 — API Gateway Debug.md` |
| Entity | Full name (flat) | `Jane Smith.md`, `Acme Corp.md` |
| Concept | Descriptive title | `LLM-Wiki Pattern.md` |
| Project | Proper name | `My Project Name.md` |
| Source | `YYYY-MM-DD — Source Title.md` | `2026-04-06 — Karpathy LLM Wiki.md` |
| Decision | `ADR-YYYY-MM-DD — Title.md` | `ADR-2026-04-06 — Wiki Style Default.md` |
| Archive prefix | `_archived_` | `_archived_Old Project.md` |

---

## Dataview Query Patterns

### All active projects
```dataview
TABLE status, job FROM "wiki/projects"
WHERE contains(tags, "project") AND status = "active"
SORT file.name ASC
```

### Recent daily notes
```dataview
TABLE date, mood, energy FROM "wiki/daily"
SORT date DESC
LIMIT 7
```

### All entities (people, companies, tools)
```dataview
TABLE role, company, last_interaction FROM "wiki/entities"
WHERE contains(tags, "entity")
SORT last_interaction DESC
```

### Recent sources ingested
```dataview
TABLE source_type, source_url FROM "raw"
SORT date DESC
LIMIT 10
```

#!/usr/bin/env python3
"""
bootstrap_vault.py - Obsidian Second Brain Bootstrapper

Creates a complete, production-ready Obsidian vault from scratch.
Generates folder structure, templates, Home dashboard, kanban boards,
and a _CLAUDE.md so Claude can operate the vault from day one.

AI-first rule: every template emitted by this script must produce
notes that pass `hooks/validate-ai-first.sh`. That means the template
frontmatter must include `date:`, `type:`, `tags:`, and `ai-first: true`,
and the body must include a `## For future Claude` preamble. See
`references/ai-first-rules.md` for the full spec. When adding a new
template here, follow the existing shape.

Usage:
    python bootstrap_vault.py --path ~/my-vault --name "Your Name"
    python bootstrap_vault.py --path ~/my-vault --name "Your Name" --preset researcher
    python bootstrap_vault.py --path ~/my-vault --name "You" --mode assistant --subject "Boss Name"

Options:
    --path        Path where the vault should be created (required)
    --name        Your full name (required)
    --preset      Vault preset: default | executive | builder | creator | researcher
                  (default: "default" - Life OS layout)
    --mode        Operating mode: personal | assistant (default: personal)
    --subject     Subject name (required when --mode=assistant)
    --jobs        Comma-separated list of jobs/companies (default: "Work")
                  Only used by the "default" preset.
    --no-sidebiz  Omit the side business module (default preset only)
"""

import argparse
import sys
from pathlib import Path
from datetime import date

# Force UTF-8 stdout/stderr so emoji print statements work on Windows (cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

TODAY = date.today().isoformat()
YEAR = date.today().year


# ── Preset definitions ────────────────────────────────────────────────────────
# Each preset declares its folder list, kanban boards, _CLAUDE.md folder map,
# Home dashboard body, and optional extra seed files.

PRESETS = {
    "default": {
        "purpose": "Life OS - work, personal, finances",
        "folders": [
            "Daily", "Dev Logs", "Tasks", "Projects", "People",
            "Boards", "Knowledge", "Learning", "Ideas", "Content/LinkedIn", "Content/X",
            "Goals", "Health", "Finances/Spending", "Jobs", "Businesses",
            "Mentions", "Reviews", "Life Chapters", "Templates", "_trash",
        ],
        "boards": [],  # default preset builds boards from --jobs list + Personal
        "kanban_columns": [
            "📥 Backlog", "📋 This Week", "🔨 In Progress",
            "⏳ Waiting On", "📅 Next Week", "✅ Done",
        ],
    },
    "executive": {
        "purpose": "Decisions, people, meetings, strategic planning",
        "folders": [
            "Daily", "People", "Meetings", "Decisions", "OKRs",
            "Projects", "Boards", "Knowledge", "Reviews",
            "Templates", "_trash",
        ],
        "boards": [("OKRs", ["🎯 OKRs", "📅 Quarterly", "📋 Weekly", "✅ Done"])],
        "kanban_columns": ["🎯 OKRs", "📅 Quarterly", "📋 Weekly", "✅ Done"],
    },
    "builder": {
        "purpose": "Projects, dev logs, architecture, debugging",
        "folders": [
            "Daily", "Projects", "Dev Logs", "Architecture", "Debugging",
            "Boards", "Knowledge", "Tasks", "Ideas",
            "Templates", "_trash",
        ],
        "boards": [("Engineering", ["📥 Backlog", "🏃 Sprint", "🔨 In Progress", "✅ Done"])],
        "kanban_columns": ["📥 Backlog", "🏃 Sprint", "🔨 In Progress", "✅ Done"],
    },
    "creator": {
        "purpose": "Content calendar, ideas pipeline, audience, publishing",
        "folders": [
            "Daily", "Content/LinkedIn", "Content/X", "Content/Blog",
            "Ideas", "Audience", "Publishing",
            "Boards", "Templates", "_trash",
        ],
        "boards": [("Pipeline", ["💡 Ideas", "✏️ Drafts", "📅 Scheduled", "✅ Published"])],
        "kanban_columns": ["💡 Ideas", "✏️ Drafts", "📅 Scheduled", "✅ Published"],
    },
    "researcher": {
        "purpose": "Sources, literature, hypotheses, methodology, synthesis",
        "folders": [
            "Daily", "Sources", "Literature", "Hypotheses", "Methodology",
            "Synthesis", "Reading Queue", "Projects", "People",
            "Boards", "Templates", "_trash",
        ],
        "boards": [("Research", ["📚 Reading", "🔬 Processing", "🧬 Synthesized", "✅ Done"])],
        "kanban_columns": ["📚 Reading", "🔬 Processing", "🧬 Synthesized", "✅ Done"],
    },
}


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"  ✓ {path}")


def render_kanban(columns: list) -> str:
    column_blocks = "\n\n\n\n".join(f"## {c}" for c in columns)
    collapse = ",".join(["false"] * len(columns))
    return f"""---

kanban-plugin: board

---

{column_blocks}



%% kanban:settings
```
{{"kanban-plugin":"board","list-collapse":[{collapse}]}}
```
%%
"""


def folder_map_table(folders: list) -> str:
    descriptions = {
        "Daily": "One note per day. Named `YYYY-MM-DD.md`",
        "Dev Logs": "Technical work logs - dated, project-tagged",
        "Tasks": "Standalone task notes (linked from boards)",
        "Projects": "Active and archived projects",
        "People": "One note per person",
        "Boards": "Kanban boards",
        "Knowledge": "Reference material",
        "Learning": "Books, courses, content consumed",
        "Ideas": "Captured ideas - graduate to projects when ready",
        "Goals": "Annual and life goals",
        "Health": "Health tracking and habits",
        "Mentions": "Recognition and shoutouts",
        "Jobs": "Employment and contract roles",
        "Businesses": "Companies I own",
        "Templates": "Note templates",
        "Reviews": "Weekly and monthly reviews",
        "Life Chapters": "Major life phases and transitions",
        "Meetings": "Meeting notes - one per meeting",
        "Decisions": "ADR-style decision records",
        "OKRs": "Objectives and key results",
        "Architecture": "System design and architecture notes",
        "Debugging": "Bug investigations and root-cause notes",
        "Audience": "Audience research and persona notes",
        "Publishing": "Published content archive",
        "Sources": "Original source material - articles, papers, transcripts",
        "Literature": "Literature notes - your read of each source",
        "Hypotheses": "Hypotheses being tested or refined",
        "Methodology": "Research methods and protocols",
        "Synthesis": "Cross-source synthesis pages",
        "Reading Queue": "What to read next",
        "_trash": "Deleted notes (Obsidian default)",
    }
    rows = []
    for f in folders:
        # Use top-level segment for description lookup
        key = f.split("/")[0]
        if key == "Content":
            sub = f.split("/", 1)[1] if "/" in f else ""
            desc = f"Content drafts for {sub}" if sub else "Content calendar and post drafts"
        elif key == "Finances":
            sub = f.split("/", 1)[1] if "/" in f else ""
            desc = f"Finance notes ({sub})" if sub else "Finance notes"
        else:
            desc = descriptions.get(key, "-")
        rows.append(f"| `{f}/` | {desc} |")
    return "\n".join(rows)


def claude_md_personal(name: str, preset_key: str, preset: dict, jobs: list, vault_path: Path) -> str:
    primary_job = jobs[0] if jobs else "Work"
    folder_table = folder_map_table(preset["folders"])
    if preset_key == "default":
        jobs_table = "\n".join(f"| `Jobs/{j}.md` | Employment / contract role |" for j in jobs)
        if jobs_table:
            folder_table = folder_table + "\n" + jobs_table
        key_files = (
            "- **Dashboard:** `Home.md`\n"
            f"- **Work Board:** `Boards/{primary_job}.md`\n"
            "- **Personal Board:** `Boards/Personal.md`\n"
            "- **Mentions Log:** `Mentions/Mentions Log.md`"
        )
    else:
        board_lines = [f"- **{b[0]} Board:** `Boards/{b[0]}.md`" for b in preset["boards"]]
        key_files = "- **Dashboard:** `Home.md`\n" + "\n".join(board_lines)

    return f"""# Claude Operating Manual - {name}'s Vault

> Read this file before doing anything in this vault.
> This is the single source of truth for how Claude operates here.

---

## Vault Identity

- **Owner:** {name}
- **Preset:** {preset_key}
- **Mode:** personal
- **Primary purpose:** {preset["purpose"]}
- **Last updated:** {TODAY}

---

## Folder Map

| Folder | Purpose |
|---|---|
{folder_table}

---

## Key Files

{key_files}

---

## Auto-Save Rules

Claude should auto-save the following **without asking**:
- Decisions made in conversation → relevant project note + daily note
- New people mentioned → People/ (create stub if needed)
- Tasks assigned or committed to → kanban board + Tasks/ note
- Dev work done → Dev Logs/ + project note + daily note
- Mentions/recognition → Mentions Log + person's note + daily note
- Completed tasks → move on kanban to ✅ Done

Claude should **ask before saving**:
- Anything in Finances/ with personal financial data
- Anything involving deleting or archiving an existing note

---

## Naming Conventions

- Daily notes: `YYYY-MM-DD.md`
- Dev logs: `YYYY-MM-DD - Description.md`
- People: Full name (e.g. `Jane Smith.md`)
- Archive prefix: `_archived_`

---

## Kanban Convention

Priority: 🔴 critical · 🟡 important · 🟢 low

Active item:
```
- [ ] 🔴 **Title** · @{{YYYY-MM-DD}}
\tDescription. [[Related Project]] [[Person]]
```

Done item:
```
- [x] ~~🔴 **Title**~~ ✅ Date
```

---

## Propagation Rules

| Event | Also update |
|---|---|
| New project | Board (Backlog) + today's daily note |
| Task done | Board (Done) + project note + daily note |
| Dev session | Dev Logs/ + project note + daily note |
| Person interaction | Daily note + their People/ note |
| Decision made | Project note (Key Decisions) + daily note |
| Mention/recognition | Mentions Log + person's note + daily note |

---

*Generated by obsidian-second-brain bootstrap script (preset: {preset_key}).*
*Regenerate: "Claude, update my _CLAUDE.md"*
"""


def claude_md_assistant(operator: str, subject: str, preset_key: str, preset: dict, vault_path: Path) -> str:
    folder_table = folder_map_table(preset["folders"])
    board_lines = [f"- **{b[0]} Board:** `Boards/{b[0]}.md`" for b in preset["boards"]]
    key_files = "- **Dashboard:** `Home.md`\n" + ("\n".join(board_lines) if board_lines else "")

    return f"""# Claude Operating Manual - {subject}'s Vault

> Read this file before doing anything in this vault.
> This vault is maintained BY {operator} FOR {subject}.

---

## Vault Identity

- **Subject:** {subject} - the person this vault is about
- **Operator:** {operator} - the person who maintains this vault
- **Vault path:** {vault_path}
- **Preset:** {preset_key}
- **Mode:** assistant
- **Primary purpose:** {preset["purpose"]}
- **Last updated:** {TODAY}

---

## Operating Mode: Assistant

This vault is operated on behalf of someone else. Key differences from personal mode:

- **Voice**: write in {subject}'s voice and perspective, not the operator's
- **Capture logic**: save what matters to {subject}, not what matters to the operator
- **Synthesis focus**: surface patterns relevant to {subject}'s goals and decisions
- **Privacy**: the operator may not have full context - ask before saving sensitive topics
- **Decision records**: always note WHO made the decision (subject or operator)

---

## Subject Profile

- **Role:** [fill in]
- **Company:** [fill in]
- **Communication style:** [fill in]
- **Priorities:** [fill in]
- **Key people:** [fill in]

---

## Operator Rules

- Save everything from conversations the operator has ABOUT the subject
- Flag when the operator's interpretation might differ from the subject's intent
- Keep a clear audit trail - the subject should be able to review what was saved and why
- Never mix the operator's personal notes into this vault

---

## Folder Map

| Folder | Purpose |
|---|---|
{folder_table}

---

## Key Files

{key_files}

---

## Naming Conventions

- Daily notes: `YYYY-MM-DD.md`
- People: Full name (e.g. `Jane Smith.md`)
- Archive prefix: `_archived_`

---

## Kanban Convention

Priority: 🔴 critical · 🟡 important · 🟢 low

Active item:
```
- [ ] 🔴 **Title** · @{{YYYY-MM-DD}}
\tDescription. [[Related Project]] [[Person]]
```

Done item:
```
- [x] ~~🔴 **Title**~~ ✅ Date
```

---

*Generated by obsidian-second-brain bootstrap script (preset: {preset_key}, mode: assistant).*
"""


def render_home(name: str, preset_key: str, preset: dict, jobs: list, mode: str, subject: str = "") -> str:
    title = f"{name}'s Life OS" if (preset_key == "default" and mode == "personal") else (
        f"{subject}'s Vault" if mode == "assistant" else f"{name}'s {preset_key.title()} Vault"
    )

    if preset_key == "default":
        primary_job = jobs[0] if jobs else "Work"
        nav = (
            "| Work | Life | System |\n"
            "|------|------|--------|\n"
            f"| [[Boards/{primary_job}\\|📋 Work Board]] | [[Goals/{YEAR} Goals\\|🎯 Goals]] | [[Templates/\\|📝 Templates]] |\n"
            "| [[Boards/Personal\\|📋 Personal]] | [[Finances/Income Streams\\|💵 Income]] | [[Mentions/Mentions Log\\|💬 Mentions]] |\n"
            "| [[Projects/\\|🔨 Projects]] | [[Health/Health Dashboard\\|🏋️ Health]] | [[People/\\|👥 People]] |"
        )
    else:
        board_links = " · ".join(f"[[Boards/{b[0]}\\|📋 {b[0]}]]" for b in preset["boards"])
        folder_links = " · ".join(f"[[{f.split('/')[0]}/\\|📁 {f.split('/')[0]}]]"
                                  for f in preset["folders"]
                                  if "/" not in f and f not in ("Boards", "Templates", "_trash"))
        nav = f"{board_links}\n\n{folder_links}"

    queries = """## 📅 Recent Daily Notes

```dataview
TABLE WITHOUT ID file.link AS "Day", mood AS "Mood", energy AS "Energy"
FROM "Daily"
SORT date DESC
LIMIT 7
```

---

## 📊 Vault Stats

```dataviewjs
const all = dv.pages("");
dv.paragraph(`📝 **${all.length}** total notes`);
```
"""

    return f"""---
date: {TODAY}
tags:
  - home
aliases:
  - Dashboard
---

# 🧠 {title}

> Claude automatically saves everything important from every conversation.

---

## ⚡ Quick Navigation

{nav}

---

{queries}
"""


def write_core_templates(vault: Path):
    """Templates shared by all presets."""
    write(vault / "Templates/Daily Note.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: daily
tags:
  - daily
ai-first: true
mood:
energy:
---

# <% tp.date.now("YYYY-MM-DD") %> - <% tp.date.now("dddd") %>

## For future Claude

Daily note for this date. Captures what was worked on, who was met, decisions made, energy, and the day's intention. Pull this when reconstructing what happened on a given day.

---

## 🌅 Morning

**Intention:** <% tp.file.cursor() %>

**Grateful for:**
1.
2.
3.

---

## 🎯 Today's Focus

### 🔴 #1 -

### 🟡 #2 -

### 🟢 #3 -

---

## 💼 Work Log



---

## 🏠 Personal



---

## ✅ Habits

- [ ] Exercised
- [ ] Read/learned something
- [ ] Reached out to someone

---

## 🌙 Evening Review

**What went well:**

**What didn't:**

**Tomorrow's #1 priority:**
""")

    write(vault / "Templates/Project.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: project
tags:
  - project
ai-first: true
status: active
job:
---

# <% tp.file.title %>

## For future Claude

Project note. Captures overview, architecture, key decisions, and related tasks. Pull this when reasoning about the project's direction, prior decisions, or current scope.

## Overview
<% tp.file.cursor() %>

## Architecture


## Key Decisions


## Links


## Related Tasks

```dataview
TABLE WITHOUT ID file.link AS "Task", status AS "Status"
FROM "Tasks"
WHERE contains(file.outlinks, this.file.link)
SORT date DESC
```

## Recent Activity

```dataview
LIST FROM "Daily"
WHERE contains(file.outlinks, this.file.link)
SORT date DESC
LIMIT 5
```
""")

    write(vault / "Templates/Person.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: person
tags:
  - person
ai-first: true
role:
company:
relationship_strength:
last_interaction: <% tp.date.now("YYYY-MM-DD") %>
follow_up_date:
contact_email:
location:
---

# <% tp.file.title %>

## For future Claude

Person note. Captures role, company, relationship context, what they care about, and how to help each other. Pull this before any interaction with this person or when reasoning about who knows what.

## About
<% tp.file.cursor() %>

## What They Care About


## How We Can Help Each Other


## Notes


---

## Interactions

```dataview
LIST FROM "Daily"
WHERE contains(file.outlinks, this.file.link)
SORT date DESC
LIMIT 15
```
""")

    write(vault / "Templates/Task.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: task
tags:
  - task
ai-first: true
status: in-progress
project:
job:
requested_by:
due:
---

# <% tp.file.title %>

## For future Claude

Task note. Captures requirements, implementation notes, and what was delivered. Pull this when reconstructing why a piece of work was done or what was actually shipped vs requested.

## Requirements
<% tp.file.cursor() %>

## Implementation Notes


## Delivered

## Related
""")

    write(vault / "Templates/Dev Log.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: devlog
tags:
  - devlog
ai-first: true
project:
job:
---

# Dev Log - <% tp.date.now("YYYY-MM-DD") %>

## For future Claude

Engineering log for this date. Captures what was worked on, problems solved, decisions made, and next steps. Pull this when reconstructing the chain of technical decisions on a project.

## What I Worked On
<% tp.file.cursor() %>

## Problems Solved


## Decisions Made


## Next Steps
- [ ]
""")


def write_preset_extras(vault: Path, preset_key: str):
    """Preset-specific templates and seed files."""
    if preset_key == "default":
        write(vault / "Templates/Goal.md", f"""---
date: <% tp.date.now("YYYY-MM-DD") %>
type: goal
tags:
  - goal
ai-first: true
category:
status: active
progress: 0
target_date: {YEAR}-12-31
---

# <% tp.file.title %>

## For future Claude

Goal note. Captures why this goal matters, success criteria, milestones, and progress. Pull this when assessing whether work being proposed actually moves toward a stated goal.

## Why This Matters
<% tp.file.cursor() %>

## Success Criteria


## Milestones
- [ ]

## Progress Log
""")

        write(vault / "Templates/Mention.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: mention
tags:
  - mention
ai-first: true
source:
from:
context:
---

# <% tp.file.title %>

## For future Claude

Mention note. Captures a moment when someone recognized work publicly (Slack, email, meeting, LinkedIn). Pull these to surface social proof, track recurring advocates, or reconstruct who said what about a project.

## What Was Said
<% tp.file.cursor() %>

## Context


## My Takeaway
""")

        write(vault / f"Goals/{YEAR} Goals.md", f"""---
date: {TODAY}
tags:
  - goal
---

# {YEAR} Goals

```dataview
TABLE WITHOUT ID file.link AS "Goal", category, progress + "%" AS "Progress", status
FROM "Goals"
WHERE contains(tags, "goal") AND status = "active"
SORT progress DESC
```
""")

        write(vault / "Mentions/Mentions Log.md", f"""---
date: {TODAY}
tags:
  - log
---

# Mentions Log

Every time someone publicly recognizes your work - in Slack, email, meetings, LinkedIn.

```dataview
TABLE WITHOUT ID file.link AS "Mention", date, from, source, context
FROM "Mentions"
WHERE contains(tags, "mention")
SORT date DESC
```
""")

        write(vault / "Health/Health Dashboard.md", f"""---
date: {TODAY}
tags:
  - health
---

# Health Dashboard

## Weekly Habits

```dataview
TABLE WITHOUT ID file.link AS "Day", date AS "Date"
FROM "Daily"
SORT date DESC
LIMIT 14
```

## Notes
""")

        write(vault / "Content/Content Calendar.md", f"""---
date: {TODAY}
tags:
  - content
---

# Content Calendar

```dataview
TABLE WITHOUT ID file.link AS "Post", platform, status, published_date
FROM "Content"
WHERE contains(tags, "content") AND file.name != "Content Calendar"
SORT date DESC
```
""")
        return

    if preset_key == "executive":
        write(vault / "Templates/Meeting.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: meeting
tags:
  - meeting
ai-first: true
attendees:
duration:
---

# <% tp.file.title %>

## For future Claude

Meeting note. Captures attendees, agenda, decisions, action items, and free-form notes. Pull this when reconstructing what was decided in a meeting or what commitments were made.

## Agenda
<% tp.file.cursor() %>

## Decisions

## Action Items
- [ ]

## Notes
""")
        write(vault / "Templates/Decision.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: decision
tags:
  - decision
ai-first: true
status: decided
context:
---

# ADR - <% tp.file.title %>

## For future Claude

Decision record (ADR). Captures the context, options considered, the decision, and its consequences. Pull this when a similar decision comes up again, or when reconstructing why the system is shaped the way it is.

## Context

## Options Considered

## Decision

## Consequences
""")
        write(vault / "Templates/OKR.md", f"""---
date: <% tp.date.now("YYYY-MM-DD") %>
type: okr
tags:
  - okr
ai-first: true
quarter:
status: active
progress: 0
---

# <% tp.file.title %>

## For future Claude

OKR note. Captures the objective, key results, and progress over the quarter. Pull this when reasoning about whether current work is aligned to a stated objective.

## Objective

## Key Results
- [ ] KR1 -
- [ ] KR2 -
- [ ] KR3 -

## Progress Log
""")
        return

    if preset_key == "builder":
        write(vault / "Templates/Architecture.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: architecture
tags:
  - architecture
ai-first: true
project:
---

# <% tp.file.title %>

## For future Claude

Architecture note. Captures the problem, constraints, design, tradeoffs, and open questions. Pull this when extending a system, debating a refactor, or onboarding to a component.

## Problem

## Constraints

## Design

## Tradeoffs

## Open Questions
""")
        write(vault / "Templates/Debug.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: debug
tags:
  - debug
ai-first: true
project:
status: investigating
---

# Bug - <% tp.file.title %>

## For future Claude

Bug investigation note. Captures the symptom, repro steps, investigation trail, root cause, and fix. Pull this when a similar symptom comes up again or when reasoning about why a fix was shaped a certain way.

## Symptom

## Repro

## Investigation

## Root Cause

## Fix
""")
        return

    if preset_key == "creator":
        write(vault / "Templates/Post.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: post
tags:
  - content
ai-first: true
platform:
status: draft
hook:
---

# <% tp.file.title %>

## For future Claude

Content post note. Captures the hook, body, CTA, and platform variants for a piece of public-facing content. Pull this to reconstruct what was published, where it went, and which hooks worked.

## Hook

## Body

## CTA

## Variants
""")
        write(vault / "Templates/Audience Note.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: audience
tags:
  - audience
ai-first: true
segment:
---

# <% tp.file.title %>

## For future Claude

Audience segment note. Captures who they are, what they want, what they read, and the hooks that work for them. Pull this before drafting content aimed at this segment.

## Who They Are

## What They Want

## What They Read

## Hooks That Work
""")
        return

    if preset_key == "researcher":
        write(vault / "Templates/Source.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: source
tags:
  - source
ai-first: true
source_kind:
authors:
year:
url:
---

# <% tp.file.title %>

## For future Claude

Source note (book, paper, podcast, video, article). Captures citation, abstract or summary, and raw notes. `source_kind` distinguishes the form (book/paper/podcast/etc.). Pull this when reasoning about what's been read on a topic.

## Citation

## Abstract / Summary

## Raw Notes
""")
        write(vault / "Templates/Literature Note.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: literature
tags:
  - literature
ai-first: true
source:
---

# <% tp.file.title %>

## For future Claude

Literature note. Distillation of one source's key claims, methodology, critique, and connections to other ideas. Pull this when reasoning about what one specific source argues, separate from the broader landscape.

## Source
[[<% tp.file.title %>]]

## Key Claims

## Methodology

## Critique

## Connections
""")
        write(vault / "Templates/Hypothesis.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: hypothesis
tags:
  - hypothesis
ai-first: true
status: open
confidence: medium
---

# <% tp.file.title %>

## For future Claude

Hypothesis note. Captures a testable statement, predictions, evidence for and against, and a verdict. Pull this when reasoning about open questions or when new evidence arrives that could update an open hypothesis.

## Statement

## Predictions

## Evidence For

## Evidence Against

## Verdict
""")
        write(vault / "Reading Queue/_Queue.md", f"""---
date: {TODAY}
tags:
  - queue
---

# Reading Queue

```dataview
TABLE WITHOUT ID file.link AS "Source", type, year, status
FROM "Sources"
SORT date DESC
```
""")
        return


def bootstrap(vault: Path, name: str, preset_key: str, mode: str, subject: str,
              jobs: list, include_sidebiz: bool):
    preset = PRESETS[preset_key]

    print(f"\n🧠 Bootstrapping vault: {vault}")
    print(f"   Owner: {name}")
    print(f"   Preset: {preset_key}")
    print(f"   Mode: {mode}{' (subject: ' + subject + ')' if mode == 'assistant' else ''}")
    if preset_key == "default":
        print(f"   Jobs: {', '.join(jobs)}")
    print()

    # ── Folders ──────────────────────────────────────────────────────────────
    folders = list(preset["folders"])
    if preset_key == "default" and include_sidebiz:
        folders += ["Side Biz/Deals/Location1", "Side Biz/Deals/Location2"]

    for f in folders:
        (vault / f).mkdir(parents=True, exist_ok=True)
    print("📁 Folders created")

    # ── _CLAUDE.md ────────────────────────────────────────────────────────────
    if mode == "assistant":
        write(vault / "_CLAUDE.md", claude_md_assistant(name, subject, preset_key, preset, vault))
    else:
        write(vault / "_CLAUDE.md", claude_md_personal(name, preset_key, preset, jobs, vault))

    # ── Home ──────────────────────────────────────────────────────────────────
    write(vault / "Home.md", render_home(name, preset_key, preset, jobs, mode, subject))

    # ── Kanban Boards ─────────────────────────────────────────────────────────
    if preset_key == "default":
        for job in jobs:
            write(vault / f"Boards/{job}.md", render_kanban(preset["kanban_columns"]))
        write(vault / "Boards/Personal.md", render_kanban(["📥 Backlog", "📋 This Week", "✅ Done"]))
    else:
        for board_name, columns in preset["boards"]:
            write(vault / f"Boards/{board_name}.md", render_kanban(columns))

    # ── Templates ─────────────────────────────────────────────────────────────
    write_core_templates(vault)
    write_preset_extras(vault, preset_key)

    # ── .obsidian stub ────────────────────────────────────────────────────────
    (vault / ".obsidian").mkdir(exist_ok=True)
    if not (vault / ".obsidian/app.json").exists():
        write(vault / ".obsidian/app.json", "{}")

    print(f"\n✅ Vault bootstrapped at: {vault}")
    print("\n📋 Recommended Obsidian plugins:")
    print("   • Dataview  - powers the dashboard queries")
    print("   • Templater - powers the Templates/ folder")
    print("   • Kanban    - powers the Boards/ folder")
    print("   • Calendar  - daily note navigation")
    print("\n🤖 Claude MCP config:")
    print(f'   "obsidian-vault": {{"command": "npx", "args": ["-y", "mcp-obsidian", "{vault}"]}}')
    print("\n🧠 _CLAUDE.md is ready - Claude will read it automatically on every session.")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap an Obsidian Second Brain vault")
    parser.add_argument("--path", required=True, help="Path to create the vault")
    parser.add_argument("--name", required=True, help="Your full name")
    parser.add_argument("--preset", default="default", choices=sorted(PRESETS.keys()),
                        help="Vault preset (default: default)")
    parser.add_argument("--mode", default="personal", choices=["personal", "assistant"],
                        help="Operating mode (default: personal)")
    parser.add_argument("--subject", default="", help="Subject name (required when --mode=assistant)")
    parser.add_argument("--jobs", default="Work", help="Comma-separated job/company names (default preset only)")
    parser.add_argument("--no-sidebiz", action="store_true", help="Omit side business module (default preset only)")
    args = parser.parse_args()

    if args.mode == "assistant" and not args.subject:
        parser.error("--subject is required when --mode=assistant")

    vault = Path(args.path).expanduser().resolve()
    if vault.exists() and any(p for p in vault.iterdir() if p.name != ".obsidian"):
        print(f"⚠️  {vault} already exists and is not empty.")
        try:
            confirm = input("Continue anyway? This may overwrite files. [y/N] ").strip().lower()
        except EOFError:
            confirm = "n"
        if confirm != "y":
            print("Aborted.")
            sys.exit(1)

    jobs = [j.strip() for j in args.jobs.split(",") if j.strip()]
    bootstrap(vault, args.name, args.preset, args.mode, args.subject,
              jobs, include_sidebiz=not args.no_sidebiz)


if __name__ == "__main__":
    main()

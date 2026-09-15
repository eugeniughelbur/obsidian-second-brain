#!/usr/bin/env python3
"""
bootstrap_vault.py - Obsidian Second Brain Bootstrapper

Creates a complete, production-ready Obsidian vault from scratch.
Generates folder structure, templates, Home dashboard, kanban boards,
and a _CLAUDE.md so Claude can operate the vault from day one.

AI-first rule: every template emitted by this script must produce
notes that pass `hooks/validate-ai-first.sh`. That means the template
frontmatter must include `date:`, `type:`, `tags:`, and `ai-first: true`,
and the body must include a `## For future agent` preamble. See
`references/ai-first-rules.md` for the full spec. When adding a new
template here, follow the existing shape.

Usage:
    python bootstrap_vault.py --path ~/my-vault --name "Your Name"
    python bootstrap_vault.py --path ~/my-vault --name "Your Name" --preset researcher
    python bootstrap_vault.py --path ~/my-vault --name "You" --mode assistant --subject "Boss Name"
    python bootstrap_vault.py --path ~/my-vault --name "Your Name" --style wiki

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
    --style       Folder layout: obsidian | wiki (default: obsidian)
                  obsidian - Daily/, People/, Projects/ and the preset's topic folders
                  wiki     - wiki/daily/, wiki/entities/, wiki/projects/, boards/, templates/
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import NamedTuple

# Force UTF-8 stdout/stderr so emoji print statements work on Windows (cp1252).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

TODAY = date.today().isoformat()
YEAR = date.today().year

TEMPLATE_DIR = Path(__file__).parent.parent / "references" / "bases"

# Maps template filename → (output filename, placeholder to replace)
BASE_TEMPLATES: dict[str, tuple[str, str]] = {
    "projects.base.template": ("Projects.base", "{{PROJECTS_FOLDER}}"),
    "people.base.template":   ("People.base",   "{{PEOPLE_FOLDER}}"),
    "tasks.base.template":    ("Tasks.base",    "{{TASKS_FOLDER}}"),
    "daily.base.template":    ("Daily.base",    "{{DAILY_FOLDER}}"),
}

OBSIDIAN_FOLDERS = {
    "{{PROJECTS_FOLDER}}": "Projects",
    "{{PEOPLE_FOLDER}}":   "People",
    "{{TASKS_FOLDER}}":    "Tasks",
    "{{DAILY_FOLDER}}":    "Daily",
}

WIKI_FOLDERS = {
    "{{PROJECTS_FOLDER}}": "wiki/projects",
    "{{PEOPLE_FOLDER}}":   "wiki/entities",
    "{{TASKS_FOLDER}}":    "wiki/tasks",
    "{{DAILY_FOLDER}}":    "wiki/daily",
}

STYLES = ("obsidian", "wiki")

# Obsidian-style preset folder -> its path in the wiki layout, following the
# rows of references/folder-map.md (boards/ and templates/ come from the wiki
# tree in references/vault-schema.md). A preset folder with no entry has no home
# in the wiki layout - Goals/, Mentions/, Health/ and the other topic folders
# appear only in the Obsidian-style tree, and no command files notes into them -
# so a wiki-style vault does not create it, or the seed notes that live in it.
WIKI_PATHS = {
    "Daily": "wiki/daily",
    "Dev Logs": "wiki/logs",
    "Tasks": "wiki/tasks",
    "Projects": "wiki/projects",
    "People": "wiki/entities",
    "Ideas": "wiki/concepts",
    "Knowledge": "wiki/concepts",
    "Synthesis": "wiki/concepts",
    "Reviews": "wiki/reviews",
    "Meetings": "wiki/meetings",
    "Decisions": "wiki/decisions",
    "Boards": "boards",
    "Templates": "templates",
    "_trash": "_trash",
}

WIKI_DESCRIPTIONS = {
    "wiki/daily": "One note per day. Named `YYYY-MM-DD.md`",
    "wiki/logs": "Dev and work session logs - dated, project-tagged",
    "wiki/tasks": "Standalone task notes (linked from boards)",
    "wiki/projects": "Active and archived projects",
    "wiki/entities": "People, companies and tools - one note per entity",
    "wiki/concepts": "Ideas, concepts, frameworks and synthesis",
    "wiki/reviews": "Weekly and monthly reviews",
    "wiki/meetings": "Meeting notes - one per meeting",
    "wiki/decisions": "Decision records (ADRs)",
    "boards": "Kanban boards",
    "templates": "Note templates",
}


def resolve_folder(name: str, style: str = "obsidian") -> str | None:
    """Where a preset folder lives in the given layout, or None when the wiki
    layout has no home for it. Obsidian style is the preset's own name."""
    if style == "obsidian":
        return name
    return WIKI_PATHS.get(name)


def resolve_folders(folders: list[str], style: str = "obsidian") -> list[str]:
    """A preset's folder list in the given layout: order kept, folders with no
    home dropped, duplicates collapsed (Ideas and Knowledge are both wiki/concepts)."""
    out: list[str] = []
    for f in folders:
        path = resolve_folder(f, style)
        if path is not None and path not in out:
            out.append(path)
    return out


def _dataview_sources(text: str, style: str) -> str:
    """Point every `FROM "<Folder>"` query at that folder's path in the layout."""
    if style == "obsidian":
        return text
    return re.sub(
        r'FROM "([^"]+)"',
        lambda m: f'FROM "{resolve_folder(m.group(1), style) or m.group(1)}"',
        text,
    )


def _writer(vault: Path, style: str):
    """write() for a template or seed note addressed by its Obsidian-style path
    ("Templates/Task.md", "Goals/2026 Goals.md"). The top folder is resolved for
    the layout; a note whose folder has no home in it is skipped."""
    def put(rel: str, content: str) -> None:
        top, _, rest = rel.partition("/")
        base = resolve_folder(top, style)
        if base is None:
            return
        write(vault / base / rest, _dataview_sources(content, style))
    return put


# ── Preset definitions ────────────────────────────────────────────────────────
# Each preset declares its folder list, kanban boards, _CLAUDE.md folder map,
# Home dashboard body, and optional extra seed files.

class Board(NamedTuple):
    """A kanban board definition.

    Was a bare (name, columns) tuple. Three call sites read it positionally as
    b[0] and a fourth destructured it, so reordering or extending the tuple
    would break the three silently, with no type error to catch it.
    """
    name: str
    columns: list[str]


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
        "boards": [Board("OKRs", ["🎯 OKRs", "📅 Quarterly", "📋 Weekly", "✅ Done"])],
        "kanban_columns": ["🎯 OKRs", "📅 Quarterly", "📋 Weekly", "✅ Done"],
    },
    "builder": {
        "purpose": "Projects, dev logs, architecture, debugging",
        "folders": [
            "Daily", "Projects", "People", "Dev Logs", "Architecture", "Debugging",
            "Boards", "Knowledge", "Tasks", "Ideas",
            "Templates", "_trash",
        ],
        "boards": [Board("Engineering", ["📥 Backlog", "🏃 Sprint", "🔨 In Progress", "✅ Done"])],
        "kanban_columns": ["📥 Backlog", "🏃 Sprint", "🔨 In Progress", "✅ Done"],
    },
    "creator": {
        "purpose": "Content calendar, ideas pipeline, audience, publishing",
        "folders": [
            "Daily", "People", "Content/LinkedIn", "Content/X", "Content/Blog",
            "Ideas", "Audience", "Publishing",
            "Boards", "Templates", "_trash",
        ],
        "boards": [Board("Pipeline", ["💡 Ideas", "✏️ Drafts", "📅 Scheduled", "✅ Published"])],
        "kanban_columns": ["💡 Ideas", "✏️ Drafts", "📅 Scheduled", "✅ Published"],
    },
    "researcher": {
        "purpose": "Sources, literature, hypotheses, methodology, synthesis",
        "folders": [
            "Daily", "Sources", "Literature", "Hypotheses", "Methodology",
            "Synthesis", "Reading Queue", "Projects", "People",
            "Boards", "Templates", "_trash",
        ],
        "boards": [Board("Research", ["📚 Reading", "🔬 Processing", "🧬 Synthesized", "✅ Done"])],
        "kanban_columns": ["📚 Reading", "🔬 Processing", "🧬 Synthesized", "✅ Done"],
    },
}


FORCE = False  # set by --force; write() never clobbers user files without it


def write(path: Path, content: str, force: bool | None = None):
    """Create a file, refusing to overwrite existing content unless forced.

    Bootstrap must be safe to run on a non-empty vault: silently replacing a
    hand-made Home.md or _CLAUDE.md is data loss, not setup (stress-test fix
    23/24 - the audit verified the loss).

    `force` defaults to the module-level FORCE that main() sets from --force.
    Passing it explicitly is what makes this function testable in-process: every
    write in this file funnels through here, and reading a global meant the only
    way to exercise both branches was a fresh subprocess per scenario, which is
    why test_front_door and test_showroom shell out. Existing call sites are
    unchanged.
    """
    force = FORCE if force is None else force
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        print(f"  = kept existing {path} (re-run with --force to overwrite)")
        return
    path.write_text(content.strip() + "\n", encoding="utf-8")
    print(f"  ✓ {path}")


def write_bases(vault: Path, style: str = "obsidian", preset_folders: list[str] | None = None) -> None:
    """Create Bases/ with premade .base files stamped for the vault style.

    Skips any base whose target folder is absent from the preset and never
    overwrites an existing file - safe to call on re-runs.
    """
    folder_map = WIKI_FOLDERS if style == "wiki" else OBSIDIAN_FOLDERS
    bases_dir = vault / "Bases"
    bases_dir.mkdir(exist_ok=True)

    for template_name, (output_name, placeholder) in BASE_TEMPLATES.items():
        target = bases_dir / output_name
        if target.exists():
            continue

        folder = folder_map[placeholder]
        if preset_folders is not None and not any(
            f == folder or f.startswith(folder + "/") for f in preset_folders
        ):
            continue

        template_path = TEMPLATE_DIR / template_name
        if not template_path.exists():
            print(f"  ⚠️  template not found: {template_path}")
            continue

        content = template_path.read_text(encoding="utf-8")
        target.write_text(content.replace(placeholder, folder), encoding="utf-8")
        print(f"  ✓ {target}")


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
        if f in WIKI_DESCRIPTIONS:
            rows.append(f"| `{f}/` | {WIKI_DESCRIPTIONS[f]} |")
            continue
        # Use top-level segment for description lookup
        key = f.split("/")[0]
        if key == "Content":
            sub = f.split("/", 1)[1] if "/" in f else ""
            desc = f"Content drafts for {sub}" if sub else "Content calendar and post drafts"
        elif key == "Finances":
            sub = f.split("/", 1)[1] if "/" in f else ""
            desc = f"Finance notes ({sub})" if sub else "Finance notes"
        elif key == "Side Biz":
            sub = f.split("/", 1)[1] if "/" in f else ""
            desc = f"Side business ({sub})" if sub else "Side business"
        else:
            desc = descriptions.get(key, "-")
        rows.append(f"| `{f}/` | {desc} |")
    return "\n".join(rows)


def claude_md_personal(name: str, preset_key: str, preset: dict, jobs: list, vault_path: Path,
                       folders: list | None = None, style: str = "obsidian") -> str:
    primary_job = jobs[0] if jobs else "Work"
    boards, people = resolve_folder("Boards", style), resolve_folder("People", style)
    tasks, dev_logs = resolve_folder("Tasks", style), resolve_folder("Dev Logs", style)
    # Mentions/ and Finances/ have no home in the wiki layout, so a wiki-style
    # manual must not route anything to them.
    topic_folders = style == "obsidian"
    # The map is the agent's ground truth for what is where, so build it from the
    # folders bootstrap actually creates (which may extend the preset, e.g. the
    # Side Biz tree) - and list no file it does not write: the default preset
    # used to add a `Jobs/<job>.md` row per job while creating no such file, so
    # every fresh vault's map opened with a phantom note.
    folder_table = folder_map_table(folders if folders is not None else preset["folders"])
    if preset_key == "default":
        key_files = (
            "- **Dashboard:** `Home.md`\n"
            f"- **Work Board:** `{boards}/{primary_job}.md`\n"
            f"- **Personal Board:** `{boards}/Personal.md`"
            + ("\n- **Mentions Log:** `Mentions/Mentions Log.md`" if topic_folders else "")
        )
    else:
        board_lines = [f"- **{b.name} Board:** `{boards}/{b.name}.md`" for b in preset["boards"]]
        key_files = "- **Dashboard:** `Home.md`\n" + "\n".join(board_lines)
    mentions_rule = "- Mentions/recognition → Mentions Log + person's note + daily note\n" if topic_folders else ""
    finances_rule = "- Anything in Finances/ with personal financial data\n" if topic_folders else ""
    mentions_row = "\n| Mention/recognition | Mentions Log + person's note + daily note |" if topic_folders else ""

    return f"""# Claude Operating Manual - {name}'s Vault

> Read this file before doing anything in this vault.
> This is the single source of truth for how Claude operates here.

---

## Vault Identity

- **Owner:** {name}
- **Preset:** {preset_key}
- **Mode:** personal
- **Vault style:** {style}
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
- New people mentioned → {people}/ (create stub if needed)
- Tasks assigned or committed to → kanban board + {tasks}/ note
- Dev work done → {dev_logs}/ + project note + daily note
{mentions_rule}- Completed tasks → move on kanban to ✅ Done

Claude should **ask before saving**:
{finances_rule}- Anything involving deleting or archiving an existing note

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
| Dev session | {dev_logs}/ + project note + daily note |
| Person interaction | Daily note + their {people}/ note |
| Decision made | Project note (Key Decisions) + daily note |{mentions_row}

---

*Generated by obsidian-second-brain bootstrap script (preset: {preset_key}).*
*Regenerate: "Claude, update my _CLAUDE.md"*
"""


def claude_md_assistant(operator: str, subject: str, preset_key: str, preset: dict, vault_path: Path,
                        folders: list | None = None, style: str = "obsidian") -> str:
    # Same rule as claude_md_personal: the map documents the folders bootstrap
    # actually creates, not just the preset's base list.
    folder_table = folder_map_table(folders if folders is not None else preset["folders"])
    boards = resolve_folder("Boards", style)
    board_lines = [f"- **{b.name} Board:** `{boards}/{b.name}.md`" for b in preset["boards"]]
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
- **Vault style:** {style}
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


def render_home(name: str, preset_key: str, preset: dict, jobs: list, mode: str, subject: str = "",
                style: str = "obsidian") -> str:
    title = f"{name}'s Life OS" if (preset_key == "default" and mode == "personal") else (
        f"{subject}'s Vault" if mode == "assistant" else f"{name}'s {preset_key.title()} Vault"
    )
    daily = resolve_folder("Daily", style)

    if style == "wiki":
        # The default preset's navigation table links Goals/, Finances/, Health/
        # and Mentions/ seed notes that a wiki-style vault does not create, so
        # every wiki-style Home links only its boards and the folders it has.
        board_names = (jobs + ["Personal"]) if preset_key == "default" else [b.name for b in preset["boards"]]
        board_links = " · ".join(f"[[boards/{n}\\|📋 {n}]]" for n in board_names)
        folder_links = " · ".join(f"[[{p}/\\|📁 {p.split('/')[-1].title()}]]"
                                  for p in resolve_folders(preset["folders"], style)
                                  if p not in ("boards", "templates", "_trash"))
        nav = f"{board_links}\n\n{folder_links}"
    elif preset_key == "default":
        primary_job = jobs[0] if jobs else "Work"
        nav = (
            "| Work | Life | System |\n"
            "|------|------|--------|\n"
            f"| [[Boards/{primary_job}\\|📋 Work Board]] | [[Goals/{YEAR} Goals\\|🎯 Goals]] | [[Templates/\\|📝 Templates]] |\n"
            "| [[Boards/Personal\\|📋 Personal]] | [[Finances/Income Streams\\|💵 Income]] | [[Mentions/Mentions Log\\|💬 Mentions]] |\n"
            "| [[Projects/\\|🔨 Projects]] | [[Health/Health Dashboard\\|🏋️ Health]] | [[People/\\|👥 People]] |\n"
            "| [[Content/Content Calendar\\|📅 Content]] | [[Ideas/\\|💡 Ideas]] | [[Reviews/\\|📆 Reviews]] |"
        )
    else:
        board_links = " · ".join(f"[[Boards/{b.name}\\|📋 {b.name}]]" for b in preset["boards"])
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
""".replace('FROM "Daily"', f'FROM "{daily}"')

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


def write_core_templates(vault: Path, style: str = "obsidian"):
    """Templates shared by all presets."""
    put = _writer(vault, style)
    put("Templates/Daily Note.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: daily
tags:
  - daily
ai-first: true
mood:
energy:
---

# <% tp.date.now("YYYY-MM-DD") %> - <% tp.date.now("dddd") %>

## For future agent

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

    put("Templates/Project.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: project
tags:
  - project
ai-first: true
status: active
job:
---

# <% tp.file.title %>

## For future agent

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

    put("Templates/Person.md", """---
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

## For future agent

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

    put("Templates/Task.md", """---
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

## For future agent

Task note. Captures requirements, implementation notes, and what was delivered. Pull this when reconstructing why a piece of work was done or what was actually shipped vs requested.

## Requirements
<% tp.file.cursor() %>

## Implementation Notes


## Delivered

## Related
""")

    put("Templates/Dev Log.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: devlog
tags:
  - devlog
ai-first: true
project:
job:
---

# Dev Log - <% tp.date.now("YYYY-MM-DD") %>

## For future agent

Engineering log for this date. Captures what was worked on, problems solved, decisions made, and next steps. Pull this when reconstructing the chain of technical decisions on a project.

## What I Worked On
<% tp.file.cursor() %>

## Problems Solved


## Decisions Made


## Next Steps
- [ ]
""")


def write_preset_extras(vault: Path, preset_key: str, style: str = "obsidian"):
    """Preset-specific templates and seed files. In a wiki-style vault the seed
    notes that live in topic folders (Goals/, Mentions/, Finances/, Health/,
    Content/, Reading Queue/) are skipped with their folders; templates are not."""
    put = _writer(vault, style)
    if preset_key == "default":
        put("Templates/Goal.md", f"""---
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

## For future agent

Goal note. Captures why this goal matters, success criteria, milestones, and progress. Pull this when assessing whether work being proposed actually moves toward a stated goal.

## Why This Matters
<% tp.file.cursor() %>

## Success Criteria


## Milestones
- [ ]

## Progress Log
""")

        put("Templates/Mention.md", """---
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

## For future agent

Mention note. Captures a moment when someone recognized work publicly (Slack, email, meeting, LinkedIn). Pull these to surface social proof, track recurring advocates, or reconstruct who said what about a project.

## What Was Said
<% tp.file.cursor() %>

## Context


## My Takeaway
""")

        put(f"Goals/{YEAR} Goals.md", f"""---
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

        put("Mentions/Mentions Log.md", f"""---
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

        # Home.md's nav links this note - a fresh vault must not ship a
        # dangling wikilink (stress-test fix 9/24: the showroom rule).
        put("Finances/Income Streams.md", f"""---
date: {TODAY}
tags:
  - finance
---

# Income Streams

Track every income source here - salary, side business, one-off invoices.

| Stream | Type | Status |
|--------|------|--------|
| Salary | monthly | active |
""")

        put("Health/Health Dashboard.md", f"""---
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

        put("Content/Content Calendar.md", f"""---
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
        put("Templates/Meeting.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: meeting
tags:
  - meeting
ai-first: true
attendees:
duration:
---

# <% tp.file.title %>

## For future agent

Meeting note. Captures attendees, agenda, decisions, action items, and free-form notes. Pull this when reconstructing what was decided in a meeting or what commitments were made.

## Agenda
<% tp.file.cursor() %>

## Decisions

## Action Items
- [ ]

## Notes
""")
        put("Templates/Decision.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: decision
tags:
  - decision
ai-first: true
status: decided
context:
---

# ADR - <% tp.file.title %>

## For future agent

Decision record (ADR). Captures the context, options considered, the decision, and its consequences. Pull this when a similar decision comes up again, or when reconstructing why the system is shaped the way it is.

## Context

## Options Considered

## Decision

## Consequences
""")
        put("Templates/OKR.md", """---
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

## For future agent

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
        put("Templates/Architecture.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: architecture
tags:
  - architecture
ai-first: true
project:
---

# <% tp.file.title %>

## For future agent

Architecture note. Captures the problem, constraints, design, tradeoffs, and open questions. Pull this when extending a system, debating a refactor, or onboarding to a component.

## Problem

## Constraints

## Design

## Tradeoffs

## Open Questions
""")
        put("Templates/Debug.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: debug
tags:
  - debug
ai-first: true
project:
status: investigating
---

# Bug - <% tp.file.title %>

## For future agent

Bug investigation note. Captures the symptom, repro steps, investigation trail, root cause, and fix. Pull this when a similar symptom comes up again or when reasoning about why a fix was shaped a certain way.

## Symptom

## Repro

## Investigation

## Root Cause

## Fix
""")
        return

    if preset_key == "creator":
        put("Templates/Post.md", """---
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

## For future agent

Content post note. Captures the hook, body, CTA, and platform variants for a piece of public-facing content. Pull this to reconstruct what was published, where it went, and which hooks worked.

## Hook

## Body

## CTA

## Variants
""")
        put("Templates/Audience Note.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: audience
tags:
  - audience
ai-first: true
segment:
---

# <% tp.file.title %>

## For future agent

Audience segment note. Captures who they are, what they want, what they read, and the hooks that work for them. Pull this before drafting content aimed at this segment.

## Who They Are

## What They Want

## What They Read

## Hooks That Work
""")
        return

    if preset_key == "researcher":
        put("Templates/Source.md", """---
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

## For future agent

Source note (book, paper, podcast, video, article). Captures citation, abstract or summary, and raw notes. `source_kind` distinguishes the form (book/paper/podcast/etc.). Pull this when reasoning about what's been read on a topic.

## Citation

## Abstract / Summary

## Raw Notes
""")
        put("Templates/Literature Note.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: literature
tags:
  - literature
ai-first: true
source:
---

# <% tp.file.title %>

## For future agent

Literature note. Distillation of one source's key claims, methodology, critique, and connections to other ideas. Pull this when reasoning about what one specific source argues, separate from the broader landscape.

## Source
[[<% tp.file.title %>]]

## Key Claims

## Methodology

## Critique

## Connections
""")
        put("Templates/Hypothesis.md", """---
date: <% tp.date.now("YYYY-MM-DD") %>
type: hypothesis
tags:
  - hypothesis
ai-first: true
status: open
confidence: medium
---

# <% tp.file.title %>

## For future agent

Hypothesis note. Captures a testable statement, predictions, evidence for and against, and a verdict. Pull this when reasoning about open questions or when new evidence arrives that could update an open hypothesis.

## Statement

## Predictions

## Evidence For

## Evidence Against

## Verdict
""")
        put("Reading Queue/_Queue.md", f"""---
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
              jobs: list, include_sidebiz: bool, style: str = "obsidian"):
    preset = PRESETS[preset_key]

    print(f"\n🧠 Bootstrapping vault: {vault}")
    print(f"   Owner: {name}")
    print(f"   Preset: {preset_key}")
    print(f"   Mode: {mode}{' (subject: ' + subject + ')' if mode == 'assistant' else ''}")
    print(f"   Style: {style}")
    if preset_key == "default":
        print(f"   Jobs: {', '.join(jobs)}")
    print()

    # ── Folders ──────────────────────────────────────────────────────────────
    folders = list(preset["folders"])
    if preset_key == "default" and include_sidebiz:
        folders += ["Side Biz/Deals/Location1", "Side Biz/Deals/Location2"]
    folders = resolve_folders(folders, style)

    for f in folders:
        (vault / f).mkdir(parents=True, exist_ok=True)
    print("📁 Folders created")

    # ── _CLAUDE.md ────────────────────────────────────────────────────────────
    if mode == "assistant":
        write(vault / "_CLAUDE.md",
              claude_md_assistant(name, subject, preset_key, preset, vault, folders=folders, style=style))
    else:
        write(vault / "_CLAUDE.md",
              claude_md_personal(name, preset_key, preset, jobs, vault, folders=folders, style=style))

    # ── .claude/CLAUDE.md: native import of the manual ─────────────────────────
    # Claude Code loads a CLAUDE.md found from the working directory and follows
    # its @imports, with a 4 MiB limit and no interpreter involved. That makes it
    # the reliable way to put _CLAUDE.md in front of a session: the SessionStart
    # hook is capped at 10,000 characters of context, and a real manual outgrows
    # that (#270). The hook still runs - it publishes the skill root, which no
    # import can - and skips the manual when this file has already loaded it.
    (vault / ".claude").mkdir(exist_ok=True)
    write(vault / ".claude" / "CLAUDE.md",
          "# Vault operating manual\n\n"
          "The manual lives at the vault root so every agent surface can find it.\n"
          "This import loads it in full for Claude Code sessions started here.\n\n"
          "@../_CLAUDE.md\n")

    # ── Home ──────────────────────────────────────────────────────────────────
    write(vault / "Home.md", render_home(name, preset_key, preset, jobs, mode, subject, style=style))

    # ── Kanban Boards ─────────────────────────────────────────────────────────
    boards = vault / resolve_folder("Boards", style)
    if preset_key == "default":
        for job in jobs:
            write(boards / f"{job}.md", render_kanban(preset["kanban_columns"]))
        write(boards / "Personal.md", render_kanban(["📥 Backlog", "📋 This Week", "✅ Done"]))
    else:
        for board_name, columns in preset["boards"]:
            write(boards / f"{board_name}.md", render_kanban(columns))

    # ── Templates ─────────────────────────────────────────────────────────────
    write_core_templates(vault, style)
    write_preset_extras(vault, preset_key, style)

    # ── Bases ─────────────────────────────────────────────────────────────────
    write_bases(vault, style=style, preset_folders=folders)
    print("📊 Bases created")

    # ── .obsidian stub ────────────────────────────────────────────────────────
    (vault / ".obsidian").mkdir(exist_ok=True)
    if not (vault / ".obsidian/app.json").exists():
        write(vault / ".obsidian/app.json", "{}")

    # ── Showroom rule ─────────────────────────────────────────────────────────
    # A fresh vault must pass its own health check with zero findings. Scaffold
    # folders that end up empty get an invisible .gitkeep so vault_health's
    # empty-folder alarm stays honest for folders that BECOME empty later
    # (stress-test fix 9/24).
    for f in folders:
        d = vault / f
        if d.is_dir() and not any(d.iterdir()):
            (d / ".gitkeep").write_text("", encoding="utf-8")

    print(f"\n✅ Vault bootstrapped at: {vault}")
    print("\n📋 Recommended Obsidian plugins:")
    print("   • Bases     - powers the Bases/ live views (core plugin, enable in Settings)")
    print("   • Dataview  - powers the Home.md / Health Dashboard queries")
    print("   • Templater - powers the Templates/ folder")
    print("   • Kanban    - powers the Boards/ folder")
    print("   • Calendar  - daily note navigation")
    print("\n🤖 Claude MCP config:")
    print(f'   "obsidian-vault": {{"command": "npx", "args": ["-y", "mcp-obsidian", "{vault}"]}}')
    # Auto-read is wiring, not a property of the file: it happens only when
    # the load_vault_context SessionStart hook is registered (install.sh / the
    # Claude Code plugin) AND OBSIDIAN_VAULT_PATH is set (scripts/setup.sh)
    # AND the session starts inside the vault. Promising it unconditionally
    # strands bare-clone users in sessions that never load the manual, with
    # nothing telling them why.
    print("\n🧠 _CLAUDE.md is ready. Make sure your agent reads it before working in")
    print("   this vault - a configured integration may do that automatically (the")
    print("   SessionStart hook from install.sh or the Claude Code plugin, plus")
    print("   OBSIDIAN_VAULT_PATH from scripts/setup.sh, for sessions started")
    print("   inside the vault).")
    # The one moment the reader has definitely just got value: their vault
    # exists and they can see what was created. Once per machine, never in CI.
    try:
        from star_prompt import maybe_ask
        maybe_ask(f"Your vault is set up at {vault}.")
    except Exception:
        pass  # never let this break a bootstrap that otherwise succeeded


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
    parser.add_argument("--style", default="obsidian", choices=list(STYLES),
                        help="Folder layout: obsidian (Daily/, People/, ...) or wiki "
                             "(wiki/daily/, wiki/entities/, ...) (default: obsidian)")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing files (default: keep anything already in the vault)")
    args = parser.parse_args()
    global FORCE
    FORCE = args.force

    if args.mode == "assistant" and not args.subject:
        parser.error("--subject is required when --mode=assistant")

    vault = Path(args.path).expanduser().resolve()
    if vault.exists() and any(vault.iterdir()):
        if FORCE:
            print(f"⚠️  {vault} is not empty and --force is set: existing files WILL be overwritten.")
        else:
            print(f"ℹ️  {vault} is not empty: existing files will be KEPT (re-run with --force to overwrite).")


    jobs = [j.strip() for j in args.jobs.split(",") if j.strip()]
    bootstrap(vault, args.name, args.preset, args.mode, args.subject,
              jobs, include_sidebiz=not args.no_sidebiz, style=args.style)


if __name__ == "__main__":
    main()

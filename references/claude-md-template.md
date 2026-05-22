# `_CLAUDE.md` Template

`_CLAUDE.md` is a file that lives at the root of your vault.
It is the first thing Claude reads when working in your vault.
It gives every Claude surface (Desktop, Code, VS Code, terminal) the same operating context — no memory required.

---

## How to Generate It

When a user asks Claude to create their `_CLAUDE.md`, Claude should:
1. Call `list_files_in_vault()` to map the vault structure
2. Call `get_file_contents("Home.md")` (or equivalent dashboard) if it exists
3. Call `get_file_contents(path)` on 2–3 templates from the `Templates/` folder
4. Call `get_file_contents(path)` on the current kanban boards
5. Fill in the template below with discovered values
6. Call `append_content("_CLAUDE.md", content)` to write the file to the vault root

---

## The Template

Copy this, fill in the bracketed values, and save as `_CLAUDE.md` in the vault root.

```markdown
# Claude Operating Manual — [Your Name]'s Vault

> Read this file before doing anything in this vault.
> This is the single source of truth for how Claude operates here.

---

## Section 0 — AI-First Vault Rule (read first, applies to every note)

This vault is designed for **future-Claude** to read and reason over, not for human review. The owner rarely reads notes directly — they call Claude to retrieve, synthesize, and connect dots across years of accumulated knowledge.

**Every note Claude writes to this vault must follow these rules:**

1. **Self-contained context** — Each note must explain itself. Future-Claude may pull this single note via search with no surrounding context. Don't rely on backlinks alone for meaning.
2. **"For future Claude" preamble** — Every note begins with a 2-3 sentence summary in plain English so Claude can decide relevance in 10 seconds before parsing the structured data.
3. **Rich, consistent frontmatter** — Filterable metadata (`type`, `date`, `topic`, `tags`, `related-people`, `related-projects`, `sources`, `confidence`). Different note types may have different schemas, but every note has machine-readable frontmatter.
4. **Recency markers per claim** — When stating external facts, attach the date: "Mem0 raised $24M (as of 2026-04)" so future-Claude knows what to verify before trusting.
5. **Sources preserved verbatim** — Every external claim has its source URL inline so it can be re-verified or refreshed.
6. **Cross-links are mandatory** — Every person, project, idea, decision, or concept referenced uses `[[wikilinks]]` so the graph is traversable.
7. **Confidence levels** — Where applicable, mark claims as `stated | high | medium | speculation` so future-Claude knows what to trust vs verify.

This rule applies to all `/obsidian-*` and `/research*` commands, all scheduled agents, and any direct vault writes.

---

## Section 0.5 — Verify Live State Before Acting

Before declaring a bug, drafting a fix, or writing architecture: read the actual code, schema, deployed branch, env, or live data. Speculation from stale context burns hours and produces drafts that contradict reality.

Specific cues:
- Read the schema or types before declaring a bug (real field names live in the code, not in memory)
- `git fetch origin` and read the deployed branch, not local `main`
- Grep the live file before any anchor-based patch
- Fetch live time, dates, and rates (never infer from training data)
- Verify env vars in the running process before blaming code
- Mock tests miss schema drift: read one real payload before declaring "done"

This is a general operating principle, not vault-specific. Keep it in `_CLAUDE.md` so every Claude session in this vault inherits it.

---

## Vault Identity

- **Owner:** [Full Name]
- **Primary purpose:** [e.g. "Life OS — work, personal, side business, finances"]
- **Last updated:** [YYYY-MM-DD]

---

## Folder Map

| Folder | Purpose |
|---|---|
| `Daily/` | One note per day. Named `YYYY-MM-DD.md` |
| `Projects/` | Active and archived projects |
| `Tasks/` | Standalone task notes (linked from boards) |
| `Boards/` | Kanban boards: [list your board names] |
| `People/` | One note per person |
| `Dev Logs/` | Technical work logs — dated, project-tagged |
| `Side Biz/` | [Remove if not applicable] Deals, dashboard, tasks |
| `Side Biz/Deals/` | Deal notes — one per client opportunity |
| `Knowledge/` | Reference material and permanent notes |
| `Learning/` | Books, courses, content consumed |
| `Content/` | Content calendar and post drafts |
| `Finances/` | Monthly finance notes and subscriptions |
| `Goals/` | Annual and life goals |
| `Mentions/` | Times I've been recognized or mentioned |
| `Jobs/` | Employment and contract roles |
| `Businesses/` | Companies I own (founder stake) |
| `Templates/` | Note templates (Templater) |

---

## Key Files

- **Dashboard:** `[[Home]]` — main navigation and dataview queries
- **Work Board:** `[[Boards/[Work Board Name]]]`
- **Personal Board:** `[[Boards/Personal]]`
- **Mentions Log:** `[[Mentions/Mentions Log]]`
- **People Index:** `People/` folder

---

## Active Context

> Update this section at the start of each major project or focus period.

**Current top priority:** [Your current top priority here]
**Current job:** [Company] — [Your Role]
**Manager:** [Name]
**Key colleagues:** [Name (role), Name (role), ...]

---

## Auto-Save Rules

Claude should auto-save the following **without asking**:
- Decisions made in conversation → relevant project note + daily note
- New people mentioned → People/ (create stub if needed)
- Tasks assigned or committed to → kanban board + Tasks/ note
- Dev work done → Dev Logs/ + project note + daily note
- Mentions/recognition from colleagues → Mentions Log + person's note
- Completed tasks → move on kanban to ✅ Done

Claude should **ask before saving**:
- Anything touching Finances/ or personal financial data
- Faith/ or Partner/ (private notes)
- Anything that involves deleting or archiving an existing note

---

## Naming Conventions

- Daily notes: `YYYY-MM-DD.md`
- Dev logs: `YYYY-MM-DD — Description.md`
- Deals: `Client Name - Description Month Year.md`
- Tasks: Descriptive title, no date prefix
- People: Full name (e.g. `Jane Smith.md`, not `Jane.md`)
- Archive prefix: `_archived_`

---

## Frontmatter Requirements

Every note must have at minimum:
```yaml
---
date: YYYY-MM-DD
tags:
  - [note-type]
---
```

Note types: `daily` | `project` | `task` | `person` | `devlog` | `deal` | `goal` | `mention` | `content`

---

## Kanban Convention

Columns in boards: `📥 Backlog` · `📋 This Week` · `🔨 In Progress` · `⏳ Waiting On` · `✅ Done`

Priority: 🔴 critical · 🟡 important · 🟢 low

Item format:
```
- [ ] 🔴 **Title** · @{YYYY-MM-DD}
	Description. [[Related Project]] [[Person]]
```

Completed:
```
- [x] ~~🔴 **Title**~~ ✅ Date
```

---

## Propagation Rules

| Event | Also update |
|---|---|
| New project | Board (Backlog) + today's daily note |
| Task done | Board (Done, strikethrough) + project note + daily note |
| Dev session | Dev Logs/ + project note (Recent Activity) + daily note |
| Person interaction | Daily note + their People/ note |
| Decision made | Project note (Key Decisions) + daily note |
| Mention/recognition | Mentions Log + person's note + daily note |
| Deal update | Deal file + Side Biz board + daily note |

---

## People to Know

> Add the people most relevant to your work here so Claude doesn't have to discover them.

| Person | Role | Notes |
|---|---|---|
| [Name] | [Role] | [One-line context] |
| [Name] | [Role] | [One-line context] |

---

## Projects Currently Active

> Keep this list current. Claude uses it to route context correctly.

- `[[Projects/Project Name]]` — [one-line status]
- `[[Projects/Project Name]]` — [one-line status]

---

## Do Not Touch

- `Templates/` — Never modify templates during normal vault operations
- `Faith/` — Private. Read only if directly asked.
- `[Other private folders]` — [Reason]

---

*This file was generated by the obsidian-second-brain skill.*
*Regenerate with: "Claude, update my _CLAUDE.md"*
```

---

## Keeping `_CLAUDE.md` Fresh

`_CLAUDE.md` should be regenerated or updated when:
- A new major project starts
- A team change happens (new manager, new colleagues)
- A folder is restructured
- Active priorities shift significantly

The user can trigger this with: *"Update my `_CLAUDE.md`"* or *"Regenerate my vault manifest."*

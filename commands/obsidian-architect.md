---
description: Scan a codebase and write a maintained set of architecture notes into the vault - overview, per-module notes, key decisions. Re-run to refresh without clobbering your edits
category: meta
triggers_en: ["document this codebase", "architect this project", "map this code into my vault", "generate architecture notes", "refresh architecture docs"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-architect [path-to-codebase]`:

Turns a software project into a maintained set of architecture notes in the vault, so future-you (and future-Claude) can answer "how does this project work and why" without re-reading the code. Re-running refreshes the notes in place.

This is a hybrid command: a deterministic Python scan produces the facts, then YOU synthesize the prose, rationale, and diagram. Never invent structure the scan did not find (see the anti-fabrication rule).

1. **Resolve the codebase path.** Use the argument if given. Otherwise infer from the active project note's `local-path`, or ask. Confirm it is a directory.

2. **Run the scan** from the skill repo root:
   ```bash
   python scripts/architect_scan.py --path <codebase>
   ```
   It returns JSON: `name`, `kind`, `languages` (with file counts), `modules` (proposed top-level parts with a `core`/`support` hint), `dependencies`, `entry_points`, `signals` (dockerfile/makefile/ci), and `git` (commit). It writes nothing and calls no LLM - the synthesis is yours.

3. **Optionally pull decision history** for the "Key decisions" note:
   ```bash
   python scripts/mine_commit_decisions.py --repo <codebase> --json
   ```

4. **Pick the destination.** Write under the project's hub: `wiki/projects/<name>/Architecture/` (create it if missing). If the vault has no project note for this codebase yet, offer to create one via `/obsidian-project` first so the architecture links into it.

5. **Synthesize and write these notes**, each AI-first compliant:
   - **`Architecture - Overview.md`** (`type: architecture-overview`): what the project is, its stack (from `languages`/`kind`/`dependencies`), how the parts fit together, and ONE Mermaid diagram of the modules and their main flow. Include a short **Personas** section (2-4 likely user types, marked `confidence: speculation` unless a README states them). Link to each module note.
   - **One note per `core` module** (`type: architecture-module`): `Architecture - <Module>.md` - what it does, what it depends on, and its role in the whole. Keep `support` modules to a single line in the overview unless they are substantial.
   - **`Architecture - Key decisions.md`** (`type: adr` entries or a decisions list): write up the candidates from the commit-decisions miner, each as a real decision with context. Mark anything inferred as `confidence: speculation`.

6. **Sentinel-safe writing (so refresh never destroys your edits).** Wrap every machine-generated section between markers:
   ```
   <!-- @generated:start -->
   ...synthesized content...
   <!-- @generated:end -->
   ```
   Anything a human adds should go in a `<!-- @user:start -->` ... `<!-- @user:end -->` block, or simply outside the generated markers. **On a re-run, replace ONLY the content inside `@generated` blocks; never touch `@user` blocks or anything outside the markers.** If a note has no markers yet (first run), add them around what you generate.

7. **Refresh behavior.** If the architecture notes already exist, this is a refresh: re-scan, then update only the generated blocks whose underlying facts changed (new module, dropped dependency, etc.). Note in the overview's frontmatter the `scanned-commit` so a reader knows how current the docs are. Report what changed.

8. Link the overview from the project note and from today's daily note. Append a one-line entry to the operation log.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Describe only what the scan and the code actually show - never invent a module, a dependency, a data flow, or a decision that is not grounded in the manifest or the source. If the scan is thin (small project, no manifest), say so and keep the notes short rather than padding. Mark inferred rationale and personas as `confidence: speculation`. See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.

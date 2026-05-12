---
description: Generate a decision record when the vault structure changes — the vault knows why it knows what it does
category: thinking
---

Use the obsidian-second-brain skill. Execute `/obsidian-adr $ARGUMENTS`:

The optional argument is the decision topic. If not provided, infer from recent conversation context.

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Identify the structural decision:
   - From the argument, or from recent conversation (e.g., a project was graduated, a folder was reorganized, a new convention was adopted, a concept was promoted to hub status)
3. Create a decision record at `Knowledge/ADR-YYYY-MM-DD — Title.md`:

   ```yaml
   ---
   date: YYYY-MM-DD
   tags:
     - decision-record
   status: accepted
   ---
   ```

   Structure:
   - **Decision**: one-line summary of what was decided
   - **Context**: what prompted this decision — the problem or trigger
   - **Options Considered**: 2-3 alternatives that were evaluated
   - **Rationale**: why this option was chosen over the others
   - **Consequences**: what changes as a result — what notes were created, moved, or restructured
   - **Related**: links to affected project notes, people, or ideas

4. Update the relevant project note's Key Decisions section with a link to the ADR
5. Update `index.md` with the new ADR
6. Append to `log.md`: `## [YYYY-MM-DD] adr | Title — decision recorded`
7. Link from today's daily note

Decision records prevent the vault from becoming a black box. When the user (or a future Claude session) asks "why is the vault structured this way?" — the ADR has the answer.

This command can also be triggered automatically by other commands: when `/obsidian-graduate` promotes an idea, when `/obsidian-health` recommends a structural fix, or when the user reorganizes folders. In those cases, offer to create an ADR — don't force it.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.

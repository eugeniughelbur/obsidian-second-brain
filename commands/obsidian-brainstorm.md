---
description: Multi-turn Socratic brainstorm - one question per turn until the idea converges, then a design note with named alternatives and one recommendation
category: thinking
trigger-mode: explicit
triggers_en: ["brainstorm this", "brainstorm with me", "think this through with me", "help me design this", "interview me about this idea"]
triggers_es: ["haz una lluvia de ideas conmigo", "piensa esto conmigo", "ayúdame a diseñar esto", "entrevístame sobre esta idea"]
triggers_pt: ["faça um brainstorm comigo", "pense nisso comigo", "me ajude a desenhar isto", "me entreviste sobre esta ideia"]
---

Use the obsidian-second-brain skill. Execute `/obsidian-brainstorm $ARGUMENTS`:

The optional argument is the topic. If not provided, infer it from recent conversation, or ask "What are we brainstorming?"

Every other thinking tool in this skill is a single-shot analytical pass. This one is different: it is **stateful and multi-turn** - you interview the user one question at a time until the idea has actually converged, and only then write anything. Do not rush to the output. The interview IS the tool.

## Phase 1 - ground in the vault (silent, no LLM theatrics)

1. Read `_CLAUDE.md` first if it exists in the vault root
2. Search the vault for the topic: related project notes, past decisions (Key Decisions sections, ADRs), idea fragments, and open questions (`TBD`, `TODO`, open-question sections). This is context for your questions - do not dump it at the user
3. Note contradictions or prior failures the vault records about this topic; they become questions in Phase 2

## Phase 2 - the interview (one question per turn, hard rule)

Ask **exactly one question per turn**. Prefer multiple-choice (2-4 concrete options plus "other") over open questions - options force clarity. Draw each question from whichever of these six categories is least resolved:

1. **Problem framing** - what actually hurts today? Who feels it?
2. **Constraint surfacing** - time, money, skills, platform, non-negotiables
3. **Trade-off forcing** - "if you could only have one of X or Y, which?"
4. **Scope bounding** - what is explicitly OUT of the first version?
5. **Prior-decision linking** - "your vault records [[decision]] - does that still hold here?"
6. **Anti-goals** - what outcome would make this a failure even if it "works"?

Track convergence against this checklist (internally - do not show a scoreboard):

- [ ] problem stated in one sentence
- [ ] hard constraints known
- [ ] at least one trade-off explicitly decided
- [ ] first-version scope bounded
- [ ] linked to (or consciously departing from) prior vault decisions
- [ ] anti-goals named

Keep interviewing until at least 5 of 6 are checked. If the user says "just write it" earlier, comply - but mark the unchecked items as `open-questions` in the note instead of silently guessing.

## Phase 3 - converge and propose

1. Present 2-3 **named** approaches (give each a real name, not "Option A"), each with a one-line essence and a short trade-off table
2. Mark exactly one **(Recommended)** and say why in one sentence
3. Let the user pick or push back - this can loop once or twice; that is normal

## Phase 4 - write the brainstorm note

Save to the ideas/concepts folder (resolved per `references/folder-map.md`), named `YYYY-MM-DD - Brainstorm - <topic>.md`, `type: brainstorm`, thinking-tool schema in `references/ai-first-rules.md`. Structure:

- `## For future Claude` preamble: what was being designed, what got decided, what is still open
- `## Problem` - the one-sentence framing (verbatim from the interview)
- `## Constraints and anti-goals`
- `## Approaches considered` - the named alternatives with the trade-off table, the chosen one marked
- `## Decisions made` - each with its reasoning, `[[wikilinked]]` to related project/ADR notes
- `## Open questions` - anything unresolved, including checklist items skipped on user request

Then propagate: link the note from today's daily note, from the related project note (if one exists), and offer `/obsidian-graduate` if the brainstorm produced something project-shaped, or `/obsidian-decide` if a decision deserves an ADR.

Do not pad the note with the interview transcript - future-Claude needs the conclusions and the reasoning, not the dialogue.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval - not human reading.

**Anti-fabrication:** Search exhaustively before claiming any note, person, or file is absent - false absence is the most common failure mode - and never invent facts, entities, or dates (mark unknowns as `TBD`). See the anti-fabrication and search-completeness hard rules in `references/ai-first-rules.md`.

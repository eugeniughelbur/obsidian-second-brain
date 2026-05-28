---
description: Create a new obsidian-second-brain command via interview - zero markdown editing required
category: meta
triggers_en: ["create command", "new command", "add a command", "scaffold a command"]
---

Use the obsidian-second-brain skill. Execute `/create-command $ARGUMENTS`:

This command runs a short interview, then writes a new `commands/<name>.md` file that the build pipeline picks up automatically. The user never touches frontmatter, never edits a template, and never copies an existing command file.

**Hard rule:** You MUST use the AskUserQuestion tool for every question in this flow. ONE question per call. Wait for the answer before the next question. Do not batch.

The optional argument is a free-text seed describing what the command should do (e.g., `summarize my notion pages and save to vault`). If given, use it to pre-fill suggestions in the interview. If empty, the first question opens with "what problem do you want to solve?".

---

## Phase 1 - Intent

Ask ONE question via AskUserQuestion:

> "What problem do you want this new command to solve?" (free text)

Read the answer. Confirm understanding back in one sentence before proceeding.

---

## Phase 2 - Naming

From the intent, propose 3 candidate kebab-case names. Names should be lowercase, hyphenated, and start with `obsidian-` (vault-management commands) OR a topic prefix (research toolkit uses `research-*`, social uses `x-*`/`brand-*`) OR just a verb (`create-*`, `import-*`).

Use AskUserQuestion (single-select) with 3 options plus "Other" implicit:

> "Which name should I use?"
> - `<candidate-1>`
> - `<candidate-2>`
> - `<candidate-3>`

After the user picks, validate:
1. Check that `commands/<name>.md` does NOT already exist (use Read; if it succeeds, the name is taken - go back and re-ask)
2. Confirm the name passes the regex `^[a-z][a-z0-9-]*$`

---

## Phase 3 - Category

Ask via AskUserQuestion (single-select, 4 options):

> "Which category does this command belong to?"
> - `vault` - daily writing, capture, find (note creation, retrieval, kanban)
> - `thinking` - synthesis, decisions, learning, reviews
> - `research` - bring external sources into the vault
> - `meta` - vault setup, health, structure, tooling

---

## Phase 4 - Trigger phrases

Generate 3-5 natural-language trigger phrases the user might say to invoke this command (not slash-form). Examples from existing commands: `"save this"`, `"deep research"`, `"weekly review"`. Avoid duplicating triggers already used by other commands (read all `commands/*.md` frontmatter `triggers_en:` once and warn on collisions).

Ask via AskUserQuestion (free text, default to your suggested set):

> "Trigger phrases the user might say to fire this command, comma-separated:"
> Default: `<suggestion-1>, <suggestion-2>, <suggestion-3>`

---

## Phase 5 - Behavior outline

Ask via AskUserQuestion (free text):

> "Describe what the command does in 3-5 numbered steps. Plain English, no code."

Use the answer as the spine of the command body.

---

## Phase 6 - Vault writes? (AI-first compliance gate)

Ask via AskUserQuestion (single-select):

> "Does this command write notes to the user's Obsidian vault?"
> - `yes` - output must apply the AI-first rule (frontmatter, preamble, wikilinks)
> - `no` - read-only, informational, or external-write only

If `yes`: the generated command body MUST end with the AI-first rule footer (see Phase 8).

---

## Phase 7 - External APIs?

Ask via AskUserQuestion (multi-select):

> "Does this command call any external APIs?"
> - Perplexity Sonar (web research)
> - xAI Grok (X posts, Live Search)
> - YouTube Data API
> - Other (free text)
> - None - purely operates on the vault and conversation

If any are selected, the generated body should include a setup line referencing `~/.config/obsidian-second-brain/.env` and the relevant key (e.g., `PERPLEXITY_API_KEY`).

---

## Phase 8 - Generate the file

Build the new command file. The exact format MUST be:

```
---
description: <one-line, sentence-case, ends without period>
category: <vault | thinking | research | meta>
triggers_en: ["<trigger 1>", "<trigger 2>", "<trigger 3>"]
---

Use the obsidian-second-brain skill. Execute `/<name> $ARGUMENTS`:

<one-sentence framing tying the user's intent (Phase 1) to the action>

1. Read `_CLAUDE.md` first if it exists in the vault root
2. <step from Phase 5, step 1>
3. <step from Phase 5, step 2>
4. <step from Phase 5, step 3>
5. <step from Phase 5, step 4 if present>
6. <step from Phase 5, step 5 if present>

<closing one-liner explaining why this matters>

---

<AI-first footer ONLY if Phase 6 = yes>
**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` — `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. The vault is for future-Claude retrieval — not human reading.
```

Write the file to `commands/<name>.md` using the Write tool.

---

## Phase 9 - Confirm + next steps

Show the user the absolute path of the file you just wrote. Then surface the three follow-up actions:

1. **Build** - `bash scripts/build.sh` will recompile every platform (`dist/claude-code/commands/<name>.md`, plus the auto-generated routing tables and trigger reference in `AGENTS.md` / `GEMINI.md`)
2. **Install** - for Claude Code users who symlink, the new command appears automatically on next session. For other platforms, copy `dist/<platform>/` into the vault.
3. **Iterate** - open the file, refine steps, commit. Or rerun `/create-command` to add a sibling command.

If the new command writes to the vault and the user has the validate-ai-first hook installed, remind them that the validator will warn on missing preamble/frontmatter - that's expected; just follow the AI-first rule in the command's own logic.

---

**Why this matters:** Most "no-code" frameworks fail because they make the user fill out a form. This command treats the conversation itself as the form. Six questions, one file, zero markdown editing. Lowers the contribution bar so anyone can extend the skill - and every command added through this flow lands AI-first-compliant by construction.

---

**Note for future-Claude:** This is a command that creates commands. Do not run it recursively on itself. Do not rewrite this file when invoked - write a NEW `commands/<name>.md` based on the interview.

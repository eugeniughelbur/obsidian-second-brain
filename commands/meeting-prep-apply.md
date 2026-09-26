---
description: Compile a checked-off meeting-prep note into a talking-points-and-questions list
category: thinking
triggers_en: ["apply meeting prep", "compile my talking points", "give me my talking points", "meeting prep output"]
triggers_es: ["aplicar preparación de reunión", "compilar mis puntos de conversación"]
---

Use the obsidian-second-brain skill. Execute `/meeting-prep-apply $ARGUMENTS`:

The argument is a person's name, optionally followed by a date (e.g. `<Person> 2026-09-08`) - handle typos and partial matches, and treat a request naming the owner's own manager as a request for the owner's own upward-1:1 prep note (see step 1). This is the other half of the `meeting-prep-daily-trigger` scheduled task: that task writes a checklist note under a person's own `Meeting Prep/To Review/` subfolder with a single master "reviewed" checkbox plus itemized Follow-ups/Challenges/Growth/Achievements/Company related checkboxes; this command reads that note back, and if - and only if - the master checkbox is checked, compiles exactly the itemized boxes that are also checked into a **single flat bullet outline of talking points and questions** styled after the owner's own personal meeting-agenda doc convention (see step 6) - not grouped under the checklist's own category headings - presents that outline directly in chat (the actual deliverable - the owner needs this before walking into the meeting), moves the note to that same folder's `Done/`, and confirms via Slack + a desktop push notification.

**Checking the master box is the confirmation gate - do not ask for a separate approval before compiling.**

1. Read `_CLAUDE.md` first if it exists in the vault root.
2. Resolve the person:
   - If the argument names the owner's own manager (or clearly means the owner's own upward 1:1), the target folder is the owner's own folder, `Knowledge Base/People/<Owner's Own Folder>/` - this is the owner's upward-reporting meeting prep, not a direct report's.
   - Otherwise, resolve the name against `Knowledge Base/People/` the same way `/direct-report` does (fuzzy match across every team subfolder, confirm if ambiguous).
   Their `Meeting Prep/` subfolder sits alongside their facet files (`<Person> - Profile Card.md`, etc.) and, for direct reports, their `Transcripts/` subfolder.
3. Find the target note in that folder's `Meeting Prep/To Review/` ONLY (never `Meeting Prep/Done/`): if a date was given, use `<date> - <Person Full Name>.md` exactly (for the owner's-own-manager case, `<Person Full Name>` is the owner's own full name); otherwise take the most recent dated note still sitting in `To Review/`. If none exists there, say so and stop - don't fabricate one, and don't look in `Done/`.
4. Read the note in full. Check its `## Review status` section for the master checkbox:
   - If it is still `- [ ] I have reviewed this note and selected my talking points` (unchecked), **stop here and do nothing** - leave the file exactly as-is, tell the owner it hasn't been marked reviewed yet.
   - If it is checked (`- [x]`), continue to step 5.
5. Parse every checkbox line under the note's `## Follow-ups`, `## Challenges`, `## Growth`, `## Achievements`, and `## Company related` headings (the last is a newer bucket - not every note will have it; parse it when present). Only lines checked `- [x]` are in scope - leave every `- [ ]` line alone, and don't infer intent beyond what's literally checked. (It's valid for the master box to be checked while zero itemized boxes are checked - that just means "reviewed, nothing to raise this time.")
6. Compile the checked items into a **grouped, multi-level nested outline** styled after the owner's own personal meeting-agenda convention - his running per-person notes doc (a Google Doc titled something like "Notes - `<Person>` / `<Owner>` - Weekly"), which groups by theme (e.g. "Personal", "Project specific", "AI") as plain top-level bullets with nested sub-bullets underneath, 2-3 levels deep. Group the compiled output the same way, using the checklist's own review categories - **Follow-ups, Challenges, Growth, Achievements, Company related**, in that order - as the top-level theme bullets. Only include a category if at least one of its items was checked; drop categories with nothing checked entirely rather than leaving an empty header.
   - Each category is a plain top-level bullet (its bare name, e.g. "Follow-ups" - no bold, matching how the owner's own doc's theme bullets read as plain text).
   - Nest one bullet per checked item directly under its category, in priority order (highest first) carried over from the checklist, with the priority/recurrence tag itself dropped.
   - Phrase every item bullet as something the owner would actually say out loud - **a direct question addressed to the person ("you"), or a stated idea/suggestion** - never a meta-instruction describing the act of asking. Wrong: "Ask whether Nemo has confirmed the 80% -> 100% allocation timing yet." Right: "Has Nemo confirmed the 80% -> 100% allocation timing yet, and can we announce it to the team?" An idea reads the same way: not "Offer to help with X" but "I can help you with X once Y lands - let's find the time." Company related items are usually news to share rather than a question - phrase them as a stated update (e.g. "Heads up - Vaimo just signed Thule Group as a new account, kicking off with go-live targeted early 2027.").
   - Nest a further third-level sub-bullet under an item only where there's a genuine follow-on question or supporting reference (a link, a specific number, a "by when") - matching how the owner's own doc nests a clarifying sub-question under a topic (e.g. "Current satisfaction with your work (1 to 5)?" -> "Can you name a few?"). Don't force a third level onto an item that's already a single, self-contained ask. For Company related items specifically, always nest the item's own "[View in Slack](...)" link from the checklist as a third-level sub-bullet - it's a genuine supporting reference the owner may want to pull up live.
   - Don't just copy the checklist line verbatim - it was written as a scannable proposal with priority tags and recurrence counts, not as something to say out loud; strip that scaffolding out of the final phrasing.
   - After the last category group, always add two fixed, unnested closing bullets - "Anything from your side?" then "Q/A" - matching how the owner's own doc always ends every entry with a flat, ungrouped "Q/A" bullet outside any theme.
   - Never add a talking point that wasn't checked, and never invent detail beyond what the checked item and the note's own sourced material support.
7. Present the compiled outline directly in chat, in a fenced code block using plain `-` markdown bullets with 2-space indent per nesting level, so the owner can copy-paste it straight into his Google Doc under a new dated heading - this is the primary deliverable, needed before the meeting starts. Lead with a one-line header (outside the code block) naming who the meeting is with and when.
8. **Rewrite the note entirely** rather than appending to it - the checklist (priority tags, recurrence counts, checkboxes, the Review status section) was scratch scaffolding for the owner's selection step and is not wanted in the final result. The note that lands in `Done/` contains ONLY:
   - Minimal frontmatter (`type: meeting-prep`, `person`, `role`, `company`, `tags`, `date`, `ai-first: true` - drop `meetings-reviewed` and any other checklist-stage-only fields)
   - A 1-2 sentence `## For future Claude` preamble noting this matches the owner's personal agenda-doc convention and is distilled from a checklist that is not preserved
   - A `# <Person> - Talking Points - <date>` heading
   - A `## Notes` heading, then the grouped, multi-level nested bullet outline from step 6 (category groups in order, each with their nested items, ending with "Anything from your side?" / "Q/A")
   - A `## Action items` heading with a single empty placeholder bullet (`-`) for the owner to fill in during/after the meeting, matching how the owner's own doc always carries this section (usually empty beforehand, filled in afterward)
   No checkboxes anywhere, no priority/recurrence tags, no area headers, no "Compiled" bookkeeping section, none of the original checklist items that weren't selected.
9. Move the note from `<folder>/Meeting Prep/To Review/<filename>` to `<folder>/Meeting Prep/Done/<filename>` (same filename, just relocated) - write the rewritten content from step 8 to that Done/ path directly rather than moving the old file and editing it in place.
10. Notify the owner in two ways, in addition to the in-chat bullet list from step 7 (always send both, regardless of how this command was invoked):
    a. **Slack**, posted to the vault's configured direct-report/meeting-prep notification channel (the same channel `meeting-prep-daily-trigger` uses - a private channel with only the owner in it. Use that channel directly, do NOT search for or DM the owner's user profile). Keep this brief - the full list already went to chat:
       ```
       🗓️ Talking points compiled for <Person>'s <date> 1:1 and moved to Done - <N> item(s).
       ```
    b. **Desktop push notification** (the `PushNotification` tool, `status: "proactive"`) - one line, under 200 characters, e.g. "🗓️ Talking points ready for <Person> - N item(s)."

HARD RULES:
- Never touch any person's Profile Card, Skills Matrix, Performance Review, or AI Competency Framework file from this command - it only ever reads a `Meeting Prep/To Review/` note, writes the compiled list back into that same note, and moves it to `Meeting Prep/Done/`.
- Never compile an itemized box that isn't checked `- [x]`.
- Never fabricate a talking point beyond what a checked item and its sourced material actually support.

This closes the loop the scheduled task opens: `meeting-prep-daily-trigger` writes a prioritized checklist and a Slack ping every morning, the owner reviews at their own pace (including directly in Obsidian, since checkbox clicks there edit the underlying markdown in place), checks the boxes they actually want to raise plus the master "reviewed" box, and this command turns that into the actual talking-points-and-questions list they walk into the meeting with - no live back-and-forth required to re-litigate what was already decided by checking boxes. See `references/meeting-prep-daily-trigger.md` for the scheduled task's own setup and prompt.

---

**AI-first rule:** Every note created or updated by this command MUST follow `references/ai-first-rules.md` - `## For future Claude` preamble, rich frontmatter (`type`, `date`, `tags`, `ai-first: true`, plus type-specific fields), recency markers per external claim, mandatory `[[wikilinks]]` for every person/project/concept referenced, sources preserved verbatim with URLs inline, and confidence levels where applicable. If that path does not resolve from your working directory, search upward for it; if you still cannot read it, say so before writing rather than producing a note that silently skips the rule. The vault is for future-Claude retrieval - not human reading.

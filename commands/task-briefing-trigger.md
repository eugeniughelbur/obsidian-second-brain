---
description: Manually run the daily task briefing right now instead of waiting for the scheduled morning check
category: thinking
triggers_en: ["task briefing", "run task briefing now", "what's due today", "check my tasks now"]
triggers_es: ["informe de tareas", "revisar mis tareas ahora"]
---

Use the obsidian-second-brain skill. Execute `/task-briefing-trigger $ARGUMENTS`:

This command takes no argument - it reports on the owner's own task board, not on a specific person. It's the on-demand version of the `daily-task-briefing` scheduled task: instead of waiting for its own scheduled morning run, execute that task's exact logic right now.

**Single source of truth:** the scheduled task's own instructions live at `~/.claude/scheduled-tasks/daily-task-briefing/SKILL.md`. This command deliberately does NOT keep its own copy of those steps - an earlier copy drifted (it moved files into `Tasks/✅ Done/` without setting `status: done`, so `Bases/Tasks.base` showed them in the wrong column). Whatever that file says is what this command does.

1. Read `~/.claude/scheduled-tasks/daily-task-briefing/SKILL.md` in full (skip its YAML frontmatter).
2. Execute every step in it exactly as written, in order - including its board moves, file moves, `status`/`area` frontmatter repairs, Slack message, and desktop push notification. Its HARD RULES and IMPLEMENTATION NOTE apply unchanged.
3. Then, because this was invoked live rather than on a schedule, also report back briefly here in chat: the count per bucket (Today / This week / Overdue), any tasks swept into Done or moved into Today, any board repairs made or flagged, and confirmation that the Slack message and push notification were sent.

**Fallback - only if that file does not exist** (e.g. the scheduled task was never set up on this machine): do a read-only briefing instead. Read `Boards/Personal.md`, skip the Done and Recurring columns, bucket every card with a `due @{YYYY-MM-DD}` date into TODAY (due today), THIS WEEK (after today, on or before the coming Sunday) and OVERDUE (before today), sort each bucket by the card's own priority emoji (🔴, then 🟡, then 🟢, then unmarked), and report the three buckets in chat. In fallback mode, never modify `Boards/Personal.md` or any file under `Tasks/`, and say clearly that the scheduled task's instructions were not found.

---

This command does not create any vault note, so the usual AI-first write rule does not apply to its own output. Any vault edits it makes are the scheduled task's own mechanical board/file reconciliation, governed by that file's rules.

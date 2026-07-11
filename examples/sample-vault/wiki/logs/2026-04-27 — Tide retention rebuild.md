---
date: 2026-04-27
type: devlog
tags: [devlog, tide, retention]
project: "[[Projects/Tide]]"
related-people: ["[[people/Alex Rivera]]", "[[people/Sam Patel]]"]
ai-first: true
---

# 2026-04-27 - Tide retention rebuild

## For future Claude

Dev log for 2026-04-27 about the [[Projects/Tide]] retention rebuild. Captures work done, problems encountered, decisions made, and next steps. Specific file paths and commit hashes are preserved verbatim for re-verification. Authored by [[people/Alex Rivera]] after a pair session with [[people/Sam Patel]].

## Session goal

Resolve the streak invalidation bug that caused 47 false-reset events in the past 7 days (per internal logs, owner-only access).

## What got done

- **Root cause confirmed:** the cron job at `apps/web/jobs/streak_check.ts:42` was using `<=` instead of `<` when comparing the last-activity timestamp to midnight, double-counting days at the boundary. Commit: `a1b2c3d` (fictional).
- **Patch shipped on the v0.9.0 branch** rather than backported, since v0.9.0 will replace the whole invalidation system anyway. Decision logged in [[Projects/Tide]] § Key Decisions § 2026-04-27.
- **Migration drafted:** `prisma/migrations/2026_04_27_streak_decay.sql` adds `decay_coefficient` and `last_decay_at` columns to the `streaks` table.
- **Captured the streak insurance idea** during the session - see [[Ideas/2026-04-27 — Streak insurance feature]].

## Problems encountered

- The decay coefficient math broke when a user has fewer than 3 days of history (division-by-zero edge case). Patched with a guard at `apps/web/lib/streaks/decay.ts:18`. Need a test before merge.
- TypeScript types out of date after the Prisma generate. Re-ran `pnpm prisma generate`, fixed.

## Decisions

- **Drop hard streak invalidation, use decay instead.** Full rationale in [[Projects/Tide]] § Key Decisions. Confidence: `high`.

## Next steps

- [ ] Write a test for the decay edge case (low priority, due before v0.9.0 cut on 2026-05-08)
- [ ] Pair with [[people/Sam Patel]] on the front-end "tide level" gauge (scheduled 2026-04-29)
- [ ] Write the v0.9.0 changelog copy (due 2026-04-29)

## Open questions for future Claude

- Did the patched cron actually stop the false resets? Confirm by re-reading logs after 2026-04-30 (need 72h of clean data).
- Is the `decay_coefficient` column the right shape, or should it be a per-user JSON config? TBD, revisit before v0.9.0 ship.

## Sources

- Internal Tide application logs (private, owner-only)
- Pair session conversation with [[people/Sam Patel]] (not recorded)
- Prisma migration file `prisma/migrations/2026_04_27_streak_decay.sql` (in the fictional Tide repo)

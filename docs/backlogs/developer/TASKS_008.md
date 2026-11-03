# TASKS-008: Flow Calibration, Difficulty Levers and Frustration Barrier

**User Story:** E1 (Rate each task), E2 (One lever at a time), E3 (Frustration barrier)
**User Flow:** Flow 6 - Flow calibration after each task (SPEC §6.3, §12 step 8)
**Priority:** P0 (MVP)

---

## Prerequisites

- [x] Classification of productive struggle vs overwhelm (rules in code, no prompt file: the spec defines them exactly, see D-018)
- [x] Difficulty level 1-5 stored per skill (`LearnerSkill.difficulty_current`)
- [x] Lever catalog as data: easier (worked example, template, smaller scope, hint, split into steps), harder (remove template, add constraint, time limit, higher standard, combine with a passed skill)

---

## STEP 1: Rating (E1)

- [x] After each task show one-tap Too easy / Just right / Too hard (44px targets)
- [x] Save `FlowRating.self_rating`

## STEP 2: Collect Signals

- [x] Accuracy (concept answers, principles met)
- [x] Time taken vs given (`time_ratio`)
- [x] Number of revisions
- [x] Repeated mistakes from `Mistake.count`

## STEP 3: Decide (E2, E3)

**Question to ask:** "Which single lever changes, and when do we hold the level?"

- [x] Just right: keep
- [x] Too easy: remove one support or add one constraint
- [x] Too hard after the first ~3 hours (hours from `LearnerSkill.hours_total`): add one support
- [x] Too hard within the first ~3 hours: classify stuck vs productive struggle
- [x] Stuck = same mistake twice in a row, no improvement after a revision, or "I don't know where to start" → add one support
- [x] Productive struggle → keep level
- [x] Pick levers from history of what moved the user to "just right"
- [x] Guarantee exactly one lever per adjustment

## STEP 4: Tell the User

- [x] One-line message naming the change ("Added a template")
- [x] When level kept: say so and why
- [x] Save `lever_changed`, `classification`, new difficulty
- [x] Apply the change to the next task prompt

## STEP 5: Targets

- [x] Track success rate per skill and aim for roughly 70-85% (computed and exposed; it does not change decisions yet, see D-018)
- [x] Early-stage tasks favor quantity and speed over polish

---

## Edge Cases

- [x] Rating skipped: infer from signals, mark as inferred
- [x] Difficulty at 1 or 5: no further movement, pick another lever or keep
- [x] No lever left to add: keep level and say why

## Testing

- [x] Unit tests (no network) for lever selection: one lever only
- [x] Unit tests for the frustration barrier: each stuck condition and the productive case
- [x] Test the message always names the change or the reason for holding
- [x] Acceptance: after "Too hard" the next task changes one lever unless the barrier holds, and the app says which

---

## Task Summary

| Category | Tasks | Status |
| --- | --- | --- |
| Prerequisites | 3 | Done |
| Step 1-5 | 20 | Done |
| Edge Cases | 3 | Done |
| Testing | 4 | Done |
| **Total** | **30** | **30/30 done** |

---

**Task List Version:** 1.1
**Created:** 2026-11-03

# TASKS-008: Flow Calibration, Difficulty Levers and Frustration Barrier

**User Story:** E1 (Rate each task), E2 (One lever at a time), E3 (Frustration barrier)
**User Flow:** Flow 6 - Flow calibration after each task (SPEC §6.3, §12 step 8)
**Priority:** P0 (MVP)

---

## Prerequisites

- [ ] `prompts/flow_classification.md` (signals in, JSON out: productive struggle / overwhelm)
- [ ] Difficulty level 1-5 stored per skill (`LearnerSkill.difficulty_current`)
- [ ] Lever catalog as data: easier (worked example, template, smaller scope, hint, split into steps), harder (remove template, add constraint, time limit, higher standard, combine with a passed skill)

---

## STEP 1: Rating (E1)

- [ ] After each task show one-tap Too easy / Just right / Too hard (44px targets)
- [ ] Save `FlowRating.self_rating`

## STEP 2: Collect Signals

- [ ] Accuracy (concept answers, principles met)
- [ ] Time taken vs given (`time_ratio`)
- [ ] Number of revisions
- [ ] Repeated mistakes from `Mistake.count`

## STEP 3: Decide (E2, E3)

**Question to ask:** "Which single lever changes, and when do we hold the level?"

- [ ] Just right: keep
- [ ] Too easy: remove one support or add one constraint
- [ ] Too hard after the first ~3 hours (hours from `LearnerSkill.hours_total`): add one support
- [ ] Too hard within the first ~3 hours: classify stuck vs productive struggle
- [ ] Stuck = same mistake twice in a row, no improvement after a revision, or "I don't know where to start" → add one support
- [ ] Productive struggle → keep level
- [ ] Pick levers from history of what moved the user to "just right"
- [ ] Guarantee exactly one lever per adjustment

## STEP 4: Tell the User

- [ ] One-line message naming the change ("Added a template")
- [ ] When level kept: say so and why
- [ ] Save `lever_changed`, `classification`, new difficulty
- [ ] Apply the change to the next task prompt

## STEP 5: Targets

- [ ] Track success rate per skill and aim for roughly 70-85%
- [ ] Early-stage tasks favor quantity and speed over polish

---

## Edge Cases

- [ ] Rating skipped: infer from signals, mark as inferred
- [ ] Difficulty at 1 or 5: no further movement, pick another lever or keep
- [ ] No lever left to add: keep level and say why

## Testing

- [ ] Unit tests (no network) for lever selection: one lever only
- [ ] Unit tests for the frustration barrier: each stuck condition and the productive case
- [ ] Test the message always names the change or the reason for holding
- [ ] Acceptance: after "Too hard" the next task changes one lever unless the barrier holds, and the app says which

---

## Task Summary

| Category      | Tasks  | Status          |
| ------------- | ------ | --------------- |
| Prerequisites | 3      | Pending         |
| Step 1-5      | 22     | Pending         |
| Edge Cases    | 3      | Pending         |
| Testing       | 4      | Pending         |
| **Total**     | **32** | **0% Complete** |

---

**Task List Version:** 1.0
**Created:** 2026-11-03

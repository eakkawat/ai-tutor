# TASKS-010: Continue Mode, Spaced Review and Concepts Screen

**User Story:** F2 (Continue where I left off), F3 (Review mode, P1), F5 (Concepts screen)
**User Flow:** Flow 7 - Continue, Flow 8 - Review mode (SPEC §5.3, §5.4, §6, §12 step 10)
**Priority:** P0 (Continue, Concepts), P1 (Review mode)

---

## Prerequisites

- [x] SM-2-style scheduler on `ReviewItem` (due_at, ease, last_result)
- [x] Review items created for skills and for concepts at pass/check time
- [x] Session pause/resume from TASKS_005

---

## STEP 1: Pick Two Review Questions (F2)

**Question to ask:** "Which two questions best use the user's time?"

- [x] Select 2 due items mixed across skills and concepts
- [x] Weight toward past mistakes and shaky concepts (`Mistake`, `confusions_json`)
- [x] Skip the review if nothing is due

## STEP 2: Ask and Correct

- [x] One question at a time on Home → Continue
- [x] Wrong: brief correction with citation; mark for earlier review
- [x] Right: schedule later
- [x] Update `ReviewItem` and `ConceptMastery`

## STEP 3: Resume (F2)

- [x] Resume the active skill at the saved phase with the next task ready
- [x] No active skill: go to Flow 3 (TASKS_004)
- [x] Home states: active skill with Continue, reviews due

## STEP 4: Review Mode (F3, P1)

- [x] Review screen (`design/Review.dc.html`): question, hint, answer with citation, summary
- [x] List due items across passed skills and concepts, mixed
- [x] Correct: schedule later; wrong: hint → answer, schedule sooner
- [x] Failing the same skill repeatedly (twice in a row): move it back to "needs practice"
- [x] Failed concept drops to its last secure level (the level below the one missed; a missed Define keeps its level)
- [x] Summary at the end

## STEP 5: Concepts Screen (F5)

- [x] Concepts screen (`design/Concepts.dc.html`): list with level (define / spot / use), foundations first
- [x] Concept detail: definition, example, sources (clickable), skills that use it, what the user confuses it with
- [x] "3-minute check" on one concept: run define → spot → use questions and update levels
- [x] Levels shown as text labels, not color alone

---

## Edge Cases

- [x] First-ever Continue (nothing to review)
- [x] Review backlog large: cap per sitting
- [x] Concept with no spot-level question: generate one before checking

## Testing

- [x] Test scheduler intervals
- [x] Test weighting picks past-mistake items first
- [x] Test resume restores the exact phase and task
- [x] Test review failure sends the skill back to needs practice
- [x] Acceptance: spaced review includes concepts mixed across skills
- [x] Acceptance: close and reopen, Continue resumes at the correct phase after 2 questions

---

## Task Summary

| Category      | Tasks  | Status          |
| ------------- | ------ | --------------- |
| Prerequisites | 3      | Done            |
| Step 1-5      | 22     | Done            |
| Edge Cases    | 3      | Done            |
| Testing       | 6      | Done            |
| **Total**     | **34** | **100% Complete** |

---

**Task List Version:** 1.0
**Created:** 2026-11-03

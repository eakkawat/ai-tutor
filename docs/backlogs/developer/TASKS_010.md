# TASKS-010: Continue Mode, Spaced Review and Concepts Screen

**User Story:** F2 (Continue where I left off), F3 (Review mode, P1), F5 (Concepts screen)
**User Flow:** Flow 7 - Continue, Flow 8 - Review mode (SPEC §5.3, §5.4, §6, §12 step 10)
**Priority:** P0 (Continue, Concepts), P1 (Review mode)

---

## Prerequisites

- [ ] SM-2-style scheduler on `ReviewItem` (due_at, ease, last_result)
- [ ] Review items created for skills and for concepts at pass/check time
- [ ] Session pause/resume from TASKS_005

---

## STEP 1: Pick Two Review Questions (F2)

**Question to ask:** "Which two questions best use the user's time?"

- [ ] Select 2 due items mixed across skills and concepts
- [ ] Weight toward past mistakes and shaky concepts (`Mistake`, `confusions_json`)
- [ ] Skip the review if nothing is due

## STEP 2: Ask and Correct

- [ ] One question at a time on Home → Continue
- [ ] Wrong: brief correction with citation; mark for earlier review
- [ ] Right: schedule later
- [ ] Update `ReviewItem` and `ConceptMastery`

## STEP 3: Resume (F2)

- [ ] Resume the active skill at the saved phase with the next task ready
- [ ] No active skill: go to Flow 3 (TASKS_004)
- [ ] Home states: active skill with Continue, reviews due

## STEP 4: Review Mode (F3, P1)

- [ ] Review screen (`design/Review.dc.html`): question, hint, answer with citation, summary
- [ ] List due items across passed skills and concepts, mixed
- [ ] Correct: schedule later; wrong: hint → answer, schedule sooner
- [ ] Failing the same skill repeatedly: move it back to "needs practice"
- [ ] Failed concept drops to its last secure level
- [ ] Summary at the end

## STEP 5: Concepts Screen (F5)

- [ ] Concepts screen (`design/Concepts.dc.html`): list with level (define / spot / use), foundations first
- [ ] Concept detail: definition, example, sources (clickable), skills that use it, what the user confuses it with
- [ ] "3-minute check" on one concept: run define → spot → use questions and update levels
- [ ] Levels shown as text labels, not color alone

---

## Edge Cases

- [ ] First-ever Continue (nothing to review)
- [ ] Review backlog large: cap per sitting
- [ ] Concept with no spot-level question: generate one before checking

## Testing

- [ ] Test scheduler intervals
- [ ] Test weighting picks past-mistake items first
- [ ] Test resume restores the exact phase and task
- [ ] Test review failure sends the skill back to needs practice
- [ ] Acceptance: spaced review includes concepts mixed across skills
- [ ] Acceptance: close and reopen, Continue resumes at the correct phase after 2 questions

---

## Task Summary

| Category      | Tasks  | Status          |
| ------------- | ------ | --------------- |
| Prerequisites | 3      | Pending         |
| Step 1-5      | 22     | Pending         |
| Edge Cases    | 3      | Pending         |
| Testing       | 6      | Pending         |
| **Total**     | **34** | **0% Complete** |

---

**Task List Version:** 1.0
**Created:** 2026-11-03

# TASKS-005: Session State Machine, Teaching Prompts and Text Submissions

**User Story:** D1 (Diagnose), D2 (Learn just enough), D4 (Timed practice), D8 (Pass), D9 (Steer me back), D10 (Ask anytime, P1), G1 (This felt wrong)
**User Flow:** Flow 4 - Teaching session, Flow 9 - This felt wrong (SPEC §6.1, §6.5, §7, §12 step 4)
**Priority:** P0 (MVP), D10 P1

---

## Prerequisites

### State machine

**Question to ask:** "How do phases advance one at a time and survive a restart?"

- [ ] Define phases: diagnose, learn, check, practice, feedback, revise, pass
- [ ] Server-side state machine with transitions and guards; persisted on `Session.phase`
- [ ] Transitions only on user action (the app waits between phases)
- [ ] Mockable LLM client for tests

### Prompt assembly

- [ ] Prompt builder: persona + style rules (§6.5), phase instructions, skill + principles, retrieved chunks, learner profile, recent messages
- [ ] Fence books, submissions and profile text as data
- [ ] Prompts as files: `prompts/diagnose.md`, `prompts/teach.md`, `prompts/qa.md`
- [ ] Post-generation citation validation (reuse TASKS_002) on Learn and Feedback

---

## STEP 1: Session Screen Shell

- [ ] Session view (`design/Practice.dc.html`, `design/Main.dc.html`): chat area, phase indicator, timer, citations panel
- [ ] One question or task per message
- [ ] Message storage in `Message` with `citations_json` and `phase`

## STEP 2: Diagnose (D1)

- [ ] Generate short task or 3 questions including key concepts
- [ ] Skip concepts already at spot and use
- [ ] Output a 1-2 sentence "can do / gap" summary; save starting level and concept levels
- [ ] If the work already meets all principles: jump to Pass

## STEP 3: Learn Just Enough (D2)

- [ ] Generate explanation ≤ 300 words, one example (film scene preferred), citations
- [ ] Enforce word limit; regenerate or trim if over
- [ ] Block output with no valid citation; label anything else **[outside my books]**
- [ ] "Continue" action to advance to Check

## STEP 4: Practice (D4)

- [ ] Prepare next task, template and references before the session starts
- [ ] Task applied to the active project, default 15-25 min
- [ ] Timer: visible, pausable; overtime allowed and logged
- [ ] Text editor for submission; save `Submission` versions

## STEP 5: Pass (D8)

- [ ] Pass screen (`design/SkillReview.dc.html` or session pass state): suggest next skill
- [ ] Log hours, set `LearnerSkill.status = passed`, schedule `ReviewItem`s

## STEP 6: Steer Back and Questions (D9, D10)

- [ ] Classify off-task messages during practice; reply briefly and return to the task
- [ ] Ask-anytime: answer from retrieved chunks, then restore the same phase (P1)

## STEP 7: This Felt Wrong (G1)

- [ ] Button on every tutor message
- [ ] Optional note modal
- [ ] Append message ID, session, phase and note to `data/feedback.log`
- [ ] Return to session without interruption

## STEP 8: Pause and Resume

- [ ] Pause saves phase, timer and next task
- [ ] Resume restores exactly (used by TASKS_010)

---

## Error Scenarios

- [ ] LLM call fails mid-phase: retry, keep state, show message
- [ ] Invalid structured output: re-ask once, then fall back with a visible error
- [ ] App closed mid-practice: draft submission preserved

## Testing

- [ ] State machine tests with mocked client: legal and illegal transitions
- [ ] Test Learn word cap
- [ ] Test citation validator strips fake citations
- [ ] Test feedback.log entry format
- [ ] Acceptance: no message shows a full curriculum

---

## Task Summary

| Category      | Tasks  | Status          |
| ------------- | ------ | --------------- |
| Prerequisites | 8      | Pending         |
| Step 1-8      | 29     | Pending         |
| Errors        | 3      | Pending         |
| Testing       | 5      | Pending         |
| **Total**     | **45** | **0% Complete** |

---

**Task List Version:** 1.0
**Created:** 2026-11-03

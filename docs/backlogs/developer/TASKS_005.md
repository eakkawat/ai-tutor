# TASKS-005: Session State Machine, Teaching Prompts and Text Submissions

**User Story:** D1 (Diagnose), D2 (Learn just enough), D4 (Timed practice), D8 (Pass), D9 (Steer me back), D10 (Ask anytime, P1), G1 (This felt wrong)
**User Flow:** Flow 4 - Teaching session, Flow 9 - This felt wrong (SPEC §6.1, §6.5, §7, §12 step 4)
**Priority:** P0 (MVP), D10 P1

---

## Prerequisites

### State machine

**Question to ask:** "How do phases advance one at a time and survive a restart?"

- [x] Define phases: diagnose, learn, check, practice, feedback, revise, pass
- [x] Server-side state machine with transitions and guards; persisted on `Session.phase`
- [x] Transitions only on user action (the app waits between phases)
- [x] Mockable LLM client for tests

### Prompt assembly

- [x] Prompt builder: persona + style rules (§6.5), phase instructions, skill + principles, retrieved chunks, learner profile, recent messages
- [x] Fence books, submissions and profile text as data
- [x] Prompts as files: `prompts/diagnose.md`, `prompts/teach.md`, `prompts/qa.md`
- [x] Post-generation citation validation (reuse TASKS_002) on Learn and Feedback

---

## STEP 1: Session Screen Shell

- [x] Session view (`design/Practice.dc.html`, `design/Main.dc.html`): chat area, phase indicator, timer, citations panel
- [x] One question or task per message
- [x] Message storage in `Message` with `citations_json` and `phase`

## STEP 2: Diagnose (D1)

- [x] Generate short task or 3 questions including key concepts
- [x] Skip concepts already at spot and use
- [x] Output a 1-2 sentence "can do / gap" summary; save starting level (concept levels are set only by the check, TASKS_006, see D-015)
- [x] If the work already meets all principles: jump to Pass

## STEP 3: Learn Just Enough (D2)

- [x] Generate explanation ≤ 300 words, one example (film scene preferred), citations
- [x] Enforce word limit; regenerate or trim if over
- [x] Block output with no valid citation; label anything else **[outside my books]**
- [x] "Continue" action to advance to Check

## STEP 4: Practice (D4)

- [x] Prepare next task, template and references before the session starts
- [x] Task applied to the active project, default 15-25 min
- [x] Timer: visible, pausable; overtime allowed and logged
- [x] Text editor for submission; save `Submission` versions

## STEP 5: Pass (D8)

- [x] Pass screen (`design/SkillReview.dc.html` or session pass state): suggest next skill
- [x] Log hours (as each attempt is submitted), set `LearnerSkill.status = passed`, schedule `ReviewItem`s

## STEP 6: Steer Back and Questions (D9, D10)

- [x] Classify off-task messages during practice; reply briefly and return to the task
- [x] Ask-anytime: answer from retrieved chunks, then restore the same phase (P1)

## STEP 7: This Felt Wrong (G1)

- [x] Button on every tutor message
- [x] Optional note modal
- [x] Append message ID, session, phase and note to `data/feedback.log`
- [x] Return to session without interruption

## STEP 8: Pause and Resume

- [x] Pause saves phase, timer and next task
- [x] Resume restores exactly (used by TASKS_010)

---

## Error Scenarios

- [x] LLM call fails mid-phase: retry, keep state, show message
- [x] Invalid structured output: re-ask once, then fall back with a visible error
- [x] App closed mid-practice: draft submission preserved

## Testing

- [x] State machine tests with mocked client: legal and illegal transitions
- [x] Test Learn word cap
- [x] Test citation validator strips fake citations
- [x] Test feedback.log entry format
- [x] Acceptance: no message shows a full curriculum

---

## Task Summary

| Category | Tasks | Status |
| --- | --- | --- |
| Prerequisites | 8 | Done |
| Step 1-8 | 25 | Done |
| Errors | 3 | Done |
| Testing | 5 | Done |
| **Total** | **41** | **41/41 done** |

---

**Task List Version:** 1.1
**Created:** 2026-11-03

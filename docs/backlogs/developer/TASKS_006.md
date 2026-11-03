# TASKS-006: Foundations Check, Principle Feedback and Revise

**User Story:** D3 (Foundations check), D6 (Principle-based feedback), D7 (Revise and compare), D11 (Concept or execution?)
**User Flow:** Flow 10 - Foundations check, Flow 5 - Feedback (SPEC §6.1.1, §6.1.2, §12 step 5)
**Priority:** P0 (MVP)

---

## Prerequisites

- [x] `prompts/concept_check.md`: one question at a time, hint before answer, judged on meaning not wording
- [x] `prompts/feedback.md`: JSON with per-principle result, evidence ref, top 1-2 fixes with citations, mistakes tagged `concept` or `execution`
- [x] Schema validator for feedback JSON (every principle present, result in followed/partly/not)
- [x] Concept level logic: none → define → spot → use; define-only never counts as spot

---

## STEP 1: Load Concepts for the Skill (Flow 10)

- [x] Load `SkillConcept` entries; skip those already at the required level
- [x] Cap the check to 2-5 minutes

## STEP 2: Define (D3)

- [x] Ask in own words; judge against cited definition
- [x] On miss: hint, then answer with citation; ask again

## STEP 3: Spot (D3)

- [x] Present real example (dialogue line, storyboard frame, or clip moment) via `ConceptQuestion.asset_ref` (text examples now; frames and clips with TASKS_007)
- [x] Correct: set `ConceptMastery.level = spot`
- [x] Wrong: explain why, give a new example, ask again
- [x] If a concept fails twice: re-teach from a new angle before asking again

## STEP 4: Unlock Practice

- [x] Gate: Practice locked until all required concepts at spot
- [x] UI states which concepts are missing (`design/Practice.dc.html` locked state)
- [x] Hint before answer on every question
- [x] Update `last_checked_at` and `confusions_json`

## STEP 5: Principle Feedback (D6)

**Question to ask:** "How do we judge only against the checklist?"

- [x] Send submission + checklist + retrieved chunks to the feedback prompt
- [x] Parse result per principle: followed / partly / not followed
- [x] Evidence must point to a line (text), region (image), or timestamp + frame (video) (lines done; regions and timestamps arrive with TASKS_007)
- [x] Save `Feedback` and `PrincipleCheck`
- [x] Show top 1-2 fixes each tied to a cited principle; do not rewrite the work (at most a tiny example)
- [x] No taste comments unless asked
- [x] Checklist UI (`design/Feedback.dc.html`) with evidence (the quote and its line are shown under each verdict; the work itself is not highlighted)

## STEP 6: Concept vs Execution (D11)

- [x] Tag each mistake in `Mistake` with kind and principle chunk
- [x] Concept mistake: route to short re-teach (new angle/example) and concept check before the next attempt
- [x] Execution mistake: route straight to Practice/Revise
- [x] Mark use level for concepts shown in the work

## STEP 7: Revise and Compare (D7)

- [x] Resubmit creates a new `Submission` version
- [x] Compare versions; name what improved (revision diff)
- [x] Loop back to Feedback

## STEP 8: Pass Check

- [x] Pass only when every principle is followed
- [x] Hand off to Pass (TASKS_005 step 5)

---

## Edge Cases

- [x] Empty or tiny submission: ask for more, no feedback
- [x] Model returns a citation not in retrieved chunks: strip/flag
- [x] Same mistake repeats: keep count for the frustration-barrier rule (TASKS_008)

## Testing

- [x] Test define-only never reaches spot
- [x] Test practice gate lists missing concepts
- [x] Test pass requires all followed
- [x] Test concept mistake routes to re-teach, execution to practice
- [x] Test feedback validator rejects missing principles
- [x] Acceptance: every principle gets a result with evidence

---

## Task Summary

| Category | Tasks | Status |
| --- | --- | --- |
| Prerequisites | 4 | Done |
| Step 1-8 | 28 | Done |
| Edge Cases | 3 | Done |
| Testing | 6 | Done |
| **Total** | **41** | **41/41 done** |

---

**Task List Version:** 1.1
**Created:** 2026-11-03

# TASKS-006: Foundations Check, Principle Feedback and Revise

**User Story:** D3 (Foundations check), D6 (Principle-based feedback), D7 (Revise and compare), D11 (Concept or execution?)
**User Flow:** Flow 10 - Foundations check, Flow 5 - Feedback (SPEC §6.1.1, §6.1.2, §12 step 5)
**Priority:** P0 (MVP)

---

## Prerequisites

- [ ] `prompts/concept_check.md`: one question at a time, hint before answer, judged on meaning not wording
- [ ] `prompts/feedback.md`: JSON with per-principle result, evidence ref, top 1-2 fixes with citations, mistakes tagged `concept` or `execution`
- [ ] Schema validator for feedback JSON (every principle present, result in followed/partly/not)
- [ ] Concept level logic: none → define → spot → use; define-only never counts as spot

---

## STEP 1: Load Concepts for the Skill (Flow 10)

- [ ] Load `SkillConcept` entries; skip those already at the required level
- [ ] Cap the check to 2-5 minutes

## STEP 2: Define (D3)

- [ ] Ask in own words; judge against cited definition
- [ ] On miss: hint, then answer with citation; ask again

## STEP 3: Spot (D3)

- [ ] Present real example (dialogue line, storyboard frame, or clip moment) via `ConceptQuestion.asset_ref`
- [ ] Correct: set `ConceptMastery.level = spot`
- [ ] Wrong: explain why, give a new example, ask again
- [ ] If a concept fails twice: re-teach from a new angle before asking again

## STEP 4: Unlock Practice

- [ ] Gate: Practice locked until all required concepts at spot
- [ ] UI states which concepts are missing (`design/Practice.dc.html` locked state)
- [ ] Hint before answer on every question
- [ ] Update `last_checked_at` and `confusions_json`

## STEP 5: Principle Feedback (D6)

**Question to ask:** "How do we judge only against the checklist?"

- [ ] Send submission + checklist + retrieved chunks to the feedback prompt
- [ ] Parse result per principle: followed / partly / not followed
- [ ] Evidence must point to a line (text), region (image), or timestamp + frame (video)
- [ ] Save `Feedback` and `PrincipleCheck`
- [ ] Show top 1-2 fixes each tied to a cited principle; do not rewrite the work (at most a tiny example)
- [ ] No taste comments unless asked
- [ ] Checklist UI (`design/Feedback.dc.html`) with evidence highlight

## STEP 6: Concept vs Execution (D11)

- [ ] Tag each mistake in `Mistake` with kind and principle chunk
- [ ] Concept mistake: route to short re-teach (new angle/example) and concept check before the next attempt
- [ ] Execution mistake: route straight to Practice/Revise
- [ ] Mark use level for concepts shown in the work

## STEP 7: Revise and Compare (D7)

- [ ] Resubmit creates a new `Submission` version
- [ ] Compare versions; name what improved (revision diff)
- [ ] Loop back to Feedback

## STEP 8: Pass Check

- [ ] Pass only when every principle is followed
- [ ] Hand off to Pass (TASKS_005 step 5)

---

## Edge Cases

- [ ] Empty or tiny submission: ask for more, no feedback
- [ ] Model returns a citation not in retrieved chunks: strip/flag
- [ ] Same mistake repeats: keep count for the frustration-barrier rule (TASKS_008)

## Testing

- [ ] Test define-only never reaches spot
- [ ] Test practice gate lists missing concepts
- [ ] Test pass requires all followed
- [ ] Test concept mistake routes to re-teach, execution to practice
- [ ] Test feedback validator rejects missing principles
- [ ] Acceptance: every principle gets a result with evidence

---

## Task Summary

| Category      | Tasks  | Status          |
| ------------- | ------ | --------------- |
| Prerequisites | 4      | Pending         |
| Step 1-8      | 30     | Pending         |
| Edge Cases    | 3      | Pending         |
| Testing       | 6      | Pending         |
| **Total**     | **43** | **0% Complete** |

---

**Task List Version:** 1.0
**Created:** 2026-11-03

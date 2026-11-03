# TASKS-004: Projects and Skill Picker

**User Story:** C1 (Start from a project), C2 (Short list, not a curriculum), C3 (One active skill)
**User Flow:** Flow 3 - New project → choose one skill (SPEC §5.2, §12 step 3)
**Priority:** P0 (MVP)

---

## Prerequisites

- [x] `Project` CRUD API (name, description, good_enough, minutes_per_session, active)
- [x] `LearnerSkill` row created on first pick
- [x] Prompt `prompts/skill_recommendation.md` (project + skills in, 5-10 skills with one recommended and a one-sentence why, JSON out)

---

## STEP 1: Home → New Skill

**Question to ask:** "Is there an active project?"

- [x] "New skill" action on Home
- [x] No active project: go to project form
- [x] Active project: offer use it or create new

## STEP 2: Project Form (C1)

- [x] Form (`design/Project.dc.html`): what do you want to make, what does good enough look like, minutes per session (Type and Target date from the mockup are left out, see D-014)
- [x] Validation: all three required
- [x] Project picker for existing projects

## STEP 3: Short List (C2)

**Question to ask:** "How do we pick 5-10 relevant skills without showing a curriculum?"

- [x] Pre-filter skills by retrieval against the project text, then rank with the LLM
- [x] Return 5-10 skills, one flagged recommended with why
- [x] Flag missing prerequisites on a skill ("needs X first")
- [x] Skill picker UI (`design/Picker.dc.html`); the full skill map is never shown here
- [x] Suggest the prerequisite first or allow continue anyway

## STEP 4: One Active Skill (C3)

- [x] Enforce one active skill in the data layer
- [x] Pause dialog when another skill is active (`design/PickerPause.dc.html`); save its state
- [x] Other skills are locked until the active one is paused or passed
- [x] On confirm, create `Session` at `diagnose` and go to it (the session screen itself is TASKS_005)

---

## Edge Cases

- [x] Fewer than 5 skills in the library: show what exists with a note
- [x] Project edited later: keep sessions linked
- [x] All relevant skills already passed: say so and offer review

## Testing

- [x] Test that two skills cannot be active at once
- [x] Test pause preserves phase and next task
- [x] Test the picker never returns more than 10 skills

---

---

## Task Summary

| Category | Tasks | Status |
| --- | --- | --- |
| Prerequisites | 3 | Done |
| Step 1-4 | 15 | Done |
| Edge Cases | 3 | Done |
| Testing | 3 | Done |
| **Total** | **24** | **24/24 done** |

---

**Task List Version:** 1.1
**Created:** 2026-11-03

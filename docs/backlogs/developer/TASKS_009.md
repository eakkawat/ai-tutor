# TASKS-009: Learner Profile, Hours Tracking and Progress

**User Story:** E4 (Profile of how I learn), F1 (Hours toward 20), F4 (Progress view, P1)
**User Flow:** Flow 4 end of session (Log hours, update profile), SPEC §6.4, §12 step 9
**Priority:** P0 (MVP), F4 P1

---

## Prerequisites

- [x] `prompts/profile_update.md` (session summary in, profile notes JSON out)
- [x] `ProfileNote` read/write layer

---

## STEP 1: Hours Tracking (F1)

- [x] Keep `LearnerSkill.hours_total` equal to the minutes of all the skill's sessions (worked out continuously, not only at the end, see D-019)
- [x] Count only practice time, per the timer; include logged overtime
- [x] Paused time not counted
- [x] Handle sessions ended by closing the app

## STEP 2: Update Profile After Each Session (E4)

- [x] Update level and hours per skill
- [x] Update concept levels and confusions
- [x] Update recurring mistakes (tagged, linked to principles)
- [x] Update flow history: which levers moved the user to "just right"
- [x] Update learned preferences: examples vs rules, session length, bored/overwhelmed task types
- [x] Update explanation styles that led to correct recall (the model is given the recall-check results of the session and may write a note; the app does not yet record which explanation style came before each correct answer)

## STEP 3: Inject Profile into Prompts

- [x] Compact profile summary for every teaching prompt, fenced as data
- [x] Keep size bounded

## STEP 4: Profile Screen (E4)

- [x] Profile screen (`design/Profile.dc.html`): view all sections
- [x] Edit and delete notes
- [x] Edits take precedence over automatic updates

## STEP 5: Progress Screen (F1, F4)

- [x] Progress screen (`design/Progress.dc.html`): hours per skill toward 20
- [x] Passed skills list
- [x] Recurring mistakes
- [x] Flow history
- [x] Status shown as text, not color alone

---

## Edge Cases

- [x] Over 20 hours: show the total without breaking the bar
- [x] Empty profile on first session
- [x] Conflicting notes: newest or edited wins

## Testing

- [x] Test hours add up across several sessions
- [x] Test profile appears in the assembled prompt
- [x] Test edits persist after the next automatic update
- [x] Acceptance: hours per skill are visible and correct

---

## Task Summary

| Category | Tasks | Status |
| --- | --- | --- |
| Prerequisites | 2 | Done |
| Step 1-5 | 20 | Done |
| Edge Cases | 3 | Done |
| Testing | 4 | Done |
| **Total** | **29** | **29/29 done** |

---

**Task List Version:** 1.1
**Created:** 2026-11-03

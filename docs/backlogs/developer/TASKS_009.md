# TASKS-009: Learner Profile, Hours Tracking and Progress

**User Story:** E4 (Profile of how I learn), F1 (Hours toward 20), F4 (Progress view, P1)
**User Flow:** Flow 4 end of session (Log hours, update profile), SPEC §6.4, §12 step 9
**Priority:** P0 (MVP), F4 P1

---

## Prerequisites

- [ ] `prompts/profile_update.md` (session summary in, profile notes JSON out)
- [ ] `ProfileNote` read/write layer

---

## STEP 1: Hours Tracking (F1)

- [ ] Add session minutes to `LearnerSkill.hours_total` on session end
- [ ] Count only practice time, per the timer; include logged overtime
- [ ] Paused time not counted
- [ ] Handle sessions ended by closing the app

## STEP 2: Update Profile After Each Session (E4)

- [ ] Update level and hours per skill
- [ ] Update concept levels and confusions
- [ ] Update recurring mistakes (tagged, linked to principles)
- [ ] Update flow history: which levers moved the user to "just right"
- [ ] Update learned preferences: examples vs rules, session length, bored/overwhelmed task types
- [ ] Update explanation styles that led to correct recall

## STEP 3: Inject Profile into Prompts

- [ ] Compact profile summary for every teaching prompt, fenced as data
- [ ] Keep size bounded

## STEP 4: Profile Screen (E4)

- [ ] Profile screen (`design/Profile.dc.html`): view all sections
- [ ] Edit and delete notes
- [ ] Edits take precedence over automatic updates

## STEP 5: Progress Screen (F1, F4)

- [ ] Progress screen (`design/Progress.dc.html`): hours per skill toward 20
- [ ] Passed skills list
- [ ] Recurring mistakes
- [ ] Flow history
- [ ] Status shown as text, not color alone

---

## Edge Cases

- [ ] Over 20 hours: show the total without breaking the bar
- [ ] Empty profile on first session
- [ ] Conflicting notes: newest or edited wins

## Testing

- [ ] Test hours add up across several sessions
- [ ] Test profile appears in the assembled prompt
- [ ] Test edits persist after the next automatic update
- [ ] Acceptance: hours per skill are visible and correct

---

## Task Summary

| Category      | Tasks  | Status          |
| ------------- | ------ | --------------- |
| Prerequisites | 2      | Pending         |
| Step 1-5      | 22     | Pending         |
| Edge Cases    | 3      | Pending         |
| Testing       | 4      | Pending         |
| **Total**     | **31** | **0% Complete** |

---

**Task List Version:** 1.0
**Created:** 2026-11-03

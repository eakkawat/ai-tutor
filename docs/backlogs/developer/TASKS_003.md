# TASKS-003: Skill Extraction, Concepts Library and Skill Map

**User Story:** B3 (Practicable skills), B4 (Edit the skill map), B5 (Merge books, P1), B7 (Concepts library)
**User Flow:** Flow 2 - Add a book, from skill extraction onward (SPEC §5.1, §6.1.1, §12 step 2)
**Priority:** P0 (MVP), merge diff P1

---

## Prerequisites

**Question to ask:** "What does a good extracted skill look like, and how do we check it?"

- [x] Write `prompts/skill_extraction.md`: skills phrased as things I can do, 15-60 min per attempt, at least one source chunk, 2-6 principles each with a one-line test and chunk citation, prerequisites, practice type
- [x] Write `prompts/concept_extraction.md`: definition in plain words, one film example, citation
- [x] Write `prompts/skill_merge.md`
- [x] JSON schemas and validators for all three outputs
- [x] Validator rule: reject skills with no chunk, principles with no chunk, or invented chunk IDs

---

## STEP 1: Extract Skills

- [x] Run extraction after triage for practicable books
- [x] Save `Skill`, `SkillPrinciple`, `SkillSource`, `SkillPrereq`
- [x] Link every skill to at least one concept

## STEP 2: Extract Concepts (B7)

**Question to ask:** "How do we avoid duplicate concepts across books?"

- [x] Extract concepts per skill; save `Concept`, `ConceptSource`, `SkillConcept` with `required_level`
- [x] Match against existing concepts by name and embedding; link instead of duplicating
- [x] Flag `is_foundation` when many skills depend on a concept
- [x] Generate `ConceptQuestion` rows for define, spot and use levels (spot is text for now; `asset_ref` stays empty until TASKS_007)
- [x] Initialize `ConceptMastery` as `none`

## STEP 3: Match Existing Skills (B5, P1)

- [x] Detect candidate matches between new and existing skills
- [x] Merge diff UI: "adds 2 principles to *Scene want/obstacle*" with accept/reject (`design/SkillReview.dc.html`)
- [x] On accept, add sources and principles; never duplicate

## STEP 4: Auto vs Manual Mode

- [x] Setting for mode
- [x] Auto: add skills straight to the map
- [x] Manual: one skill card at a time with principles and citations; keep / edit / delete

## STEP 5: Skill Map Screen (B4)

- [x] Skill Map (`design/SkillMap.dc.html`) grouped by domain; status (not started / in progress / passed) and hours
- [x] Rename skill, delete skill
- [x] Split skill into two (reassign principles and sources)
- [x] Merge two skills manually
- [x] Edit principles (text, test, source)
- [x] Skill detail: name, one-line description, 2-6 principles with citations, prerequisites, practice type
- [x] Never present the map as a plan; no "next" ordering here

## STEP 6: Concepts Library Data Views

- [x] API to list concepts with level, foundations first
- [x] API for one concept: definition, example, sources, skills using it, confusions

---

## Edge Cases

- [x] Book yields zero valid skills: show reason, offer retry
- [x] Skill removed that a concept depended on: keep the concept, unlink
- [x] Deleting a skill with session history: confirm and archive

## Testing

- [x] Test validators reject skills/principles without real chunks
- [x] Test concept dedupe links a second book's concept
- [x] Test split and merge keep sources and principles
- [ ] Acceptance: a storytelling book gives 5+ skills, each with page range, checklist, and linked concept (needs a real book; only a 2-chapter made-up text was tried: 2 skills)

---

## Task Summary

| Category | Tasks | Status |
| --- | --- | --- |
| Prerequisites | 5 | Done |
| Step 1-6 | 23 | Done |
| Edge Cases | 3 | Done |
| Testing | 4 | 3/4 done |
| **Total** | **35** | **34/35 done** |

---

**Task List Version:** 1.1
**Created:** 2026-11-03

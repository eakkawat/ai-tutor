# TASKS-001: Foundation, Reuse Audit and First Run

**User Story:** A1 (Check my machine), A2 (Empty state guides me)
**User Flow:** Flow 1 - First run (SPEC §12 step 0, §10, §11)
**Priority:** P0 (MVP)

---

## Prerequisites

### Reuse audit (SPEC §11)

**Question to ask:** "What in the book-learning app and chapter-splitter app can we copy instead of rebuild?"

- [x] Read the book-learning app codebase and the chapter-splitter app
- [x] Write `REUSE.md` with columns: Candidate, Where in book-learning app, Reuse as-is / adapt / skip, Why
- [x] Cover: PDF/EPUB extraction with pages and chapters, chapter-PDF input, chunking and embedding, triage, skill extraction and merge, auto/manual mode, LLM client and retry/cost handling, DB schema and migrations, file storage, UI components
- [x] Decide stack: keep the default (Next.js + Tailwind + SQLite) or match the book-learning app if reused code is substantial
- [x] Record the stack decision in `DECISIONS.md`

### Project scaffold

**Question to ask:** "What must exist before any feature can be built?"

- [x] Initialize the project with the chosen stack
- [x] Create `data/` with `library/`, `submissions/`, `frames/`; git-ignore `data/`
- [x] Create `prompts/` folder for plain-file prompts
- [x] Add `DECISIONS.md` and `IDEAS.md`
- [x] Set up test runner and a mockable LLM client interface
- [x] Port design tokens (colors, type, spacing) from `docs/DESIGN_SYSTEM.md` into Tailwind config
- [x] Build base layout and nav (Home, Library, Skill Map, Concepts, Progress, Profile)

### Database foundation

**Question to ask:** "How is the schema created and evolved?"

- [x] Set up SQLite at `data/app.db` with `sqlite-vec`
- [x] Add migration runner
- [x] Create initial migration for tables in SPEC §9 (Source, Chunk, Skill, SkillPrinciple, SkillSource, SkillPrereq, Concept, ConceptSource, SkillConcept, ConceptMastery, ConceptQuestion, Project, LearnerSkill, Session, Message, Submission, SubmissionAsset, VideoFrame, Feedback, PrincipleCheck, FlowRating, Mistake, ProfileNote, ReviewItem)

---

## STEP 1: Launch and Dependency Check (A1)

**Question to ask:** "How does the app know what is installed and what to tell me when it is not?"

- [x] Create dependency check service: language model server (URL, model, optional key), `ffmpeg`, `ffprobe`, faster-whisper
- [x] Read server URL, model and optional key from env or local config file (never logged, never sent anywhere but the configured LLM server)
- [x] API endpoint `GET /api/setup/status` returning `{ apiKey, ffmpeg, whisper }` each `ready | missing` with a one-line fix
- [x] Build Setup screen (`design/Setup.dc.html`): all OK, API key missing, media tools missing
- [x] Form to save the API key and re-check
- [x] Store a `mediaEnabled` flag; when false, disable image and video upload with a note and keep text learning working
- [x] Run the check on every startup

## STEP 2: Route After Check

**Question to ask:** "Where does the user land after the check?"

- [x] API key missing: block on Setup until added
- [x] Media tools missing: show warning with install steps, then continue
- [x] All OK: go to Home

## STEP 3: Empty State (A2)

**Question to ask:** "What is the one thing to do next on an empty library?"

- [x] Home empty state (`design/HomeEmpty.dc.html`) with a single "Add your first book" action
- [x] Link the action to Library upload (TASKS_002)
- [x] Home states switch on data: empty library, no active skill, active skill with Continue, reviews due

---

## Error Scenarios

- [x] Invalid API key: test call fails, show clear message, stay on Setup
- [x] LLM server unreachable: show offline notice; non-LLM screens still work
- [x] ffmpeg present but Whisper model missing: report separately

## Testing

- [x] Unit test dependency check with each combination missing
- [x] Unit test that a missing media tool disables only image/video features
- [x] Verify no telemetry or analytics calls exist

---

## Task Summary

| Category      | Tasks  | Status                |
| ------------- | ------ | --------------------- |
| Prerequisites | 15     | Done                  |
| Step 1-3      | 13     | Done                  |
| Errors        | 3      | Done                  |
| Testing       | 3      | Done                  |
| **Total**     | **34** | **34/34 done**    |

---

**Task List Version:** 1.1
**Created:** 2026-11-03

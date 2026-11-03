# CLAUDE.md: AI Tutor

Guidance for Claude Code working in this repository.

## What this is

A **local-only, single-user web app** that turns my own books and courses into a map of small, practicable skills, then teaches me one skill at a time like an experienced teacher. It diagnoses, explains briefly from my books with citations, quizzes, gives timed practice on a real project, judges my work against cited principles, and keeps tasks in my flow zone. Method: *The First 20 Hours* (Josh Kaufman).

I'm a filmmaking and screenwriting student. Examples, sample data and copy should lean on film and screenwriting.

## Read these first

| File | What it holds |
| --- | --- |
| `docs/SPEC.md` | Product spec: goals, teaching engine, data model, architecture, MVP order, acceptance criteria, decisions |
| `docs/USER_STORIES_AND_FLOWS.md` | User stories (P0/P1) with acceptance criteria, 9 flowcharts, screen list |
| `docs/DESIGN_SYSTEM.md` | Colors, type, spacing, components, accessibility rules |
| `design/` | HTML mockups of every screen (open any `.dc.html` as reference; not production code) |

The spec wins over the mockups if they disagree. Ask me before changing a decision in SPEC.md §14.

## Build order

Follow SPEC.md §12. Do **step 0 first**:

0. **Reuse audit.** Read my book-learning app and chapter-splitter app, then write `REUSE.md` (candidate, location, reuse / adapt / skip, why). Copy reused code in (no runtime dependency) and note the source path in a comment. If the reused code is substantial, match its stack.
1. Upload PDF → extract text with page numbers → chunk → embed.
2. Skill extraction with principle checklists → editable skill map, plus concept extraction into the Concepts library.
3. Projects and the skill picker.
4. Session state machine (7 phases) with citations and text submissions.
5. Foundations check (define / spot / use), principle-based feedback with concept vs. execution mistakes, pass check.
6. Image submissions → 7. Video submissions.
8. Flow rating, levers, frustration-barrier rule.
9. Learner profile and hours tracking → 10. Continue mode with spaced review of skills and concepts; Concepts screen.

Finish and check each step before starting the next. After each step, tell me what works and what to try.

## Default stack

Unless the reuse audit says otherwise: Next.js + React + Tailwind, Next.js API routes (or a small FastAPI service if PDF/video processing is easier in Python), SQLite with `sqlite-vec`, an OpenAI-compatible LLM server (`openai` SDK), ffmpeg, faster-whisper. Data lives in `data/` (`library/`, `submissions/`, `frames/`, `app.db`, `feedback.log`). `data/` is git-ignored.

## Rules that must never break

**Grounding**
- Every Learn and Feedback message cites `[Book, ch. X, p. Y]` pointing to a real retrieved chunk. Validate citations after generation; strip or flag any that don't match.
- General knowledge only when labeled **[outside my books]** and shown visually distinct.
- Never invent quotes, page numbers or book content, including in seed data and tests. Use placeholders like `[Book A]`.

**Teaching**
- One active skill at a time. Never show the whole skill map as a plan, only the next step.
- Phases run one at a time; the app waits for me between them.
- Creative work is judged **only** on the skill's principle checklist: followed / partly / not followed, with evidence (line, image region, or timestamp + frame). Pass = all followed. No taste comments unless I ask.
- Feedback gives the top 1–2 fixes and never rewrites my work.

**Fundamentals (SPEC §6.1.2)**
- Concepts are first-class records shared across skills, each with a cited definition and a film example.
- Test concepts at three levels in order: define → spot → use. Defining alone never counts as knowing a concept.
- Practice stays locked until the skill's required concepts reach **spot**; say which are missing.
- Tag every feedback mistake as `concept` or `execution`. Concept mistakes route to a short re-teach and check; execution mistakes route to practice.
- Concept checks stay 2–5 minutes and tied to the current skill. Never build a standalone vocabulary course.
- Spaced review covers concepts too, mixed across skills.

**Flow calibration**
- After every task: Too easy / Just right / Too hard, combined with accuracy, time and revisions.
- Change exactly **one** lever per adjustment and tell me which.
- Frustration barrier: within the first ~3 hours on a skill, "Too hard" keeps the level unless I'm truly stuck (same mistake twice in a row, no improvement after a revision, or I say I don't know where to start). Say why.

**Local-only**
- No hosting, login, analytics or telemetry. The only network calls are to the configured OpenAI-compatible LLM server (and a hosted embedding model only if no local one works).
- Check ffmpeg, Whisper and the API key on startup. Missing media tools disable only image/video features.
- Video clips over ~3 minutes are rejected with a message to split them.

**"This felt wrong"**
- Every tutor message has this button. It appends message ID, session, phase and my note to `data/feedback.log`. Keep it working; it's how the app improves.

## LLM prompts

- One prompt per job: triage, skill extraction, concept extraction, skill merge, diagnose, teach, concept check, feedback (with mistake kind), flow classification, profile update. Keep them in `prompts/` as plain files, not inline strings.
- Every teaching prompt gets: persona + style rules (SPEC §6.5), phase instructions, current skill + principles, retrieved chunks, learner profile, recent messages.
- Ask the model for structured JSON where the app needs data (checklist results, flow classification, extracted skills) and validate it.
- Any text from books, my submissions or the profile goes into prompts fenced as data, never as instructions.

## UI

- Follow `docs/DESIGN_SYSTEM.md` and the mockups in `design/`. Reuse the tokens; don't introduce new colors or fonts.
- Real `<button>`, `<a>`, `<label>`/`<input>`; 44px minimum touch targets; text contrast ≥ 4.5:1.
- Copy is short and plain. Status is always shown as text, never by color alone.

## Working style

- Small commits with clear messages. Run tests before saying something works.
- Test the teaching logic without the network: mock the LLM client for the state machine, lever selection, frustration-barrier rule and citation validation.
- When something in the spec is unclear, make the simplest reasonable choice, note it in `DECISIONS.md`, and keep going. Ask me only for choices that are hard to undo.
- Don't add features outside SPEC.md. Put ideas in `IDEAS.md` instead.

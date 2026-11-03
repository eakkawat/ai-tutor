# SPEC: AI Tutor

A personal web app that turns my own books and courses into a map of small skills, then teaches me one chosen skill at a time like an experienced teacher: it diagnoses my level, explains from my books with citations, quizzes me, gives practice on my real project, critiques my work, and keeps every task in my flow zone.

## 1. Problem

I read a lot about learning and about my subjects (storytelling, filmmaking), but I don't feel progress. Reading feels productive; it isn't practice. Generic AI chat explains well but:

- answers from its own memory, which I don't trust;
- gives full curricula, which overwhelm me;
- doesn't remember my level, my mistakes, or what difficulty works for me;
- doesn't push me to produce real work and revise it.

## 2. Goals

1. **Grounded teaching:** every explanation and every piece of feedback cites a specific book and page/chapter from my library.
2. **One small skill at a time:** I pick a skill from a map; the app never shows a full curriculum as a plan to follow.
3. **Practice on real work:** every skill ends in assignments applied to a project I care about.
4. **Teacher behavior:** diagnose → explain just enough → check → practice → feedback → revise → pass.
5. **Personal adaptation:** the app learns how *I* learn and keeps tasks in my flow zone (not boring, not overwhelming).
6. **The First 20 Hours:** the method from Josh Kaufman's book is built into the structure (see §6).
7. **Fundamentals first:** the core terms and principles behind each skill are tested before and during practice, at the level of spotting and using them, not just defining them (see §6.1.2).

## 3. Non-goals (v1)

- Multiple users, sharing, classrooms.
- Hosting, cloud deployment, or access from other devices. The app is **local-only**.
- Teaching from the open web or the model's general knowledge (allowed only when clearly labeled, see §7).
- Video/audio lessons produced by the app, mobile app.
- Auto-generating a full course.
- A separate validation phase before building. The app is improved by using it (see §12).

## 4. Core concepts

| Concept | What it is |
| --- | --- |
| **Library** | My uploaded books and courses (PDF, EPUB, text, transcripts). |
| **Source chunk** | A passage from a source with location (book, chapter, page). Everything taught must point to chunks. |
| **Skill Map** | Small, concrete, practicable skills extracted from the library, grouped by domain, with prerequisites. |
| **Skill** | One teachable unit, e.g. "Write a scene where a character wants something and is blocked." Has sources, prerequisites, a practice type, and pass criteria. |
| **Concept** | One fundamental term or principle from my books (e.g. "subtext", "the 180° rule"), with a cited definition and a film example. Shared across skills: learned once, reused everywhere. |
| **Project** | Something real I want to make (e.g. "3-minute short film about my grandmother"). Skills are chosen and practiced in service of it. |
| **Session** | One timed learning sitting on one skill. |
| **Learner Profile** | What the app knows about how I learn: levels, recurring mistakes, flow history, preferences, hours per skill. |

## 5. Main user flows

### 5.1 Add sources → build the Skill Map

1. I upload a book (or chapter PDFs from my chapter-splitter app).
2. App extracts text with page/chapter locations, chunks it, embeds it.
3. **Triage** using table of contents + preface: what kind of book is it (practical / theory / reference / narrative), what skills it likely teaches, or "no practicable skills."
4. **Skill extraction:** the LLM proposes skills from the book. Each skill must be:
   - small enough to practice in 15–60 minutes per attempt;
   - phrased as something I can *do*;
   - backed by at least one source chunk.
5. **Concept extraction:** the LLM pulls the fundamental terms and principles each skill depends on into the Concepts library (definition, film example, citation). Concepts that already exist are linked, not duplicated.
6. **Merge:** skills from new books that match existing skills are merged (adding sources), not duplicated.
7. I can review, rename, delete, or split skills. Auto mode accepts suggestions directly; manual mode asks me.

### 5.2 Start learning (New skill)

1. App asks: what do you want to *make*? What does "good enough" look like? How many minutes per session?
2. App shows **5–10 skills** from the map most relevant to that project, with one recommended first and one sentence why. It also flags missing prerequisites.
3. I choose **one** skill.
4. Session starts at **Diagnose** (§6.2).

### 5.3 Continue

1. App opens with a **2-question spaced review** of earlier skills and concepts, weighted toward past mistakes and shaky concepts.
2. Resumes the active skill where I left off, with the exact next task ready.

### 5.4 Review

Quiz-only mode on passed skills and their concepts, mixed across skills; failures send the skill back to "needs practice" and the concept back to its last secure level.

## 6. Teaching engine

### 6.1 Session loop

Each phase is a step in a state machine. The app does one phase at a time and waits for me.

| Phase | What happens | Output stored |
| --- | --- | --- |
| 1. Diagnose | One short task or 3 questions on the skill, including its key concepts. Concepts I already spot and use are skipped. App states what I can do and the gap in 1–2 sentences. | Starting level, concept levels |
| 2. Learn just enough | Explanation ≤ 300 words + one concrete example (film scene preferred) + citations. Only what's needed to self-correct. | — |
| 3. Check (foundations) | 2–5 minutes on the lesson and the concepts this skill depends on, one question at a time, at three levels: define, spot, use (§6.1.2). Hint before answer. Practice unlocks only when the needed concepts reach **spot**. | Concept levels |
| 4. Practice | One timed assignment (default 15–25 min) on my project. Early: quantity and speed over polish. | My submission |
| 5. Feedback | What works + top 1–2 fixes, each tied to a cited principle. Doesn't rewrite my work; at most a tiny example of the fix. Each mistake is tagged **concept** (misunderstood) or **execution** (knew it, didn't do it). | Feedback, mistakes tagged by kind |
| 6. Revise | I redo it; app compares versions and names what improved. | Revision diff |
| 7. Pass check | Pass when the work follows the skill's principles (§6.1.1). Otherwise, concept mistakes loop to a short re-teach and check of that concept; execution mistakes loop to Practice with adjusted difficulty. | Pass/not yet, hours logged |

#### 6.1.1 Judging creative work

Creative work is judged **only on whether it follows the principles** behind the skill, not on taste or quality in general.

- When a skill is extracted, it gets a **principle checklist**: 2–6 principles, each with a one-line test and the source chunk it comes from (e.g. "The character's want is clear by the end of the first beat — [Book, ch. 3, p. 41]").
- Feedback goes through the checklist item by item: **followed / partly / not followed**, with evidence pointing to the exact part of my submission (a line, a frame, a timestamp).
- **Pass** = every principle on the checklist is followed.
- The tutor does not comment on taste or style beyond the checklist, unless I ask.

#### 6.1.2 Fundamentals (concepts)

Complex skills rest on a few fundamentals, so the app tracks them separately from skills.

- **Concept library:** each concept has a plain-words definition, one film example, citations, and the skills that use it. A concept that many skills depend on is flagged **foundation** and recommended early.
- **Three levels of mastery,** tested in this order:

| Level | Question type | Example |
| --- | --- | --- |
| Define | Explain it in your own words | "What is subtext?" |
| Spot | Find it in an example (a line, a frame, a clip) | "Which of these three lines has subtext?" / "Where does this clip break the 180° rule?" |
| Use | Apply it in a small task or in practice work | "Rewrite this line so it carries subtext." |

- Recognising a term is not enough. Practice on a skill needs its concepts at **spot**; passing a skill shows them at **use** through the practice work itself.
- Define answers are judged against the cited definition for meaning, not wording.
- **Mistake routing:** when feedback finds a **concept** mistake (I misunderstood it), the tutor re-teaches that concept briefly (new angle, new example) and checks it again before more practice. **Execution** mistakes (I knew it but didn't do it) go back to practice.
- **Guard:** concept checks stay short (2–5 minutes) and tied to the current skill. There is no standalone vocabulary course.

### 6.2 The First 20 Hours, mapped to features

| Kaufman principle | Where it lives in the app |
| --- | --- |
| Choose a lovable project | Project required before choosing a skill |
| Focus on one skill at a time | Only one active skill; others are locked until paused or passed |
| Define target performance level | "Good enough" captured per project, pass criteria per skill |
| Deconstruct into subskills | Skill Map |
| Learn enough to self-correct | Learn phase limited to ≤ 300 words, few sources, only the concepts this skill needs |
| Remove barriers to practice | Next task, template and references are prepared before the session starts |
| Make dedicated time | Session timer; optional daily reminder |
| Fast feedback loops | Feedback right after every submission |
| Practice by the clock in short bursts | Timed tasks; hours tracked per skill toward 20 |
| Quantity and speed | Early-stage tasks ask for many quick attempts |

### 6.3 Flow calibration

After every task the app asks one tap: **Too easy / Just right / Too hard**.

It combines this with objective signals:

- accuracy (concept questions, pass criteria met);
- time taken vs. time given;
- number of revisions needed;
- repeated mistakes.

Each skill has a **difficulty level** (1–5). Adjustments change **one lever at a time**:

| Direction | Levers |
| --- | --- |
| Make easier (add support) | Worked example, template, smaller scope, hint, split into steps |
| Make harder (remove support) | Remove template, add constraint, time limit, higher standard, combine with a passed skill |

Target: I succeed most of the time but only with a stretch (roughly 70–85% success).

**Frustration barrier rule.** In the first ~3 hours on a skill, "Too hard" does not automatically lower difficulty. The app classifies:

- **Productive struggle** → keep the level, encourage: mistakes are present but each attempt improves.
- **Real overwhelm** → add support: same mistake twice in a row, no improvement after a revision, or I say I don't know where to start.

### 6.4 Learner Profile (personal adaptation)

Updated after every session:

- level and hours per skill;
- concept levels (define / spot / use) and concepts I keep confusing;
- recurring mistakes (tagged, linked to principles);
- flow history: which levers moved me to "just right";
- preferences learned: examples vs. rules, session length that works, task types that bore or overwhelm me;
- what explanation styles led to correct recall.

The profile is injected into every teaching prompt. I can view and edit it.

### 6.5 Teacher persona and style rules

- Experienced teacher (20+ years), direct and honest, no empty praise.
- Short messages; one question or task per message.
- Ask before telling: I try first, then guidance.
- Never show the whole skill map as a plan; only the next step.
- If I drift into theory or reading, steer me back to practice.
- Use film and screenwriting examples when possible.

### 6.6 Submissions: text, images, video

Assignments can be submitted as any mix of:

| Type | Examples | How the tutor reads it |
| --- | --- | --- |
| Text | Scenes, loglines, beat sheets, shot lists | Directly |
| Images | Storyboard frames, stills, mood boards, lighting setups | Sent to the model as images |
| Video clips | Rough cuts, shots, short scenes | Processed locally first (below) |

**Video processing (local):**

1. Extract keyframes with ffmpeg: scene-change detection plus a frame at a fixed interval (e.g. every 2 s). Cap the number of frames per clip; sample evenly if over the cap.
2. Transcribe dialogue/audio locally (e.g. Whisper) with timestamps.
3. Collect metadata: duration, number of cuts and cut timestamps, shot lengths.
4. Send frames (with timestamps) + transcript + cut data to the model.

Feedback on images and video points to evidence by **frame number or timestamp** (e.g. "0:12–0:18: the reaction shot comes before we know what she sees"). The session view shows the referenced frame next to the comment.

Limits for v1: clips up to ~3 minutes; longer clips are rejected with a message to split them.

## 7. Grounding and citations

- Retrieval: every teaching prompt includes the top relevant chunks for the current skill (hybrid keyword + embedding search, filtered to the skill's linked sources first).
- Every claim in Learn and Feedback cites `[Book title, ch. X, p. Y]`; citations are clickable and open the source passage.
- If the library doesn't cover something, the tutor says so. General knowledge is allowed only when labeled **[outside my books]** and visually distinct.
- Validation step: after generation, check every citation points to a real retrieved chunk; strip or flag any that don't.
- No invented quotes, page numbers, or book content.

## 8. Screens

1. **Library:** upload sources, see triage results, processing status.
2. **Skill Map:** skills grouped by domain, with sources, prerequisites, status (not started / in progress / passed), hours. Edit, merge, split.
3. **Projects:** create a project, set "good enough" and session length.
4. **Session:** chat-style teaching view with phase indicator, foundations check (define / spot / use, practice locked until spot), timer, submission area for my work (text editor; drag-and-drop for images and video clips), principle checklist with followed/partly/not followed per item, frames/timestamps shown beside feedback, difficulty tap after tasks, citations panel showing source passages.
5. **Progress:** hours per skill toward 20, passed skills, recurring mistakes, flow history.
6. **Profile:** view/edit Learner Profile.
7. **Concepts:** the concept library: definition, example, citations, my level (define / spot / use), the skills that use it, foundations first.

## 9. Data model (sketch)

```
Source(id, title, author, type, file_path, status, triage_json, created_at)
Chunk(id, source_id, chapter, page_start, page_end, text, embedding)
Skill(id, domain, name, description, practice_type, difficulty_default)
SkillPrinciple(id, skill_id, principle, test, chunk_id, order)
SkillSource(skill_id, chunk_id)
SkillPrereq(skill_id, prereq_skill_id)
Concept(id, name, definition, example, is_foundation)
ConceptSource(concept_id, chunk_id)
SkillConcept(skill_id, concept_id, required_level[spot|use])
ConceptMastery(concept_id, level[none|define|spot|use], last_checked_at, confusions_json)
ConceptQuestion(id, concept_id, level[define|spot|use], prompt, answer_key, asset_ref)
Project(id, name, description, good_enough, minutes_per_session, active)
LearnerSkill(skill_id, status, level, difficulty_current, hours_total, last_session_at)
Session(id, project_id, skill_id, started_at, ended_at, phase, minutes)
Message(id, session_id, role, content, citations_json, phase, created_at)
Submission(id, session_id, version, text, created_at)
SubmissionAsset(id, submission_id, kind[image|video], file_path, duration_s, processed_json)
VideoFrame(id, asset_id, timestamp_s, file_path)
Feedback(id, submission_id, content, mistakes_json, passed)
PrincipleCheck(id, feedback_id, principle_id, result[followed|partly|not], evidence_ref, comment)
FlowRating(id, session_id, task_ref, self_rating, accuracy, time_ratio, classification, lever_changed)
Mistake(id, skill_id, concept_id, kind[concept|execution], tag, principle_chunk_id, count, last_seen_at)
ProfileNote(id, key, value, updated_at)
ReviewItem(id, skill_id, concept_id, level, question, answer, due_at, ease, last_result)
```

## 10. Architecture (suggested defaults, open to change)

**Local-only:** runs on my computer, served on localhost, no login. All books, submissions, frames and the database stay in a local data folder. The only network calls are to the configured LLM server, any OpenAI-compatible endpoint (and embeddings, if a hosted embedding model is used; a local embedding model is preferred).

- **Stack:** match the book-learning app's stack if the reuse audit (§11) finds shared code worth keeping; otherwise the defaults below.
- **Frontend:** Next.js + React + Tailwind, single-user, runs locally.
- **Backend:** Next.js API routes (or a small FastAPI service if PDF processing is easier in Python).
- **DB:** SQLite with `sqlite-vec` for embeddings (or Postgres + pgvector if it grows).
- **Ingestion:** PDF/EPUB text extraction with page numbers; chapter detection from TOC; accepts chapter PDFs from the existing chapter-splitter app.
- **LLM:** any OpenAI-compatible server (hosted, local or LAN), set by base URL, model name and an optional API key. Image submissions need a vision-capable model. Separate prompts per job: triage, skill extraction, concept extraction, skill merge, diagnose, teach, concept check, feedback (with mistake kind), flow classification, profile update.
- **Teaching orchestrator:** server-side state machine for session phases; LLM calls are made per phase with: persona + style rules, phase instructions, current skill, retrieved chunks, learner profile, recent messages.
- **Spaced review:** simple SM-2-style scheduling on ReviewItems.
- **Media:** ffmpeg for keyframes and cut detection; local Whisper (e.g. faster-whisper) for transcripts. Both must be installed locally; the app checks for them on startup and explains what's missing.
- **Storage layout:** `data/library/` (sources), `data/submissions/<session>/` (uploads), `data/frames/` (extracted frames), `data/app.db`.

## 11. Relationship to the book-learning app

This is a **separate project**. Both apps ingest books and extract skills: the book-learning app extracts skills for the **AI** (SKILL.md files); this app extracts skills for **me** to learn.

**Step 0 — reuse audit (do this before writing code).** Read the book-learning app's codebase (and the chapter-splitter app) and write `REUSE.md` listing, for each candidate:

| Candidate | Where in book-learning app | Reuse as-is / adapt / skip | Why |
| --- | --- | --- | --- |

Look especially for:

- PDF/EPUB text extraction with page numbers and chapter detection;
- chapter-PDF input handling (from the chapter-splitter app);
- chunking and embedding;
- triage from TOC + preface;
- skill extraction prompts and same-domain merging logic;
- auto vs. manual review mode;
- LLM client (OpenAI-compatible), prompt templates, retry/cost handling;
- DB schema and migrations, file storage, UI components.

Rules:

- **Copy** reused code into this project (no shared dependency at runtime for v1), and note the source path in a comment.
- Adapt skill extraction: this app needs skills phrased as practicable tasks with a principle checklist (§6.1.1), not SKILL.md files.
- If the book-learning app's stack differs from §10, prefer its stack when the reused code is substantial.

## 12. MVP scope (build in this order)

No separate validation phase: build the MVP, use it for real learning, and improve it from use. Add a small **"This felt wrong"** button in sessions that saves the message plus my note to `data/feedback.log`, to collect improvement ideas while using it.

0. Reuse audit → `REUSE.md` (§11).
1. Upload one PDF → chunk with page numbers → embed.
2. Skill extraction for that book → editable Skill Map with principle checklists, plus concept extraction into the Concepts library.
3. Create a project; choose one skill.
4. Session state machine with all 7 phases, citations, text submissions.
5. Foundations check (define / spot / use), principle-based feedback with concept vs. execution mistakes, and pass check.
6. Image submissions.
7. Video submissions (frames, transcript, cuts).
8. Flow rating after tasks + difficulty levers + frustration-barrier rule.
9. Learner Profile updated after each session; hours tracking.
10. Continue mode with 2-question spaced review of skills and concepts; Concepts screen.

Later: multi-book merging, EPUB, progress charts, reminders, video scene references from my film library.

## 13. Acceptance criteria (MVP)

- Uploading a storytelling book produces 5+ concrete, practicable skills, each linked to at least one page range.
- In a session, every Learn and Feedback message has at least one valid citation; clicking it shows the passage.
- No message presents a full curriculum; only the next step is shown.
- After a "Too hard" rating, the next task changes exactly one lever, unless the frustration-barrier rule keeps the level, and the app says which.
- Closing the app and choosing Continue resumes at the correct phase with the next task ready, after a 2-question review.
- Hours per skill are visible and add up correctly.
- Every extracted skill has a principle checklist; each principle cites a source chunk.
- Feedback marks every checklist principle as followed / partly / not followed with evidence; pass happens only when all are followed.
- An image submission gets feedback that refers to specific parts of the image.
- A video clip under 3 minutes gets feedback that cites timestamps, and the referenced frames show in the session view.
- With the network off (except the LLM server), all other features work; no data leaves the computer except prompts sent to the LLM server.
- `REUSE.md` exists and lists each reuse decision.
- Every extracted skill links to at least one concept; every concept has a cited definition and an example.
- Practice on a skill cannot start until its required concepts are at **spot**, and the app says which concepts are missing.
- Concept questions cover define, spot and use; a define-only answer never counts as spot.
- When feedback tags a concept mistake, the next step is a short re-teach and check of that concept, not another practice attempt.
- Spaced review includes concepts, mixed across skills.

## 14. Decisions

| # | Question | Decision |
| --- | --- | --- |
| 1 | Validate with a Claude Project first? | No. Build directly and improve the app by using it. |
| 2 | How to judge creative work? | Only by whether it follows the skill's principles (§6.1.1). |
| 3 | Submission types in v1? | Text, images and video clips (§6.6). |
| 4 | Where does it run? | Local-only (§10). |
| 5 | Reuse book-learning app code? | Separate project; audit the book-learning app first and copy what fits (§11). |
| 6 | Test fundamentals and terminology? | Yes. Concepts are tracked separately and tested at define / spot / use; practice needs **spot** (§6.1.2). |

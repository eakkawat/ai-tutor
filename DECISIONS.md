# DECISIONS

Small choices made while building. SPEC §14 decisions are not changed here.

## D-001 Stack follows the book-learning app (2026-11-03)

SPEC §10/§11: "prefer its stack when the reused code is substantial". `REUSE.md` shows it is (ingest, chunking, DB layer, LLM client, UI shell).

- Backend: Python 3.12 + FastAPI + Pydantic v2, plain `sqlite3` + `sqlite-vec`, PyMuPDF, managed by `uv`.
- Frontend: React + TypeScript + Vite + TanStack Query + React Router, plain CSS using the tokens in `docs/DESIGN_SYSTEM.md` §8. No Tailwind.
- LLM: any OpenAI-compatible server through the `openai` SDK, like B2S (see D-006).
- This replaces the "Default stack" line in `CLAUDE.md` (Next.js + Tailwind). Update that line when convenient.

## D-002 `mediaEnabled` gates both image and video (2026-11-03)

The A1 acceptance criterion says image and video upload are disabled when media tools are missing. `design/Setup.dc.html` says image practice still works. The spec wins. One flag, `mediaEnabled`, is true only when ffmpeg, ffprobe and Whisper (package and model) are all ready. If you want images to stay on, split the flag in `ai_tutor/setup_check.py`.

## D-003 API key status is checked live only on request (2026-11-03)

`GET /api/setup/status` reports whether a key is saved. `?verify=true` makes one cheap call to the LLM server (`GET /models`) to see if it works (used by "Check again" and after saving). This keeps non-LLM screens usable offline.

## D-004 Settings location (2026-11-03)

Machine-local settings (server URL, model, optional API key) live in `~/.config/ai-tutor/settings.json`, mode 600, like B2S. `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` in the environment or `.env` are the fallback. Data (books, db) lives in `./data`, or `AI_TUTOR_DATA`.

## D-005 No git repo yet (2026-11-03)

The folder was not a git repo when work began, so nothing is committed. Run `git init` when ready; `.gitignore` is in place.

## D-006 LLM is any OpenAI-compatible server (2026-11-03)

Changed from the Claude API at the user's request. This touches SPEC §10, §11, §13 and CLAUDE.md, which were edited to match.

- Settings: base URL and model name are required; the API key is optional (local servers often need none). The check id is `llm`.
- Verification: `GET {base_url}/models`. 401/403 = key rejected, connection error = unreachable, 404 = reachable (no list endpoint, treated as ready).
- Image submissions (TASKS_007) need a vision-capable model, sent as `image_url` content parts. Text-only models will fail on images; surface that in the UI when TASKS_007 is built.
- Structured JSON output depends on the server: use `response_format={"type": "json_object"}` where supported, always validate with Pydantic and retry once (pattern from B2S `llm/client.py`).
- Prompt caching and token/cost logging differ by server; log token counts when the server returns `usage`.
- Citation validation, fencing of book text as data, and per-job prompt files are unchanged.

## D-007 Page numbers in chapter PDFs are per chapter file (2026-11-03)

The splitter's chapter PDFs do not say where the chapter starts in the book. For a book uploaded as chapter PDFs, `page_start`/`page_end` are pages inside that chapter's file, and a citation reads `[Book, ch. 3, p. 4]` meaning page 4 of chapter 3's file. A whole-book PDF uses the real page numbers. Revisit if the splitter starts writing the start page into the filename.

## D-008 Embeddings are local EmbeddingGemma (2026-11-03)

The LLM server has no `/v1/embeddings`. The model `google/embeddinggemma-2` is already cached from the book-learning app, so `ai_tutor/embeddings.py` copies that loader (CPU, float32, lazy load, idle unload) and loads from the cache without contacting Hugging Face (`local_files_only`, with a one-time download fallback). Needs `uv sync --extra embed` (CPU torch, about 200 MB). 768 numbers per passage; the size is fixed in migration 0002 (`chunk_vec`).

## D-009 One upload = one book; triage is one model call (2026-11-03)

All PDFs chosen in one upload become one book (several files = chapter PDFs, one file = a whole book). No watch folder, no inbox grouping (see `IDEAS.md`). Triage reads the outline plus front matter (contents, preface, introduction; at most 12,000 characters) in a single call and returns type, practicable yes/no, up to 8 likely skills and a reason. Passages are about 2,500 characters, cut on chapter and page boundaries.

## D-010 A failed or unreachable model never loses the book (2026-11-03)

Chunks and embeddings are stored before triage runs. If the model is down, the book shows "Stopped" with a Retry button and stays searchable. Retry skips passages that already have embeddings. Books left on "processing" when the app closes restart on the next launch.

## D-011 Skill extraction rules (2026-11-03)

- Default mode is **Ask me first** (manual), since extraction quality is not yet known on real books. Switch on the Library page. Merges are always shown, in both modes.
- The model proposes at most 3 skills per part of a chapter. A skill is kept only if at least 2 of its principles cite a real passage from that part and it has at least one concept the text lets us define. Anything else is dropped and counted.
- The domain comes from triage (a short noun phrase, reusing existing domains when they fit).
- A match inside the *same book* is merged without asking (it is the same book restating itself). A match with an *older book* waits as a diff.
- Matching: skills in the same domain are compared by embedding (cosine ≥ 0.75), then the model decides `same_skill` and which principles add something. Concepts: same normalised name, or a new definition with cosine ≥ 0.9 to an existing one, is the same concept (the new passage is added as another source). Both thresholds are guesses; measure on real books.
- A concept used by 3 or more active skills is flagged a foundation.
- Manual edits allow 1 to 6 principles per skill (extraction asks for 2 to 6). Every principle must cite an existing passage.
- Deleting a skill keeps its concepts. Discarding a *proposed* skill removes the concepts only it brought, if nobody has practised them. A practised skill is archived, not deleted.
- Spot and use questions are written as text (made-up lines or moments). `asset_ref` stays empty until image and video examples exist (TASKS_007).
- Concept examples must come from the passage or begin "Made-up example:"; the prompt forbids describing real films from memory.

## D-012 Chunks are frozen once a book is chunked (2026-11-03)

A retry used to rebuild passages, which would orphan the citations skills hold. `source.chunked` now marks the point of no return; a retry skips extract/chunk/embed work already done and the skill stage resumes at the first chapter not in `extraction_done`. Removing a book first removes every citation into it (`purge_source_citations`): skills left with no principles are deleted or archived, and concepts left with no source are deleted.

## D-013 Triage sees chapter samples (2026-11-03)

With only titles and front matter, the model called a book with exercises "reference only". It now also reads the first 1,500 characters of up to 8 chapters (prompt `triage` v3). On a made-up two-chapter craft text the real model then found the book practicable and extracted 2 skills and 5 concepts in about 56 s.

## D-014 Projects and the skill picker (2026-11-03)

- A project has a name, what you are making, what "good enough" means, and a session length (25, 45, 60 or 90 minutes). The mockup also shows a project **Type** and a **Target date**; they are not in SPEC §9, so they are left out (CLAUDE.md: no features outside the spec).
- One active project and one active skill, both enforced by unique partial indexes (migration 0004), not only by code. Creating or using a project makes it the active one; starting a skill makes its project active.
- The short list is 5 to 10 skills (fewer if the library has fewer). Pre-filter: the 14 skills closest to the project text by embedding. The model then picks and gives a one-sentence reason each. In code: only real ids, no repeats, topped up from the similarity order if the model gives too few, and the recommended skill is the model's choice only if it needs nothing first (else the first pick that needs nothing). Passed skills and the active skill are not offered; paused ones are.
- If the model is unreachable the list is ordered by similarity and the screen says so.
- Starting a skill while another is active returns 409 `active_skill`; the screen asks to pause it. Pausing changes only `learner_skill.status`: the session, its phase, minutes and the hours stay. Starting a paused skill resumes its open session at the saved phase.
- Starting a skill creates a `Session` at `diagnose`. The session screen itself is TASKS_005; until then `/session/:id` shows "not built yet".
- Real model check: 8 film skills, project "Grandma's Kitchen": valid JSON, 7 picked with project-specific reasons, the skill with an unmet prerequisite flagged, in 19.5 s.

## D-015 The teaching session (2026-11-03)

- **One entry point.** `POST /api/sessions/{id}/act {action, text}`; the phase table in `ai_tutor/session.py` (`ALLOWED`) says which actions each phase accepts. Nothing moves on its own: Diagnose (begin, answer, advance), Learn (continue), Check (unlock), Practice/Revise (submit), Feedback (revise, pass). `ask`, the timer actions and `heartbeat` work in any phase. An illegal action is a 409 and changes nothing.
- **Practice cannot be reached yet in the real app.** The gate is already enforced: practice needs every concept of the skill at Spot or better, and says which are missing. Only the foundations check (TASKS_006) can raise concept levels, so until then a session stops at Check ("Practice is locked"). I did not add a way around it (CLAUDE.md: practice stays locked). Tests set mastery directly to exercise Practice, the timer and submissions.
- **Diagnose** sets one short task (not three questions), judges the answer against the skill's principles, saves the starting level (0 to 3), and states "can do" and "gap". It does **not** change concept levels: defining or showing a concept in a diagnostic answer is not the same as the Define → Spot questions (TASKS_006). "Meets every principle" needs a verdict and a quoted piece of evidence for each principle; otherwise the lesson is taught.
- **A failed or unusable model reply writes nothing.** Replies are checked first, then stored. The screen shows the message and "Try again" for the same action.
- **Lessons:** at most 300 words, at least one citation matching a retrieved passage, otherwise one retry and then the lesson is refused rather than shown ungrounded. Citations that match no passage are stripped. A long body is asked again once, then cut at a sentence end; if the cut removes every citation, the first valid citation is kept at the end. **Quotes** of 5 or more words must appear in a retrieved passage; the first time one does not, the model is asked again, after that the sentence is dropped (SPEC §7: no invented quotes).
- **Answers to questions** are cited the same way. An answer with no source behind it gets `[outside my books]`. In Practice and Revise, a question the model calls a drift into theory gets a one or two sentence redirect, no teaching and no citations; in other phases the question is simply answered. Asking never changes the phase or stops the clock.
- **Timer:** the server stores it (limit, elapsed, since, last seen) so a restart restores it. The screen sends a heartbeat every 30 s. If the screen was away more than 90 s, the timer stops at the last sign of life and shows as paused; a closed laptop never counts as practice. Going over the limit is allowed; overtime is summed on the session.
- **Hours** are added to the skill when each attempt is submitted (that is when the elapsed time is known), not at Pass. Pass marks the skill passed, closes the session, and schedules first reviews 1 day out: one for the skill (name the principles) and one per concept (its Spot question, else Define).
- **The practice task** is prepared when the learner enters Check (so it is ready), and made on unlock if that failed. Minutes are clamped to 15 to 25. The task stays the same across revisions.
- **"This felt wrong"** appends one JSON object per line to `data/feedback.log`: `at, message_id, session_id, phase, note, message`.
- **Real model check** (your server, one made-up craft text): begin 2.6 s, answer 3.9 s, lesson 8.5 s, question 4.1 s, practice task 5.4 s, a theory question during practice was steered back. The lesson cited the book with a verbatim, verified quote.

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

## D-016 Foundations check, feedback and routing (2026-11-03)

- **The check** asks, per concept the skill rests on, a Define question and then a Spot question; concepts already at Spot or Use are skipped. Questions come from the concept library first (stored `ConceptQuestion` rows), else a generic "in your own words" for Define or a freshly written example for Spot. Spot examples are text (made-up lines or moments) until image and video examples exist (TASKS_007).
- **Define alone never reaches Spot.** A correct Define answer sets the level to `define` at most; only a correct Spot answer sets `spot`; only feedback on practice work sets `use`, and only for a concept already at Spot and not named in a concept mistake.
- **Judging** is by meaning against the cited definition, not wording. A wrong answer gets a hint and the same question again; a second wrong answer shows the answer with a citation, re-teaches from a new angle (about 80 words, cited) and moves on to a new question. What the answer was confused with is saved on the concept with a count.
- **Budget:** 12 questions per sitting (about 4 minutes), then "Keep checking" extends it. The time shown is questions left × 1 minute.
- **Feedback** is judged only against the checklist. Evidence is an exact quote; the code finds it and derives the line number (the model's own line numbers are never used). A "followed" with no findable quote is shown as "partly". Pass = all followed with evidence. Each fix carries the book citation of the principle it belongs to, attached by code; citations in the model's prose are removed. At most 2 fixes, only for principles not followed; a failing principle with no fix from the model gets a plain one.
- **Incomplete verdicts** (a principle missing, repeated or unknown) are asked again once, then refused. The submission is kept, the phase is Feedback, and the screen shows "Get feedback". Work is never lost to a model failure.
- **Too short to judge** (under 15 characters or 3 words) is refused at submit, nothing saved.
- **Mistakes** are saved with kind, tag and the principle's passage; the same kind and tag seen again adds to its count (read by the frustration barrier in TASKS_008). A "concept" mistake that does not name a concept of this skill counts as "execution", since it could not be re-taught.
- **Routing:** an execution mistake goes straight to Revise. A concept mistake blocks Revise ("A concept needs another look…"): Re-teach shows a short new-angle explanation, drops the concept back to `define`, and returns to Check, which then asks only that concept (Spot). Unlocking after a re-teach returns to Revise on the **same task**.
- **Revise** starts from the work handed in. Each resubmission is a new version with the previous verdicts given to the model as context. The difference between attempts is computed in code (per principle: improved, same, worse; lines added and removed) and the sentence "Improved: principle 2." is used unless the model gives its own. "Compare attempts" shows a line-by-line view.
- **Real model check** (your server, a made-up craft text with one concept): Define judged in 2.7 s; a wrong Spot answer got a hint; a second wrong answer got the cited answer and a cited re-teach (8.7 s); a new example was written; practice unlocked; feedback on a short scene took 6.9 s, quoted lines correctly and proposed one concrete fix.
- **Known limit:** stored Spot questions written during extraction often put the choices on one line ("A: … B: …"); the screen now splits them into buttons. Evidence for images and video (regions, timestamps) arrives with TASKS_007; the data fields exist (`principle_check.locator`, `evidence_ref`).

## D-017 Pictures and clips (2026-11-03)

- **Attachments belong to the session first.** They are uploaded while the learner works, before the submission exists, so `submission_asset.submission_id` is now optional (migration 0007 rebuilds the table) and the asset has a `session_id`. Submitting attaches every ready draft to that attempt; a revision starts with none.
- **D-002 still holds:** one `media_enabled` flag turns off both pictures and clips when ffmpeg, ffprobe or Whisper is missing, with the reason on screen. Text practice is unaffected.
- **Limits:** pictures up to 25 MB (shrunk to 1,568 px on the long side before the model sees them; a 160 px thumbnail for the screen); clips up to 3:00 (a clip exactly at the limit, or up to half a second over, is accepted); 6 pictures and 2 clips per attempt; 20 keyframes per clip (a frame every 2 s plus one just after each shot change, near-duplicates merged, sampled evenly over the cap with the first and last kept). At most about 46 pictures reach the model for one attempt.
- **Clips are processed in a background worker** (one at a time, resumed after a restart): cuts, then keyframes, then the transcript. The screen polls every 1.5 s and shows each step. A clip with no audio, or with Whisper unavailable or failing, just skips the transcript with a note; an ffmpeg failure marks the clip as failed with the reason, keeps the file, and offers "Try this clip again". A clip that is processing or failed holds the submission back; a picture or clip alone is a valid submission (no minimum text).
- **What the model receives** is never the video: labelled frames (`VIDEO 1 · frame 3 · 0:06 (shot change)`), the shot-change times and shot lengths, and the timestamped dialogue, in the same order as the pictures. If the server says the model cannot read images (`architecture.input_modalities` in its model list), the picture warning is shown and feedback on an attempt with pictures is refused (the work is kept, not retryable until the model is switched). When the server does not say, the app tries.
- **Evidence in pictures and clips** is checked like quotes are. Image: a real IMAGE number, and the box (fractions of the picture) if it is valid; an invalid box is dropped and the verdict then names the whole picture ("Image 1"); a valid box adds the place ("Image 1, upper left"). Video: a real VIDEO number and a time range inside the clip (clipped to its length); the stored frames in that range (plus or minus 1 s, at most 4) are shown beside the comment, or the nearest frame. A "followed" verdict with evidence that points at nothing real counts as "partly", exactly as for text.
- **faster-whisper and PyAV:** the newest `av` (19) breaks faster-whisper 1.2.1 (`open() got an unexpected keyword argument 'metadata_errors'`), so the `media` extra pins `av>=11,<17`. Found by running the real thing. Whisper `small` runs on the CPU (int8) from the cache already on this machine.
- **Real checks** (your server, which reports image input): a drawn storyboard frame was judged against two principles in 60 s, with boxes that matched where the tin and Grandma were drawn; a 3-second clip got timestamped verdicts in 32 s; ffmpeg and Whisper processed a clip in 2.3 s. Feedback with pictures is slow (the model reads every image); the screen shows "Thinking…" while it works.

## D-018 Flow calibration (2026-11-03)

- **When:** after the feedback on each attempt, one tap: Too easy, Just right or Too hard (plus "Too hard, and I don't know where to start"). Skipping the tap is allowed: moving on (revise, re-teach or finish) judges the rating from the work and records it as inferred (a perfect first attempt well inside the time = too easy; under 40 percent of the principles, or three attempts without progress = too hard; otherwise just right). An inferred change that cannot be written (the model is down) is skipped and never blocks the learner. After a pass the rating is recorded but nothing changes, since there is no next task.
- **The rules run in code, not in a model call.** The spec states them exactly, so there is no `flow_classification` prompt (the task list asked for one). The model is only used to write a new piece of a task (`prompts/task_adjust.md`) and to build the task from the set-up (`practice_task` v2).
- **A lever is one entry in the task's set-up.** Supports (worked example, beat template, smaller scope, hint, split into steps) can be added or removed. Constraints (extra constraint, shorter time limit, higher standard, a passed skill combined in) can be added or taken away. 18 levers in all (`ai_tutor/flow.py`). The set-up is stored per skill (`learner_skill.levers_json`, default: beat template on) with the level 1 to 5; each change moves the level by exactly 1 and pulls exactly 1 lever (checked by a test over every combination).
- **Which lever:** Easier = take back a constraint first (latest first), else add a support in this order: worked example, smaller scope, hint, split into steps, beat template. Harder = take away a support first (latest first), else add a constraint: extra constraint, shorter time limit, higher standard, combine a passed skill (only if one exists). Past ratings steer it: a lever is credited when the next rating of that skill was "just right" and debited when the same complaint came back (less when it swung the other way); the best-scoring lever wins and a lever that failed is a last resort.
- **The frustration barrier:** within the first 3 hours on a skill (hours logged so far), "Too hard" keeps the level unless the learner is truly stuck: the same kind of mistake on the same principle (or the same tag) in two feedbacks in a row, a revision that did not improve (accuracy not up and no principle better), or "I don't know where to start". Productive struggle says so and names the lever it would use next. Stuck, or past 3 hours, adds one support and names the reason.
- **Limits:** at level 5 "Too easy" and at level 1 "Too hard" keep the level and say so; so does a set-up with nothing left to pull.
- **What changes in the task:** the same task, one piece different. Taking something away needs no model call; adding writes only the new piece, which is put into the task by code, so "everything else stays the same" is true. The shorter time limit is 75 percent of the base minutes (never under 10). The change applies to the very next attempt (the task is updated in place before revising), and later tasks for the skill are built from the stored set-up.
- **Failure is safe:** the model call comes first; if it fails, the tap is not recorded and can be repeated.
- **Early stage:** under 3 hours on a skill the task prompt asks for several quick short attempts instead of one polished piece, and the screen shows "Speed over polish".
- **Success rate** per skill (share of the last 5 attempts with at least 70 percent of principles followed, partly counting half) is computed and shown in the session data with the 70 to 85 percent target. It does not change any decision yet; the Progress screen (TASKS_009) will show it.
- **Real model check** (your server): a task built with a beat template and the early-stage "three quick versions" ask in 5.6 s; "Too hard, and I don't know where to start" added a worked example in 3.2 s, with the message "One change: a worked example is added for attempt 2. Everything else stays the same. You said you do not know where to start, so I am adding support."

## D-019 Hours, the learner profile and Progress (2026-11-03)

- **Hours are worked out, never added to.** `hours_total` = for every session of the skill, the minutes on submitted tasks plus the time on the task in progress (`ai_tutor/hours.py`), recomputed after each submit, timer pause, skill pause and pass. This replaces the "add the minutes at submit" of D-015: it cannot double count, includes overtime, leaves out paused time, and a task in progress counts live on the screen. The task asked for hours "on session end"; waiting would lose the time on a task left unsubmitted, so it is counted continuously instead.
- **A closed app stops the clock.** At start-up every timer still marked running with no sign of life for 90 s is stopped at its last heartbeat (`settle_stale_timers`) and every skill's hours are worked out again. Leaving a skill for another stops its running timer at its last heartbeat.
- **Profile notes** (`profile_note`): learned by counting, learned by the model from a finished session, or written by the learner. Counted notes: a lever that moved the learner to "just right" (only if it worked more often than it failed), a kind of task that feels too easy or too hard (two or more ratings, at least two thirds the same), and the task length that feels right (median of three or more "just right" tasks). They are rewritten as the evidence changes and dropped when it is gone.
- **The learner has the last word.** Editing a note makes it theirs: automatic updates never overwrite it, and it stays even when its evidence goes. Removing a learned note keeps a marker so it is not learned again; a note the learner wrote is simply deleted. On one topic (explanation length, examples versus rules, pacing, and so on) the learner's note wins, otherwise the newest.
- **Model-written notes** come from one call after a skill is finished (run after the reply, in the background; failure only means no new notes). At most three; each must be short (25 words), on a known topic, backed by evidence, and not about passing, the checklist, skipping or lowering the bar. The prompt tells the model not to repeat what counting already covers (v2, after a real run where it did).
- **Every teaching prompt gets the profile**, fenced as data and bounded: at most 12 notes and 1,600 characters, the learner's own first, one per topic, plus a few counted facts about the current skill (mistakes seen at least twice, concepts confused). With nothing learned it says "(nothing learned yet)". The persona says notes shape pacing, examples and tone and never what it takes to pass.
- **Progress** shows hours per skill with a bar capped at 20 hours (and "N past the target" in words), skills passed, "just right" ratings, reviews answered right (zero until TASKS_010 records review results), recurring mistakes (fixed when the skill's latest feedback no longer has them) and the flow history. Status is always a word.
- **Real model check** (your server): from the counted facts of a made-up session the model wrote three notes in 8.8 s, all within the rules, but two repeated counted notes; that led to the v2 prompt line.

## D-020 Spaced review, Continue and the Concepts screen (2026-11-03)

- **Schedule (SM-2 style, `ai_tutor/review.py`).** A right answer pushes the item out: 3 days, then 7, then the last interval times its ease (ease +0.05, at most 3.0). A miss brings it back tomorrow and lowers the ease by 0.2 (at least 1.3). The first answer to a question is the one that counts: right after a hint is still recorded as a miss, and "Show answer" is a miss. A second wrong answer shows the answer with its citation. The ease and interval numbers are guesses to adjust from use.
- **Items.** Passing a skill creates one question about its principles ("name the principles") and one per concept; checking a concept to Spot in a session creates its item too. A concept has one item however many skills use it, so concepts come back mixed across skills. All first reviews are due a day later. Passing again resets the skill's item instead of adding another. A skill's own question is asked only while the skill is passed; a concept's question is asked whatever its skill is doing.
- **Which questions.** Weight = past mistakes on the concept or skill (up to 3, twice each) + misses in review (up to 3) + shaky concept (confused with something, or below Spot) + days overdue (up to 5). The pick is mixed: after a skill question comes a concept question and the other way round whenever both are due; within a kind, a different skill is preferred. Two open sittings never share a question.
- **Continue.** If anything is due and no Continue review ended in the last 4 hours, Continue opens two questions, then the session at the exact saved phase (the review never touches the session). If an earlier Continue review is still open it is resumed, also after closing the app (a sitting is stored). With nothing due Continue goes straight to the session. The 4-hour rest stops Continue from asking two more every time while many items are due; Review mode has no such limit. Home shows "Review" with a count and a start button beside Continue.
- **Review mode.** Up to 8 questions per sitting; "End review" keeps what was answered and leaves the rest due. The summary says what was right or missed, when each comes back, and notes about skills and concepts that moved.
- **What a result does.** Concept right: the level rises to the level asked (never lowered by a right answer). Concept missed: it drops to the level below the missed one, at most Define after a missed Spot and at most Spot after a missed Use. A missed Define keeps the level, because there is nothing secure below it to drop to. A skill's own question missed twice in a row sends the skill back to "needs practice", where the picker offers it again. Only the learner's answers change anything; the model judges meaning.
- **3-minute concept check** (Concepts screen): Define, then Spot, then Use, one question each, stopping at the first miss. Questions are the stored ones, else made when reached (a Spot example in the project's setting; a Use question from a new prompt, `concept_use`), so a missed Define pays for nothing more. A concept checked this way also gets a review item. This is the one place that sets Use: it comes from a correct Use answer, not from practice feedback alone.
- **Model remarks carry no citations.** Anything bracketed or cited in the model's feedback or hint is removed; the app attaches the real citations from the concept's or the skill's own passages. The model's feedback after a wrong answer can still name too much of the answer; the prompt asks it not to.
- **Real model check** (your server, made-up book): Define judged in 2.5–6.7 s; a Spot question was made in the project's setting; skill review judged a good answer right in 2.2 s. Not tried with real data of a whole skill pass.

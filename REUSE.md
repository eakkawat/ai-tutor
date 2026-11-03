# REUSE.md

Reuse audit (SPEC §11, step 0). Source apps were read on 2026-11-03.

- **Book-learning app:** `/home/eakkawat/projects/python/book-to-skills` (Python 3.12, FastAPI, SQLite + sqlite-vec, PyMuPDF, React + TS + Vite). Written `B2S` below.
- **Chapter splitter:** `/home/eakkawat/projects/python/separate_pdf_chapter` (FastAPI + PyMuPDF, outputs one PDF per chapter). The older `separate_book_chapters` splits markdown/txt and is not relevant.

Rules: copy code in (no runtime dependency), keep the source path in a comment at the top of each copied file, and adapt names and imports.

## Decision on stack

B2S's stack fits and the reusable part is substantial (ingest, chunking, DB layer, LLM client, UI shell). Per SPEC §11 we **match B2S's stack** instead of the CLAUDE.md default: Python 3.12 + FastAPI + SQLite/sqlite-vec + PyMuPDF, React + TypeScript + Vite + TanStack Query. Styling is plain CSS with the AI Tutor tokens, not Tailwind. See `DECISIONS.md` D-001.

## Candidates

| Candidate | Where in B2S | Reuse as-is / adapt / skip | Why |
| --- | --- | --- | --- |
| PDF facts (pages, metadata, bookmarks, has-text check, blank-page check) | `book_to_skills/ingest/pdfinfo.py` | Reuse as-is | Never raises, gives `has_text` for the "needs OCR" flag (B1). |
| Front matter finder (TOC, preface, introduction ranges) | `ingest/front_matter.py`, `ingest/roles.py` | Reuse as-is | Exactly what triage needs (SPEC §5.1 step 3). |
| Group chapter PDFs into one book | `ingest/grouping.py`, `ingest/inbox.py`, `splitting.py` | Adapt | Same need (chapter PDFs from the splitter under one book). Drop the watch-folder and inbox states we do not need; keep grouping and duplicate detection. |
| Watch folder | `ingest/watcher.py` | Skip (v1) | Not in the user stories. Upload by file picker only. Revisit if wanted (IDEAS.md). |
| Chunking by chapter/section with pages | `pipeline/chunking.py` | Adapt | Already chunks by book structure and keeps pages. Change: store chunk text in SQLite `Chunk` rows (SPEC §9) with `chapter`, `page_start`, `page_end`, not in files under `_books/`. |
| Embeddings (EmbeddingGemma through sentence-transformers) | `llm/embeddings.py` | Adapt | Local embeddings are preferred (SPEC §10). Keep the lazy load, idle unload and the float32 rule. Change: embed chunks and concepts, not only skills; keep the `Embedder` protocol so tests use a fake. Needs `uv sync --extra embed` (torch, about 2 GB). |
| LLM client (JSON validated by Pydantic, retry once with the error, call log) | `llm/client.py`, `llm/errors.py` | Adapt | Keep the JSON-and-retry logic. It already talks to an OpenAI-compatible server, so the backend carries over. Add image input (`image_url` parts) for submissions. |
| LLM backends | `llm/backends.py` | Adapt | Same OpenAI-compatible interface. Add vision messages; the setup screen supplies base URL, model and optional key. |
| Triage prompts and logic | `pipeline/triage.py`, `triage_schema.py`, `prompts/triage_front_matter.md`, `triage_samples.md` | Adapt | Same idea (read front matter, then sample). Change output to book type, likely skills, practicable yes/no (SPEC §5.1). Skip `triage_web.md`: web search is outside our non-goals. |
| Skill mining and drafting | `pipeline/mining.py`, `clustering.py`, `drafting.py`, `prompts/mine_rules.md`, `draft_skill.md` | Skip, rewrite | Those produce SKILL.md files for an AI. We need skills phrased as practicable tasks with a principle checklist (SPEC §11). Reuse only the prompt-file layout and the validation pattern. |
| Skill matching and merge | `pipeline/matching.py`, `merging.py`, `prompts/match_skill.md`, `merge_integrate.md` | Adapt (P1) | Embedding picks candidates, the model decides. Needed for B5. Change the unit (a practice skill with principles) and show a diff. |
| Auto vs manual review mode | `components/AutoMode.tsx`, `pipeline/decision.py`, `thresholds.py` | Adapt | The mode switch is the same. Our version is simpler: auto accepts, manual asks (B4). |
| Eval gate, library repo, SKILL.md export, git commits | `evals/`, `skill_library.py`, `skillmd.py`, `export.py`, `skill_sync.py`, `links.py`, `digest.py`, `health.py` | Skip | AI-skill concerns that have no meaning here. |
| Job runner (resumable stages in SQLite) | `pipeline/runner.py` | Adapt | Needed for upload → chunk → embed → triage → skills with progress and cancel. |
| DB connection and migration runner | `store/conn.py` | Reuse as-is | WAL, foreign keys, sqlite-vec loaded, ordered `NNNN_name.sql` files. |
| Repos pattern | `store/repos.py` | Adapt | Keep the style; the tables are different (SPEC §9). |
| Schema migrations | `store/migrations/*.sql` | Skip, rewrite | Our schema is SPEC §9. Borrow the `source`/`chunk` shapes only. |
| Settings saved by the setup screen (secrets file mode 600) | `app_settings.py`, `config.py` | Adapt | Good fit for the API key (A1). Change fields to API key, data dir, media flags; home dir `~/.config/ai-tutor`. |
| Setup page | `web/src/pages/Setup.tsx`, `Setup.test.tsx` | Adapt | Basis for the dependency check screen. |
| Frontend shell: router, sidebar, query client, toast, API helper | `web/src/App.tsx`, `api.ts`, `components/Toast.tsx`, `styles.css` | Adapt | Same stack. Replace tokens with `docs/DESIGN_SYSTEM.md` values (their palette differs). |
| Logging setup | `logging_setup.py` | Reuse as-is | Local file logging; make sure no network sink. |
| Makefile | `Makefile` | Adapt | `setup`, `test`, `dev`, `web`, `start`. |
| Chapter splitter: TOC/regex chapter detection | `separate_pdf_chapter/pdf_processor.py` | Skip | Its job (splitting) stays in that app. We only consume its output via the grouping code above. |
| Chapter splitter: AI fix, slug naming | `ai_slicer.py` | Skip | Not needed. Filenames like `07_Chapter_One_...pdf` are parsed by `ingest/roles.py` `split_filename`. |
| OCR | optional `docling` extra | Skip (v1) | Scanned PDFs are only flagged "needs OCR" (B1). |

## Not available in B2S, must build new

- Vision (image) messages on the OpenAI-compatible backend
- Dependency check for ffmpeg, ffprobe, faster-whisper and the LLM server (A1)
- Hybrid search (FTS5 + vectors) and citation validator
- Everything in the teaching engine: sessions, concepts, feedback, flow, review, profile
- Video processing (ffmpeg keyframes and cuts, Whisper)

## Things to check before copying

- B2S uses Python 3.12 through `uv`; system Python here is 3.10. `uv` must be installed.
- B2S's embedding model name (`google/embeddinggemma-2`) and prompt names (`SearchQuery`, `STS`) come from its own measurements in its `DECISIONS.md`; re-check before relying on them.

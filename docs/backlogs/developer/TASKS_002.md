# TASKS-002: Library Upload, Chunking and Embedding

**User Story:** B1 (Upload a book), B2 (Triage), B6 (Open a source passage)
**User Flow:** Flow 2 - Add a book, up to triage (SPEC §5.1, §7, §12 step 1)
**Priority:** P0 (MVP)

---

## Prerequisites

### Ingestion pipeline

**Question to ask:** "How does a PDF become searchable, citable chunks?"

- [x] Reuse or write PDF text extraction that keeps page numbers (per REUSE.md)
- [x] Chapter detection from the PDF table of contents
- [x] Chunker that never crosses chapters; stores `chapter`, `page_start`, `page_end`
- [x] Choose embedding model (local preferred); wrap behind an `embed(texts)` interface
- [x] Store embeddings in `sqlite-vec`; add keyword index (FTS5) for hybrid search
- [x] Background job runner with status per source: extracting, chunking, triage, skills

### LLM client

- [x] OpenAI-compatible LLM client (adapt B2S `llm/client.py`) with retry, timeout and token logging
- [x] Prompt loader reading from `prompts/`
- [x] Helper to fence book text as data in prompts

---

## STEP 1: Choose a Book

**Question to ask:** "What can the user upload and how is it grouped?"

- [x] Library screen (`design/Library.dc.html`) with Add book action
- [x] File picker for a single PDF or several chapter PDFs
- [x] Group chapter PDFs from the chapter-splitter app under one Source
- [x] Ask for title and author (optional fields; read from the PDF metadata when empty)
- [x] Copy file to `data/library/`
- [x] Hash the file; detect duplicates and offer to skip

## STEP 2: Extract Text and Pages

**Question to ask:** "What if there is no text layer?"

- [x] Run extraction; save per-page text
- [x] If no text found: set status `needs_ocr`, show flag, stop (no silent failure)
- [x] Show estimated processing time for large books; allow cancel

## STEP 3: Chunk and Embed

- [x] Chunk and store `Chunk` rows
- [x] Embed chunks in batches; resume if interrupted
- [x] Progress UI: extracting → chunking → triage → skills (`design/Library.dc.html` processing state)

## STEP 4: Triage (B2)

**Question to ask:** "Is this book worth teaching from?"

- [x] Write `prompts/triage.md` (TOC + preface in, JSON out: book type, likely skills, practicable yes/no)
- [x] Validate JSON output; store in `Source.triage_json`
- [x] Show triage card per book
- [x] "No practicable skills": mark as reference only, still citable

## STEP 5: Retrieval and Passage Viewer (B6)

**Question to ask:** "How do we fetch grounded chunks and show them?"

- [x] Hybrid search function: keyword + embedding, filter to a skill's linked sources first
- [x] Source passage viewer (`design/Source.dc.html`): passage, page, highlighted chunk
- [x] Citation component `[Book, ch. X, p. Y]` that opens the viewer
- [x] Citation validator: every citation must match a retrieved chunk ID; strip or flag others

---

## Edge Cases

- [x] Very large book: time estimate, cancel
- [x] Duplicate upload: skip offer
- [x] Mixed text and scanned pages: flag affected page range
- [x] Failed embedding batch: mark source `error` with reason; the Retry button resumes (no automatic retry)

## Testing

- [x] Fixture PDF (made-up placeholder content, `[Book A]`) with known page numbers
- [x] Test page/chapter metadata on chunks
- [x] Test hybrid search ranks linked-source chunks first
- [x] Test citation validator strips unknown citations
- [x] Acceptance: upload produces chunks each tied to a page range

---

## Task Summary

| Category      | Tasks  | Status |
| ------------- | ------ | ------ |
| Prerequisites | 9     | Done   |
| Step 1-5      | 20     | Done   |
| Edge Cases    | 4      | Done   |
| Testing       | 5      | Done   |
| **Total**     | **38** | **38/38 done** |

---

**Task List Version:** 1.1
**Created:** 2026-11-03

-- TASKS_002: library ingestion, chunks, search, LLM call log.

ALTER TABLE source ADD COLUMN kind TEXT NOT NULL DEFAULT 'single';        -- single | chapters
ALTER TABLE source ADD COLUMN pages INTEGER NOT NULL DEFAULT 0;
ALTER TABLE source ADD COLUMN stage TEXT;                                 -- extracting | chunking | embedding | triage
ALTER TABLE source ADD COLUMN progress REAL NOT NULL DEFAULT 0;           -- 0..1 within the whole pipeline
ALTER TABLE source ADD COLUMN message TEXT;                               -- last status or error text, shown to the user
ALTER TABLE source ADD COLUMN detected_json TEXT;                         -- front matter page ranges {role: [first, last]}
ALTER TABLE source ADD COLUMN estimate_s INTEGER;
CREATE UNIQUE INDEX source_hash ON source(file_hash) WHERE file_hash IS NOT NULL;

CREATE TABLE source_file (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES source(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  path TEXT NOT NULL,
  order_idx INTEGER NOT NULL DEFAULT 0,
  role TEXT NOT NULL DEFAULT 'chapter',       -- toc | preface | introduction | chapter | appendix | index | bibliography | other
  role_number INTEGER,
  pages INTEGER NOT NULL DEFAULT 0,
  include INTEGER NOT NULL DEFAULT 1,
  note TEXT                                   -- blank | needs_ocr | unreadable
);
CREATE INDEX source_file_source ON source_file(source_id);

ALTER TABLE chunk ADD COLUMN source_file_id INTEGER REFERENCES source_file(id) ON DELETE CASCADE;
ALTER TABLE chunk ADD COLUMN title TEXT;        -- chapter or section title
ALTER TABLE chunk ADD COLUMN label TEXT;        -- "Ch. 3" or the title when the unit has no number
ALTER TABLE chunk ADD COLUMN ord INTEGER NOT NULL DEFAULT 0;

-- Keyword index for hybrid search.
CREATE VIRTUAL TABLE chunk_fts USING fts5(text, content='chunk', content_rowid='id');
CREATE TRIGGER chunk_ai AFTER INSERT ON chunk BEGIN INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.text); END;
CREATE TRIGGER chunk_ad AFTER DELETE ON chunk BEGIN INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.text); END;
CREATE TRIGGER chunk_au AFTER UPDATE OF text ON chunk BEGIN
  INSERT INTO chunk_fts(chunk_fts, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO chunk_fts(rowid, text) VALUES (new.id, new.text);
END;

-- Embeddings: EmbeddingGemma gives 768 numbers. rowid = chunk.id. Rows are removed by code when a chunk is deleted.
CREATE VIRTUAL TABLE chunk_vec USING vec0(embedding float[768]);

CREATE TABLE llm_call (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL DEFAULT (datetime('now')),
  job TEXT NOT NULL,
  model TEXT,
  prompt_version TEXT,
  source_id INTEGER,
  ok INTEGER NOT NULL,
  error TEXT,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  seconds REAL,
  raw_response TEXT
);

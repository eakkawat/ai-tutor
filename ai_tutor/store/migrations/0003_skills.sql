-- TASKS_003: skills proposed from books, review state, merge proposals, resumable extraction.

ALTER TABLE skill ADD COLUMN status TEXT NOT NULL DEFAULT 'active';          -- active | pending (waiting for review) | archived
ALTER TABLE skill ADD COLUMN source_id INTEGER REFERENCES source(id) ON DELETE SET NULL;   -- the book it was first found in
ALTER TABLE skill ADD COLUMN merge_into INTEGER REFERENCES skill(id) ON DELETE CASCADE;    -- a pending skill that matches an existing one
ALTER TABLE skill ADD COLUMN merge_note TEXT;                                -- why the model thinks they are the same
ALTER TABLE skill ADD COLUMN unit_label TEXT;                                -- chapter it came from
CREATE INDEX skill_status ON skill(status);

-- A chapter whose skills have been extracted. A retry skips these.
CREATE TABLE extraction_done (
  source_id INTEGER NOT NULL REFERENCES source(id) ON DELETE CASCADE,
  unit_label TEXT NOT NULL,
  PRIMARY KEY (source_id, unit_label)
);

-- Chunking is all-or-nothing: once a book is chunked, skills and concepts may cite its passages, so a retry must not rebuild them.
ALTER TABLE source ADD COLUMN chunked INTEGER NOT NULL DEFAULT 0;
UPDATE source SET chunked = 1 WHERE id IN (SELECT DISTINCT source_id FROM chunk);

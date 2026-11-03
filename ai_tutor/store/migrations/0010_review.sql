-- TASKS_010: spaced review. The schedule (SM-2 style) lives on the item; a run is one sitting of questions that survives closing the app.

ALTER TABLE review_item ADD COLUMN interval_days REAL NOT NULL DEFAULT 0;
ALTER TABLE review_item ADD COLUMN reps INTEGER NOT NULL DEFAULT 0;            -- right answers in a row
ALTER TABLE review_item ADD COLUMN misses INTEGER NOT NULL DEFAULT 0;          -- wrong answers, ever

CREATE TABLE review_run (
  id INTEGER PRIMARY KEY,
  mode TEXT NOT NULL CHECK (mode IN ('continue','review','concept')),
  session_id INTEGER REFERENCES session(id) ON DELETE SET NULL,    -- where Continue goes afterwards
  concept_id INTEGER REFERENCES concept(id) ON DELETE CASCADE,     -- for a 3-minute concept check
  questions_json TEXT NOT NULL,
  idx INTEGER NOT NULL DEFAULT 0,
  state_json TEXT,                                                 -- the open question: attempts, hint, whether the answer was shown
  results_json TEXT NOT NULL DEFAULT '[]',
  started_at TEXT NOT NULL,
  ended_at TEXT
);

CREATE TABLE review_result (
  id INTEGER PRIMARY KEY,
  run_id INTEGER REFERENCES review_run(id) ON DELETE SET NULL,
  item_id INTEGER REFERENCES review_item(id) ON DELETE SET NULL,
  skill_id INTEGER REFERENCES skill(id) ON DELETE CASCADE,
  concept_id INTEGER REFERENCES concept(id) ON DELETE CASCADE,
  level TEXT,
  result TEXT NOT NULL CHECK (result IN ('right','wrong')),
  at TEXT NOT NULL
);
CREATE INDEX review_result_skill ON review_result(skill_id, id);

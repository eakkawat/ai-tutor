-- Schema from SPEC §9. Timestamps are ISO text. JSON columns hold JSON text.
-- Chunk embeddings go in a sqlite-vec virtual table that TASKS_002 adds once the embedding size is fixed.

CREATE TABLE source (
  id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT,
  type TEXT NOT NULL DEFAULT 'book',
  file_path TEXT,
  file_hash TEXT,
  status TEXT NOT NULL DEFAULT 'new',   -- new | processing | needs_ocr | reference_only | ready | error
  triage_json TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE chunk (
  id INTEGER PRIMARY KEY,
  source_id INTEGER NOT NULL REFERENCES source(id) ON DELETE CASCADE,
  chapter TEXT,
  page_start INTEGER,
  page_end INTEGER,
  text TEXT NOT NULL
);
CREATE INDEX chunk_source ON chunk(source_id);

CREATE TABLE skill (
  id INTEGER PRIMARY KEY,
  domain TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  practice_type TEXT,
  difficulty_default INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE skill_principle (
  id INTEGER PRIMARY KEY,
  skill_id INTEGER NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
  principle TEXT NOT NULL,
  test TEXT NOT NULL,
  chunk_id INTEGER NOT NULL REFERENCES chunk(id),
  "order" INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE skill_source (
  skill_id INTEGER NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
  chunk_id INTEGER NOT NULL REFERENCES chunk(id),
  PRIMARY KEY (skill_id, chunk_id)
);

CREATE TABLE skill_prereq (
  skill_id INTEGER NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
  prereq_skill_id INTEGER NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
  PRIMARY KEY (skill_id, prereq_skill_id)
);

CREATE TABLE concept (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  definition TEXT NOT NULL,
  example TEXT NOT NULL,
  is_foundation INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE concept_source (
  concept_id INTEGER NOT NULL REFERENCES concept(id) ON DELETE CASCADE,
  chunk_id INTEGER NOT NULL REFERENCES chunk(id),
  PRIMARY KEY (concept_id, chunk_id)
);

CREATE TABLE skill_concept (
  skill_id INTEGER NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
  concept_id INTEGER NOT NULL REFERENCES concept(id) ON DELETE CASCADE,
  required_level TEXT NOT NULL DEFAULT 'spot' CHECK (required_level IN ('spot','use')),
  PRIMARY KEY (skill_id, concept_id)
);

CREATE TABLE concept_mastery (
  concept_id INTEGER PRIMARY KEY REFERENCES concept(id) ON DELETE CASCADE,
  level TEXT NOT NULL DEFAULT 'none' CHECK (level IN ('none','define','spot','use')),
  last_checked_at TEXT,
  confusions_json TEXT
);

CREATE TABLE concept_question (
  id INTEGER PRIMARY KEY,
  concept_id INTEGER NOT NULL REFERENCES concept(id) ON DELETE CASCADE,
  level TEXT NOT NULL CHECK (level IN ('define','spot','use')),
  prompt TEXT NOT NULL,
  answer_key TEXT NOT NULL,
  asset_ref TEXT
);

CREATE TABLE project (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  good_enough TEXT NOT NULL,
  minutes_per_session INTEGER NOT NULL DEFAULT 25,
  active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE learner_skill (
  skill_id INTEGER PRIMARY KEY REFERENCES skill(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'not_started',  -- not_started | active | paused | passed | needs_practice
  level INTEGER NOT NULL DEFAULT 0,
  difficulty_current INTEGER NOT NULL DEFAULT 3,
  hours_total REAL NOT NULL DEFAULT 0,
  last_session_at TEXT
);

CREATE TABLE session (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES project(id),
  skill_id INTEGER NOT NULL REFERENCES skill(id),
  started_at TEXT NOT NULL DEFAULT (datetime('now')),
  ended_at TEXT,
  phase TEXT NOT NULL DEFAULT 'diagnose',
  minutes REAL NOT NULL DEFAULT 0
);

CREATE TABLE message (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('tutor','user')),
  content TEXT NOT NULL,
  citations_json TEXT,
  phase TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE submission (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
  version INTEGER NOT NULL DEFAULT 1,
  text TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE submission_asset (
  id INTEGER PRIMARY KEY,
  submission_id INTEGER NOT NULL REFERENCES submission(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('image','video')),
  file_path TEXT NOT NULL,
  duration_s REAL,
  processed_json TEXT
);

CREATE TABLE video_frame (
  id INTEGER PRIMARY KEY,
  asset_id INTEGER NOT NULL REFERENCES submission_asset(id) ON DELETE CASCADE,
  timestamp_s REAL NOT NULL,
  file_path TEXT NOT NULL
);

CREATE TABLE feedback (
  id INTEGER PRIMARY KEY,
  submission_id INTEGER NOT NULL REFERENCES submission(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  mistakes_json TEXT,
  passed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE principle_check (
  id INTEGER PRIMARY KEY,
  feedback_id INTEGER NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
  principle_id INTEGER NOT NULL REFERENCES skill_principle(id),
  result TEXT NOT NULL CHECK (result IN ('followed','partly','not')),
  evidence_ref TEXT,
  comment TEXT
);

CREATE TABLE flow_rating (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
  task_ref TEXT,
  self_rating TEXT CHECK (self_rating IN ('too_easy','just_right','too_hard')),
  accuracy REAL,
  time_ratio REAL,
  classification TEXT,
  lever_changed TEXT
);

CREATE TABLE mistake (
  id INTEGER PRIMARY KEY,
  skill_id INTEGER NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
  concept_id INTEGER REFERENCES concept(id),
  kind TEXT NOT NULL CHECK (kind IN ('concept','execution')),
  tag TEXT NOT NULL,
  principle_chunk_id INTEGER REFERENCES chunk(id),
  count INTEGER NOT NULL DEFAULT 1,
  last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE profile_note (
  id INTEGER PRIMARY KEY,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE review_item (
  id INTEGER PRIMARY KEY,
  skill_id INTEGER REFERENCES skill(id) ON DELETE CASCADE,
  concept_id INTEGER REFERENCES concept(id) ON DELETE CASCADE,
  level TEXT,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  due_at TEXT NOT NULL,
  ease REAL NOT NULL DEFAULT 2.5,
  last_result TEXT
);
CREATE INDEX review_due ON review_item(due_at);

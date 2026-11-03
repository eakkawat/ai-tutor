-- TASKS_007: images and video clips attached to practice work.
-- An attachment is uploaded while the learner is still working, before the submission exists, so `submission_id` becomes optional and
-- the asset belongs to the session. SQLite cannot drop NOT NULL in place, so the table is rebuilt.

PRAGMA foreign_keys = OFF;

CREATE TABLE submission_asset_new (
  id INTEGER PRIMARY KEY,
  session_id INTEGER NOT NULL REFERENCES session(id) ON DELETE CASCADE,
  submission_id INTEGER REFERENCES submission(id) ON DELETE CASCADE,       -- NULL until the work is submitted
  kind TEXT NOT NULL CHECK (kind IN ('image','video')),
  filename TEXT NOT NULL DEFAULT '',
  file_path TEXT NOT NULL,
  mime TEXT,
  size_bytes INTEGER NOT NULL DEFAULT 0,
  duration_s REAL,
  status TEXT NOT NULL DEFAULT 'ready' CHECK (status IN ('processing','ready','error')),
  error TEXT,
  processed_json TEXT,                                                     -- images: size and file names; video: steps, cuts, frames, transcript
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO submission_asset_new(id, session_id, submission_id, kind, file_path, duration_s, processed_json)
  SELECT a.id, s.session_id, a.submission_id, a.kind, a.file_path, a.duration_s, a.processed_json
  FROM submission_asset a JOIN submission s ON s.id = a.submission_id;
DROP TABLE submission_asset;
ALTER TABLE submission_asset_new RENAME TO submission_asset;
CREATE INDEX asset_session ON submission_asset(session_id, submission_id);

PRAGMA foreign_keys = ON;

ALTER TABLE video_frame ADD COLUMN idx INTEGER NOT NULL DEFAULT 0;         -- 1-based frame number within the clip
ALTER TABLE video_frame ADD COLUMN is_cut INTEGER NOT NULL DEFAULT 0;      -- 1 if the frame was picked because the shot changes there
CREATE INDEX frame_asset ON video_frame(asset_id, idx);

-- TASKS_005: the teaching session. Everything the screen needs to be restored exactly after a restart lives in these rows.

ALTER TABLE session ADD COLUMN task_json TEXT;                                   -- the practice task being worked on
ALTER TABLE session ADD COLUMN draft_text TEXT NOT NULL DEFAULT '';              -- unsent work, saved as the learner types
ALTER TABLE session ADD COLUMN attempt INTEGER NOT NULL DEFAULT 0;               -- submissions made so far
ALTER TABLE session ADD COLUMN timer_limit_s INTEGER NOT NULL DEFAULT 0;
ALTER TABLE session ADD COLUMN timer_elapsed_s REAL NOT NULL DEFAULT 0;          -- time on the current task before the last start
ALTER TABLE session ADD COLUMN timer_since TEXT;                                 -- UTC ISO time the timer last started; NULL while paused
ALTER TABLE session ADD COLUMN timer_seen TEXT;                                  -- last sign of life from the screen (heartbeat)
ALTER TABLE session ADD COLUMN overtime_s REAL NOT NULL DEFAULT 0;               -- time over the limit, summed over submitted tasks
ALTER TABLE session ADD COLUMN diagnosis_json TEXT;                              -- {can_do, gap, level, meets_all}

ALTER TABLE message ADD COLUMN kind TEXT;                                        -- diagnose_task | answer | diagnosis | learn | note | submission | qa | ...
ALTER TABLE message ADD COLUMN meta_json TEXT;

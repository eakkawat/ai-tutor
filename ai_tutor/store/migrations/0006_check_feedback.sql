-- TASKS_006: the foundations check state, and what feedback needs to remember.

ALTER TABLE session ADD COLUMN check_json TEXT;                        -- the question being asked, wrong answers so far, questions asked this sitting
ALTER TABLE principle_check ADD COLUMN locator TEXT;                   -- "Line 2", "Lines 4–6" (image regions and timestamps come with TASKS_007)
CREATE INDEX mistake_lookup ON mistake(skill_id, kind, tag);

-- TASKS_008: flow calibration. Which supports and constraints are on for each skill, and every rating with the reasoning behind the change.

ALTER TABLE learner_skill ADD COLUMN levers_json TEXT;                 -- {"supports": [...], "constraints": [...], "combine_with": null}; NULL = the default for level 3

ALTER TABLE flow_rating ADD COLUMN skill_id INTEGER REFERENCES skill(id) ON DELETE CASCADE;
ALTER TABLE flow_rating ADD COLUMN feedback_id INTEGER REFERENCES feedback(id) ON DELETE CASCADE;
ALTER TABLE flow_rating ADD COLUMN attempt INTEGER;                    -- which attempt this rating followed
ALTER TABLE flow_rating ADD COLUMN rating_used TEXT;                   -- the rating that drove the decision (the tap, or the one inferred from the work)
ALTER TABLE flow_rating ADD COLUMN inferred INTEGER NOT NULL DEFAULT 0;
ALTER TABLE flow_rating ADD COLUMN difficulty_before INTEGER;
ALTER TABLE flow_rating ADD COLUMN difficulty_after INTEGER;
ALTER TABLE flow_rating ADD COLUMN message TEXT;                       -- the one line shown to the learner
ALTER TABLE flow_rating ADD COLUMN signals_json TEXT;
ALTER TABLE flow_rating ADD COLUMN created_at TEXT NOT NULL DEFAULT (datetime('now'));
CREATE UNIQUE INDEX flow_one_per_feedback ON flow_rating(feedback_id) WHERE feedback_id IS NOT NULL;
CREATE INDEX flow_skill ON flow_rating(skill_id, id);

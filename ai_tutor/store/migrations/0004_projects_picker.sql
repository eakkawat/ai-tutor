-- TASKS_004: one active skill and one active project, enforced by the database.

CREATE UNIQUE INDEX one_active_skill ON learner_skill(status) WHERE status = 'active';
CREATE UNIQUE INDEX one_active_project ON project(active) WHERE active = 1;
CREATE INDEX session_open ON session(skill_id) WHERE ended_at IS NULL;

-- TASKS_009: the learner profile. Notes the app learns, notes the learner writes, and what the learner changed or removed.

ALTER TABLE profile_note ADD COLUMN section TEXT NOT NULL DEFAULT 'understand';      -- understand | flow
ALTER TABLE profile_note ADD COLUMN topic TEXT;                                       -- notes on the same topic conflict: an edited one wins, else the newest
ALTER TABLE profile_note ADD COLUMN source TEXT NOT NULL DEFAULT 'auto';              -- auto | user
ALTER TABLE profile_note ADD COLUMN evidence TEXT;                                    -- "Learned from 4 recall checks"
ALTER TABLE profile_note ADD COLUMN edited INTEGER NOT NULL DEFAULT 0;                -- the learner changed the wording: automatic updates leave it alone
ALTER TABLE profile_note ADD COLUMN removed INTEGER NOT NULL DEFAULT 0;               -- the learner removed it: kept as a marker so it is not learned again
CREATE UNIQUE INDEX profile_note_key ON profile_note(key);

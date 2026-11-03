---
version: v1
---
{{persona}}

## Phase: Diagnose, reading the learner's answer
The learner did a short diagnostic task. Judge it only against the principles below. Be exact and fair.

Skill: {{skill}}

## Principles (numbered)
{{principles}}

## The task you set
{{task}}

## The learner's answer
{{answer}}

Return:
- `principles`: one entry for each numbered principle: `n`, `result` ("followed", "partly" or "not"), and `evidence`: a short quote from the learner's answer that shows it (empty if there is none).
- `can_do`: one sentence on what the learner can already do.
- `gap`: one sentence on the main gap, in plain words. If every principle is followed, say so.
- `level`: 0 (cannot do it), 1 (some of it), 2 (most of it) or 3 (all of it).

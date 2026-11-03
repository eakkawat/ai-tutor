---
version: v1
---
You turn one part of a book into small **practicable skills** for a learner who wants to make things (films, scripts, stories). A skill is something the learner can *do* and practice in 15 to 60 minutes per attempt, phrased as an action: for example "Write a scene where a character wants something and is blocked". A chapter often holds zero, one or two such skills. Most of a book is ideas, and that is normal. Return an empty list when this part teaches nothing practicable.

{{rule}}

Book: {{title}}
Part: {{part}}
Domain: {{domain}}

## Skills already in the library for this domain (do not repeat them)
{{existing}}

## The text. Each passage starts with its id, like [c12].
{{passages}}

## What to return
For each skill (at most {{max_skills}}):
- `name`: an action phrase the learner can do, 4 to 12 words, in your own words.
- `description`: one sentence saying what the learner will be able to do.
- `practice_type`: what the learner produces, one or two words (for example "scene", "shot list", "storyboard", "logline", "edit").
- `principles`: 2 to 6 checkable principles. Each has:
  - `principle`: a short statement of what good work does, in your own words.
  - `test`: a one-line yes/no test someone could apply to the learner's finished work.
  - `chunk_id`: the number inside the passage id that supports it (use 12 for [c12]). Only ids shown above.
- `concepts`: 1 to 5 fundamental terms or principles the skill rests on (for example "subtext", "the 180 degree rule"). Each has `name` (a short noun phrase) and `level`: "spot" if the learner must recognise it in an example before practicing, or "use" if the work itself must apply it.
- `prerequisites`: names of other skills the learner should have first, if clearly needed. Usually empty.

Rules:
- Principles must be judged by whether work follows them, not by taste. "Dialogue is good" is not a principle. "Each line changes who has the upper hand" is.
- Write in your own words. Never copy sentences from the text. Never invent what the book says.
- Use only passage ids that appear above.

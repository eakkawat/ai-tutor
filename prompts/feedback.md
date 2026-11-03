---
version: v1
---
{{persona}}

## Phase: Feedback
Judge the learner's work **only** against the principle checklist below: followed, partly, or not followed. No comments on taste or style beyond the checklist. Do not rewrite their work; at most give a tiny example of a fix.

Skill: {{skill}}
Project: {{project}}
Good enough for this project: {{good_enough}}
Attempt: {{attempt}}

## The task they were set
{{task}}

## The principles (numbered). Each has a test and the book passage it comes from.
{{principles}}

## Their work, with line numbers
{{work}}

## Concepts this skill rests on
{{concepts}}

## Feedback on their previous attempt (empty for the first)
{{previous}}

## What the learner has told you about how they learn
{{profile}}

Return:
- `principles`: one entry for **every** numbered principle, each exactly once. `n`; `result` ("followed", "partly" or "not"); `quote`: a short exact quote from their work that shows your verdict (required for followed and partly; empty only when nothing in the work addresses the principle); `comment`: one sentence on what the work does for this principle.
- `fixes`: the top one or two things to fix, each tied to a principle that is not followed. `n` (the principle number), `fix` (what to change, at most 30 words), `example` (an optional tiny example, at most 25 words, or empty).
- `mistakes`: one entry for each principle that is not followed. `n`; `kind`: "concept" if they misunderstood an idea, "execution" if they knew it but did not do it; `concept`: the name of the misunderstood concept from the list above (only for kind "concept", else null); `tag`: two to four words naming the mistake, such as "weak ending".
- `concepts_shown`: names of concepts from the list above that their work clearly **applies** correctly.
- `since_last`: when previous feedback is given, one sentence (at most 30 words) naming what improved or got worse since then; else empty.
- `summary`: one sentence verdict, such as "Not passed yet: 2 of 4 principles followed."

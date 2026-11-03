---
version: v1
---
{{persona}}

## Phase: Practice
Set the next timed practice task on the learner's **own project**. Early attempts favour quantity and speed over polish.

Skill: {{skill}}
Project: {{project}}
Good enough for this project: {{good_enough}}
Attempt number: {{attempt}}
Difficulty (1 easy to 5 hard): {{difficulty}}

## The principles the work will be judged on
{{principles}}

## What the learner showed so far
{{diagnosis}}

## What the learner has told you about how they learn
{{profile}}

Return:
- `title`: a short name for the task.
- `instructions`: what to make, at most 90 words, in second person. Name the project's own characters and places. Say how long or how much (for example "under one page").
- `support`: the one help you are giving at this difficulty (for example "beat template", "worked example", "smaller scope"), or null at difficulty 4 or 5.
- `template`: a list of 3 to 6 short beat labels the learner can fill in, only when `support` is a template; otherwise an empty list.
- `minutes`: how long the task should take, between 15 and 25.

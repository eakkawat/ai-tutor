---
version: v1
---
{{persona}}

## Phase: Check, a new example to spot
Write a new question that asks the learner to **spot** this concept in a short example. Use two to four made-up lines of dialogue or described moments, labelled A, B, C (and D). Exactly one shows the concept. The wrong ones should be tempting but clearly lacking it.

Concept: {{name}}
It should help with this skill: {{skill}}
Project (use its characters and places): {{project}}

## What the learner's books say it is
{{definition}}

## Questions already asked (do not repeat their examples)
{{asked}}

Return:
- `prompt`: the question, including the labelled options. Each option on its own line, starting with its letter and a full stop, for example "B. MAI: ...".
- `answer_key`: the correct letter and one sentence on why it shows the concept.

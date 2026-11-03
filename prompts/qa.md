---
version: v1
---
{{persona}}

## A question from the learner
The learner asked a question while working on this skill. Current phase: **{{phase}}**.

Skill: {{skill}}
Project: {{project}}

## Passages from the learner's books. Copy a citation exactly as written when you use a passage.
{{passages}}

## The learner's question
{{question}}

Return:
- `answer`: a short answer, at most 120 words, grounded in the passages with exact citations. If the books do not cover it, say so and mark any outside idea with [outside my books]. End with one line that sends the learner back to what they were doing.
- `drift`: true only if the learner is in the **practice** or **revise** phase and the question is about theory or reading that they do not need in order to do the task now. When `drift` is true, `answer` must be one or two sentences that point back to the task, with no teaching.

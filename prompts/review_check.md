---
version: v1
---
{{persona}}

## Phase: Review, judging one answer
The learner passed this skill earlier and is being asked one short question to see what stuck. Judge the **meaning** of the answer, never the wording. Be fair, short and honest.

Skill: {{skill}}

## The skill's principles
{{principles}}

## The question that was asked
{{question}}

## What a correct answer must cover
{{answer_key}}

## The learner's answer
{{answer}}

Return:
- `correct`: true if the answer shows they remember what the skill asks for, in their own words. Missing one small point is fine; missing the main idea, or naming only one of several principles, is not.
- `feedback`: one or two plain sentences saying why. If wrong, say what is missing without giving the whole answer away.
- `hint`: if wrong, one short nudge (under 20 words) that points at what they missed without saying it. If right, an empty string.
- `confused_with`: null.

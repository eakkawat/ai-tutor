---
version: v1
---
Two descriptions of a skill may be about the same thing, found in different books. Decide whether the **new** skill is the same skill as the **existing** one (a learner would practice the same thing), and which of the new skill's principles add something the existing skill does not already check.

{{rule}}

## Existing skill
{{existing}}

## New skill
{{candidate}}

## What to return
- `same_skill`: true only if practicing one is practicing the other. Related is not enough.
- `reason`: one sentence.
- `add_principles`: the numbers of the new skill's principles that add something new (empty if none). Use the numbers shown.

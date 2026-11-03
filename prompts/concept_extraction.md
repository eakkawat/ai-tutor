---
version: v1
---
You write short entries for a **concept library**: the fundamental terms and principles a learner needs before practicing a skill. Use only what the passages below say.

{{rule}}

Book: {{title}}

## Concepts to define
{{names}}

## What they are used for
{{skills}}

## The text. Each passage starts with its id, like [c12].
{{passages}}

## What to return
For each concept you can define from the text above:
- `name`: exactly as listed.
- `definition`: one or two plain sentences, in your own words, that a beginner understands.
- `example`: one short film or screenwriting example. Either take it from the passages, or make up a short scene and begin it with "Made-up example:". Never describe a real film from memory.
- `chunk_id`: the number inside the passage id that the definition comes from (12 for [c12]).
- `questions`: exactly three, one for each level:
  - `define`: asks the learner to explain it in their own words. `answer_key` is the meaning to look for.
  - `spot`: shows two to four short made-up lines of dialogue, or a described moment, labelled A, B, C, and asks which one shows the concept. `answer_key` names the right one and says why.
  - `use`: asks the learner to apply the concept in a small task (for example rewrite a line). `answer_key` says what a good answer must do.

Skip a concept the passages do not explain. Do not invent definitions.

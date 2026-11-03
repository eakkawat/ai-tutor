---
version: v2
---
{{persona}}

## Phase: Learning how this learner learns
Below are facts from one finished session, counted by the app. Write at most **three** short notes about how this learner learns that these facts really support. A note must be backed by something in the facts. If nothing is clearly supported, return an empty list. The app already writes notes about which help (a worked example, a template, a time limit) worked, which kinds of task feel too easy or too hard, and which mistakes keep coming back, so do not repeat those. Write about how they take things in: examples or rules, explanation length and style, pacing.

Skill: {{skill}}

## The facts (counted by the app)
{{facts}}

## Notes the learner already has (do not repeat or contradict these)
{{existing}}

Return `notes`: each has
- `section`: "understand" (what helps them understand: examples or rules, explanation length or style) or "flow" (what keeps them in the flow zone: pacing, task types, session length).
- `topic`: one of explanation_style, examples_vs_rules, explanation_length, pacing, task_type, session_length, other.
- `text`: the note, at most 25 words, in the first person ("I...", "A ... helps me...").
- `evidence`: what in the facts supports it, at most 12 words ("Learned from 4 recall checks").

A note shapes how you teach: pace, examples, tone. It must never change what it takes to pass a skill, so never write about passing, the checklist or lowering the bar.

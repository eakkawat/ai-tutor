# Design mockups

Reference mockups for every screen in `../docs/USER_STORIES_AND_FLOWS.md` Part 3. They are **design reference, not production code**. Each file is a self-contained HTML mockup in the Claude Design format: markup inside `<x-dc>`, small logic in a `DCLogic` class. Build real components from them using `../docs/DESIGN_SYSTEM.md`.

The live, editable canvas (all screens side by side): https://claude.ai/artifact/3EXAYQFey2MWe8zAnNqVq4 (private to the owner).

| File | Screen / state | Flows |
| --- | --- | --- |
| `Main.dc.html` | Session · Learn & Check | 4 |
| `Foundations.dc.html` | Session · Foundations check: spot question, practice locked (interactive) | 4, 10 |
| `Practice.dc.html` | Session · Practice & Submit (video processing, rejected clip) | 4, 5 |
| `Feedback.dc.html` | Session · Feedback & Flow rating (interactive) | 4, 5, 6 |
| `Picker.dc.html` | Skill picker (interactive) | 3 |
| `PickerPause.dc.html` | Skill picker · prerequisite warning + pause dialog | 3 |
| `Home.dc.html` | Home · active skill + reviews due | 1, 7, 8 |
| `HomeEmpty.dc.html` | Home · first run, empty library | 1 |
| `Library.dc.html` | Library · processing, reference only, needs OCR | 2 |
| `SkillMap.dc.html` | Skill map · grouped by domain, one skill open | 2, 3 |
| `SkillReview.dc.html` | Skill review (manual mode) + merge diff | 2 |
| `Project.dc.html` | Create project | 3 |
| `Setup.dc.html` | Setup check · API key missing | 1 |
| `Source.dc.html` | Source passage viewer | all citations |
| `Review.dc.html` | Review mode · hint shown | 8 |
| `Progress.dc.html` | Progress | F1, F4 |
| `Profile.dc.html` | How I learn (learner profile) | E4 |
| `Concepts.dc.html` | Concepts library · one shaky concept open | B7, F5 |

Sample content (Grandma's Kitchen, Mai, hours, mistakes) is illustrative. Book titles, pages and passages are placeholders (`[Book A]`, `p. 41`), not real citations.

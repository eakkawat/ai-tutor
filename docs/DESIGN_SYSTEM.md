# Design System: AI Tutor

A quiet, focused study tool. One accent color, plenty of white space, monospace for anything precise (timestamps, citations, hours). The work and the feedback are the loudest things on screen.

The mockups in `../design/` are the reference for every component below.

## 1. Principles

1. **Next step only.** Each screen has one obvious primary action. Never present the full curriculum as a plan.
2. **Show the source.** Citations are always visible and always clickable.
3. **Status in words.** Every state (Followed, Partly, Ready, Needs OCR…) has a text label; color only reinforces it.
4. **Calm by default.** Strong color is reserved for the primary action, the current step, and problems.

## 2. Color tokens

All text/background pairs below meet WCAG AA (4.5:1) unless marked decorative.

### Neutrals

| Token | Hex | Use |
| --- | --- | --- |
| `--bg` | `#F5F6F4` | App background |
| `--bg-reader` | `#E9EBE7` | Background behind book pages (source viewer) |
| `--surface` | `#FFFFFF` | Cards, header, inputs |
| `--surface-sunken` | `#F5F6F4` | Inset panels inside cards (examples, triage, stats) |
| `--border` | `#DADDD8` | Card borders, dividers |
| `--border-subtle` | `#E3E6E1` | Row dividers inside cards; progress-bar tracks |
| `--border-control` | `#C4C8C2` | Secondary buttons |
| `--border-input` | `#A9AFA8` | Text inputs, textareas, dashed drop zones |
| `--text` | `#16181A` | Primary text (16.4:1 on `--bg`) |
| `--text-2` | `#3A3F44` | Body copy in cards (10.6:1 on white) |
| `--text-muted` | `#5B6066` | Labels, meta, captions (5.9:1 on `--bg`, 6.3:1 on white) |
| `--text-faint` | `#8A9096` | **Decorative only** (breadcrumb slashes, `aria-hidden`). 3.2:1; never for readable text |

### Accent (action, current step, selection)

| Token | Hex | Use |
| --- | --- | --- |
| `--accent` | `#2F4BC9` | Primary buttons, links, current phase, active borders (7.1:1 with white) |
| `--accent-strong` | `#1F3399` | Link hover; text on `--accent-soft` (8.9:1) |
| `--accent-soft` | `#E8EBFA` | Selected nav item, citation chip, info banners, selected chips |
| `--accent-tint` | `#F7F8FE` | Selected list row / expanded table row |

### Status

| Status | Text | Background | Border | Used for |
| --- | --- | --- | --- | --- |
| Success | `#1E6B45` | `#E3F1E8` (pill), `#EEF6F1` (panel) | — | Followed, Passed, Ready, done steps |
| Warning | `#7A4E00` | `#FBF0D9` | `#E9CF95` | Partly, Needs prerequisite, Too hard, hints, optional missing tool |
| Danger | `#A3261A` | `#FBE4E1` (pill), `#FBEFED` (panel) | `#E8B4AC` | Not followed, Needs OCR, rejected file, required setup missing, Delete |
| Neutral | `#3A3F44` | `#ECEEEA` | — | Not started, Reference only |
| Info | `#1F3399` | `#E8EBFA` | — | Processing, In progress, Too easy, items to review |

### Special

| Token | Hex | Use |
| --- | --- | --- |
| `--highlight` | `#FFF3C4` | Cited passage highlight in source viewer and source panels |
| `--frame-placeholder` | `#2A2D30` | Video frame / clip thumbnail placeholder |
| `--image-placeholder` | `#D5D9D3` | Image thumbnail placeholder |
| `--scrim` | `rgba(22,24,26,0.45)` | Dialog backdrop |
| `--disabled-bg` | `#C9CDC7` | Disabled primary button (text `--text-2`) |

## 3. Typography

| Family | Use |
| --- | --- |
| **IBM Plex Sans** (400, 500, 600) | All UI text |
| **IBM Plex Mono** (400, 500) | Timestamps, citations, hours, file names, counts in tables, code |
| **IBM Plex Serif** (400) | Book pages in the source viewer only |

Load from Google Fonts: `IBM+Plex+Sans:wght@400;500;600`, `IBM+Plex+Mono:wght@400;500`, `IBM+Plex+Serif:wght@400`.

### Scale

| Token | Size / line-height | Weight | Use |
| --- | --- | --- | --- |
| `display` | 30–32px / 1.2 | 600 | Home "Continue" title, first-run heading |
| `h1` | 28px / 1.25 | 600 | Page titles |
| `h2` | 22px / 1.3 | 600 | Lesson and feedback titles |
| `h3` | 17–18px / 1.35 | 600 | Card titles, questions |
| `body` | 15px / 1.5 | 400 | Default |
| `body-sm` | 14px / 1.5 | 400 | Card body, table cells, buttons |
| `caption` | 13px / 1.45 | 400 | Meta, helper text |
| `label` | 12px, uppercase, 0.06em tracking | 600 | Section eyebrows ("CHECK · QUESTION 2 OF 3") |
| `mono-sm` | 12–13px | 400–500 | Citations, timestamps, hours |
| `reader` | 16px / 1.7 Serif | 400 | Book page text |

## 4. Spacing, radius, size

- **Spacing scale (px):** 4, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32, 48, 56.
  - Card padding: 20–24px (28px for the hero card).
  - Gap between cards: 16px. Page gutter: 32px desktop, 16px phone.
- **Radius:** 3–4px (inline marks, frames), 6px (small chips, copy buttons), 8px (buttons, inputs, inset panels), 10px (segmented control, step cards), 12px (cards), 16px (hero card, first-run panel), 999px (pills).
- **Control heights:** 44px default (minimum touch target), 48px for the hero primary button, 40px for filter chips and inline Edit/Remove buttons, 36px for compact copy buttons.
- **Layout widths:** content max 1120–1440px; forms and focused flows max 680–880px; the side column is `flex: 1 1 320–380px`, the main column `flex: 999 1 560px; min-width: 0`, so they stack on narrow screens.

## 5. Components

### Buttons

| Variant | Style | Use |
| --- | --- | --- |
| Primary | `--accent` bg, white text, 500 weight, no border | One per view: Continue, Submit, Start, Save |
| Secondary | white bg, `--border-control` 1px, `--text` | Hint, Pause, Cancel, Compare attempts |
| Quiet | transparent, `--text-muted` | "This felt wrong", show more |
| Danger | transparent or white, `--danger` text | Delete, Remove, Discard |
| Disabled | `--disabled-bg`, `--text-2`, with a visible reason nearby | Setup Continue without API key |
| Icon | 44×44, `aria-label` required | Remove file, page arrows, more actions |

A link that navigates can be styled as a button, but stays an `<a href>`.

### Pills and chips

- **Status pill:** 12px/600, padding 2px 10px, radius 999. Colors from the Status table. Always text.
- **Citation chip:** Mono 12–13px, `--accent` text on `--accent-soft`, padding 1px 6px, radius 4. An `<a>` that opens the source viewer.
- **Filter chip / choice chip:** 40–44px tall, radius 999 (filters) or 8 (choices). Selected = 2px `--accent` border + `--accent-soft` bg + `--accent-strong` 600 text; uses `aria-pressed` or a real radio.
- **Tag:** 13px, `--surface-sunken` bg, radius 6, e.g. "Support: beat template".

### Cards

White, 1px `--border`, radius 12. The card needing action now gets a **2px `--accent` border** (recall question, submission, flow rating, current merge). Problems get a 1px danger border.

### Phase stepper (session)

Seven steps in a wrapping row: Diagnose, Learn, Check, Practice, Feedback, Revise, Pass.
- **Done:** 22px circle `--success` with a white check (SVG).
- **Current:** 22px circle `--accent` with a white number, label 600 `--text`, `aria-current="step"`.
- **Upcoming:** 20px outlined circle (`--border-input`), label `--text-muted`.

### Progress bars

Track `--border-subtle`, fill `--accent` (in progress) or `--success` (done/passed). Heights: 4px (processing steps), 6px (header hours, queues), 8px (hero), 12px (Progress page). Always paired with a number in Mono (e.g. `2.9 / 20`). Charts use `role="img"` + `aria-label`.

### Principle check row

Pill (min 92px, centered) + principle title (600) + citation chip; below, evidence in `--text-2` with the locator in Mono (`Line 2`, `0:48–1:10`), then frame thumbnails (112×63, radius 4) with Mono timestamp captions. Rows are separated by `--border-subtle`.

### Attachment row

Thumbnail (64×40) + file name in Mono + status line + remove icon button. Processing video shows three sub-steps (Keyframes, Transcript, Cuts), each with a 4px bar and a text status. Rejected files use the danger panel with `role="alert"`.

### Flow rating

Three buttons: Too easy / Just right / Too hard (`aria-pressed`, inside `role="group"`). After a choice, a `--surface-sunken` panel says what changed in one sentence, starting with a bold verdict ("One change:", "No change:", "Keeping the level.").

### Source panel and viewer

- **Panel:** eyebrow "SOURCE", book title, Mono "Chapter 7 · page 114", an inset with surrounding text and the cited passage on `--highlight`, plus an "Open full page" link.
- **Viewer:** a page on `--bg-reader`, Plex Serif, a highlighted passage, prev/next page buttons, and a side panel with "Cited for", "Where you've seen it" and "This citation looks wrong".

### Dialog

`--scrim` backdrop; white panel, max 480px, radius 12, padding 24; `role="dialog"`, `aria-modal="true"`, `aria-labelledby`. The safe choice is secondary; the confirming action is primary on the right.

### Concept level pill

The same pill shape as status pills, one color per level:

| Level | Colors | Meaning |
| --- | --- | --- |
| Use | Success | Shown in practice work |
| Spot | Info | Can find it in an example |
| Define only | Warning | Can explain it, can't yet spot it |
| Not yet | Neutral | Not checked |

A **Foundation** tag (outlined, `--text-2`, radius 6) marks concepts many skills depend on. A shaky concept adds a warning line under its name, e.g. "Confused with exposition 2×".

### Level ladder

Three steps (Define → Spot → Use), shown as a vertical list. Each step has a status circle (done = success check, current = accent number, upcoming = outline) and a one-line description. It's used in the session's concept panel and on the Concepts screen.

### Spot question options

Each option is a full-width `<button aria-pressed>`: white, 1px `--border`, radius 10, padding 14×16, with a speaker or locator line in `label` style above content in Mono.
- **Selected:** 2px `--accent` border, `--accent-tint` background.
- **After Check answer:** the correct option gets a success border and a "Correct" pill; a wrong pick gets a danger border and a "Not this one" pill.
- The explanation follows in a `role="status"` panel with a citation chip.

### Locked step

A dashed `--border-input` panel with a lock icon and plain reasons: "Practice unlocks when all 3 concepts reach Spot. 2 of 3 done." The primary button is disabled and `aria-describedby` points to the reason.

### Navigation

- **Main app:** header with "Tutor" and tabs (Home, Skill map, Concepts, Library, Progress, How I learn). Tabs are 44px tall; the active one uses `--accent-soft` bg, `--accent-strong` 600 text and `aria-current="page"`.
- **Inside a flow** (session, skill picker, review): a breadcrumb instead of tabs.

### Tables

14px, header 12px `--text-muted` weight 500, row padding 10–12px, `--border-subtle` dividers. Numbers right-aligned in Mono. Wide tables sit in an `overflow-x: auto` box with `min-width: 640px`.

## 6. Accessibility rules

- Native elements: `<button>`, `<a href>`, `<label>` + `<input>`/`<textarea>`, `<fieldset>`/`<legend>` for radio groups, `<table>` with `<th scope>`.
- Touch targets ≥ 44px (filter chips 40px tall are the only exception, with spacing around them).
- Icon-only buttons have `aria-label`; decorative SVGs have `aria-hidden="true"`.
- Status never relies on color alone. Warning and danger colors also differ in lightness from success.
- Live updates use `role="status"` (hints, prerequisite notes) or `role="alert"` (rejected file).
- Visually hidden labels use a 1px clip pattern, never `display: none`.
- Layout works at phone width: the side column stacks under the main one, toolbars wrap, and tables scroll inside their box.

## 7. Voice and copy

- Short, plain, direct, like a good teacher. No empty praise, no exclamation marks.
- Verdict first, then the reason: "Not passed yet: 2 of 4 principles followed."
- Name the exact change: "One change: the beat template is removed."
- Use placeholders, never invented book facts: `[Book A]`, `[The cited passage]`.
- Buttons say what happens: "Submit attempt 2", "Pause and start", "Run OCR".

## 8. CSS tokens

```css
:root {
  --bg: #F5F6F4; --bg-reader: #E9EBE7; --surface: #FFFFFF; --surface-sunken: #F5F6F4;
  --border: #DADDD8; --border-subtle: #E3E6E1; --border-control: #C4C8C2; --border-input: #A9AFA8;
  --text: #16181A; --text-2: #3A3F44; --text-muted: #5B6066; --text-faint: #8A9096;
  --accent: #2F4BC9; --accent-strong: #1F3399; --accent-soft: #E8EBFA; --accent-tint: #F7F8FE;
  --success: #1E6B45; --success-soft: #E3F1E8; --success-panel: #EEF6F1;
  --warning: #7A4E00; --warning-soft: #FBF0D9; --warning-border: #E9CF95;
  --danger: #A3261A; --danger-soft: #FBE4E1; --danger-panel: #FBEFED; --danger-border: #E8B4AC;
  --neutral-soft: #ECEEEA;
  --highlight: #FFF3C4; --frame-placeholder: #2A2D30; --image-placeholder: #D5D9D3;
  --scrim: rgba(22, 24, 26, 0.45); --disabled-bg: #C9CDC7;
  --font-sans: 'IBM Plex Sans', system-ui, sans-serif;
  --font-mono: 'IBM Plex Mono', ui-monospace, monospace;
  --font-serif: 'IBM Plex Serif', Georgia, serif;
  --radius-sm: 4px; --radius: 8px; --radius-card: 12px; --radius-lg: 16px; --radius-pill: 999px;
  --control-h: 44px;
}
```

## 9. Tailwind theme (if using Tailwind)

```js
// tailwind.config.js (theme.extend)
colors: {
  bg: '#F5F6F4', reader: '#E9EBE7', surface: '#FFFFFF',
  border: { DEFAULT: '#DADDD8', subtle: '#E3E6E1', control: '#C4C8C2', input: '#A9AFA8' },
  ink: { DEFAULT: '#16181A', 2: '#3A3F44', muted: '#5B6066', faint: '#8A9096' },
  accent: { DEFAULT: '#2F4BC9', strong: '#1F3399', soft: '#E8EBFA', tint: '#F7F8FE' },
  success: { DEFAULT: '#1E6B45', soft: '#E3F1E8', panel: '#EEF6F1' },
  warning: { DEFAULT: '#7A4E00', soft: '#FBF0D9', border: '#E9CF95' },
  danger: { DEFAULT: '#A3261A', soft: '#FBE4E1', panel: '#FBEFED', border: '#E8B4AC' },
  neutral: { soft: '#ECEEEA' },
  highlight: '#FFF3C4',
},
fontFamily: {
  sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
  mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
  serif: ['"IBM Plex Serif"', 'Georgia', 'serif'],
},
borderRadius: { card: '12px', lg: '16px' },
minHeight: { control: '44px' },
```

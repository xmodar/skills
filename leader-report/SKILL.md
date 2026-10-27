---
name: leader-report
description: Build the weekly Capacity Building sector leaders meeting deck (اجتماع قادة قطاع بناء القدرات) from the official template. Interviews the user until every slide field is known (meeting date, departments, task groups, tasks with progress / what was done / next step / readiness date, not-started tasks, optional challenges), shows a summary for confirmation, then generates a .pptx with no hidden slides. Use whenever the user asks for the weekly leaders report, the leaders meeting slides, "تقرير القادة", "عرض اجتماع القادة", "شريحة الإدارة", or to update last week's leaders report.
---

# Weekly leaders report (leader-report)

Turns the user's weekly status into the deck built on `assets/template.pptx`
(copy of «قالب اجتماع قادة قطاع بناء القدرات.pptx»). The script clones the template's own
shapes (rows, progress rings, group bars, not-started cards, detail chips, icons), so the
output looks exactly like the template. Never edit the template; never hand-build slides.

Output deck: title slide (meeting date) → one slide per department → optional
challenges slide after a department → «شكراً لكم». The template's hidden helper slides
(guide, example, ready elements) are removed; the script refuses to save a deck with a
hidden slide or a leftover `[placeholder]`.

## Files

- `scripts/build_report.py` — validator + generator (run with `uv run`, deps are inline).
- `assets/template.pptx` — the template. `assets/example.json` — a complete example of the data format.

Commands (`SKILL` = this skill's folder, e.g. `~/.claude/skills/leader-report`):

```bash
uv run "$SKILL/scripts/build_report.py" --list-icons
uv run "$SKILL/scripts/build_report.py" data.json --check
uv run "$SKILL/scripts/build_report.py" data.json -o "out.pptx"
```

`--check` validates, checks that every department fits on its slide, and prints an Arabic
summary of every slide. Exit code 2 = an `ERROR:` line explains what is missing or too long.

## Data the deck needs

Per report: `meeting_date` (ISO `YYYY-MM-DD`; printed as «الثلاثاء 27 أكتوبر 2026»).

Per department (`departments[]`):
- `name` — slide title, e.g. «إدارة تصميم تجربة التعليم».
- `groups[]` — each a coloured side bar: `name` (empty string = no bar), optional `color`
  `navy`/`green` (default alternates navy, green), and `tasks[]`.
- Each task:
  - `name` (required), `description` (optional second line, short).
  - `progress` 0–100 (required). 100 ⇒ readiness is forced to «جاهزة».
  - `done` — ما تم (required, one or two lines).
  - `next` — الخطوة القادمة (required, one or two lines).
  - `readiness` — الجاهزية: a real date, never a duration (required unless 100%). ISO dates
    become «22 أكتوبر» (year added when not the meeting year). A list gives several lines,
    e.g. `["سماي ٢: 20 أكتوبر", "الحماية: 27 أكتوبر"]`.
  - `icon` — Arabic name from `--list-icons` (e.g. «تعلم إلكتروني», «مستندات», «أتمتة»). You choose it; don't ask.
  - `details` (optional) — sub-items shown as status chips under the task:
    `[{"label": "التعليم", "status": "done|in_progress|not_started"}]`.
- `not_started[]` (optional) — tasks not started yet: `name`, `start` date, `ready` date, `icon`.
- `challenges[]` (optional) — adds a slide «<الإدارة>: التحديات والدعم المطلوب»:
  `challenge` (التحدي), `impact` (الأثر), `support` (الدعم المطلوب من القادة), `due` (الموعد).

Template rules to keep (from its hidden guide slide): one slide per department; at most six
tasks in the table; a finished task is 100% and «جاهزة»; tasks that have not started go to
«لم تبدأ», not into the table with 0%; readiness is a date, not a duration.

## Workflow

Talk to the user in their language (normally Arabic). Never invent a value: every task,
percentage, date and sentence comes from the user. You may shorten wording to fit, pick
icons and group colours, and convert dates, and you show all of that in the summary.

### 1. Start point

Data lives in a reports folder, default `~/Documents/leader-reports/` (ask once if the user
wants another place). Look there for the newest `*.json`.
- If one exists, offer (AskUserQuestion) to start from last week's report: then walk the
  user through each task asking only what changed (new %, what was done, next step,
  readiness date), which tasks finished or were dropped, which not-started tasks began, and
  what is new. Do not carry over a value without the user confirming it is still true.
- Otherwise start fresh.

### 2. Interview until complete

Ask in small rounds, not one giant form, and not one field per message:
1. Meeting date (suggest the coming meeting day; confirm). Which department(s) go in the
   deck this week.
2. For each department: its task groups and the tasks in each group (names only first).
3. For each task: progress %, ما تم, الخطوة القادمة, readiness date. Ask for a short
   description line only if the name needs one. Ask whether any task has sub-items worth
   showing as status chips (like sectors of a programme).
4. Not-started tasks with planned start and readiness dates.
5. Challenges: ask whether there are any challenges needing leaders' support this week;
   if yes, get the challenge, its impact, the support needed and by when.

After each round, check what is still missing or vague and ask specifically about it
(e.g. "«تصنيف البيانات»: ما تاريخ الجاهزية المتوقع؟"). Push back on:
- durations instead of dates («أسبوعين» → ask for the date);
- 100% without «جاهزة», or «جاهزة» below 100%;
- a 0% task in the table (offer to move it to «لم تبدأ»);
- more than six tasks (ask which to merge or move);
- long texts (> ~55 characters per cell) — propose a shorter wording.

Write the data to `<reports folder>/<meeting_date>.json` (UTF-8, `ensure_ascii` off) as
you go, so nothing is lost if the conversation stops.

### 3. Check and confirm

Run `--check`. Fix every `ERROR:` with the user (missing field, slide too full — shorten
or move tasks). Relay `WARNING:` lines and resolve them or get the user's OK to keep them.

Then show the user the full summary (the `--check` output, as a readable table per slide:
task, %, ما تم, القادمة, الجاهزية, icon) plus the output path, and ask for explicit
confirmation (AskUserQuestion: «إنشاء العرض» / «تعديل»). Do not generate before the user
confirms. Apply any edits, re-run `--check`, and confirm again if anything changed.

### 4. Generate and verify

```bash
uv run "$SKILL/scripts/build_report.py" "<folder>/<date>.json" -o "<folder>/اجتماع قادة قطاع بناء القدرات - <date>.pptx"
```

The script verifies after saving: no hidden slides, expected slide count, no leftover
placeholders. On Windows with PowerPoint installed, also render it and look at each slide
(text overflowing a cell or bar, wrong ring, wrong icon):

```powershell
$app = New-Object -ComObject PowerPoint.Application
$p = $app.Presentations.Open("<pptx>", $true, $false, $false)
foreach ($s in $p.Slides) { $s.Export("<png folder>\slide$($s.SlideIndex).png", "PNG", 1600, 900) }
$p.Close(); $app.Quit()
```

If a cell overflows, shorten that text with the user's agreement (or move a line into
`description`) and regenerate. Finish by giving the user the .pptx path and the slide list.

## Notes

- Row heights grow with text (≈1–3 lines); the script errors if a department no longer fits
  above the footer. The usual fix is shorter text, fewer detail chips, or fewer tasks.
- Icons on not-started cards are drawn automatically in the template's faint grey style.
- The footer date and slide numbers are live fields from the template layout.

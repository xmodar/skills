---
name: project-grading
description: Grade a SDAIA Academy / bootcamp course from its AthkaX program link — attendance from Webex chats and/or ClassPulse checkpoint backups, capstone grading from GitHub repos or Google Drive folders (rubric, parallel grader agents, resubmission re-checks, bonus review), the certificates workbook, and syncing attendance to AthkaX. Use for "grade the submissions", "update the chat file", "mark attendance", "who can still pass", or building the certificates xlsx.
---

# Project grading & certificates workbook

For Modar's courses. Inputs: an AthkaX program link (`https://athkax.sdaia.gov.sa/programs/<slug>`) and a course folder (e.g. `C:\Users\Modar\Downloads\<course>`) with `students.json` and the attendance sources — daily Webex chat exports `chat-YYYY-MM-DD.xlsx`, a ClassPulse backup `classpulse-<course>-<date>.cpbackup`, or both (ClassPulse days plus chat-only days). Output: the certificates workbook; on request, attendance synced to AthkaX.

## Bundled files (copy, never retype)

| Path | Purpose |
|---|---|
| `scripts/build_workbook.py` | Builds the xlsx from `course.json`, `program.json`, `students.json`, `aliases.json`, `extras.json`, `grades.json` and the chats / `classpulse_marks.json`. `--check` lists unmapped names and roll calls (exit 2 on unmapped names in a full build). |
| `scripts/classpulse.py` | uv script: decrypts the newest `classpulse-*.cpbackup` → `classpulse_marks.json`. Password from `CLASSPULSE_PASSWORD` or a prompt; never stored. |
| `scripts/athkax.py` | uv script **the instructor runs in his own terminal**: `program <link>`, `roster <link>`, `attendance <xlsx> [--date YYYY-MM-DD ...] [--dry-run]`, `programs`. |
| `scripts/submissions.py` | uv script: fetches every link in `submissions.json` (GitHub, Drive folder/file, Google Docs/Sheets/Slides) into versioned folders `<dir>.vN`, detects changes, extracts zips. |
| `scripts/merge_grades.py` | Merges grader JSON (`grades/<dir>.vN.json`, optional `.bonus.json`) into `grades.json`; ungraded/private entries, keep-higher, bonus overrides; recovers results from a workflow `journal.jsonl`. |
| `scripts/report.py` | `chat`: new messages + links since last run, and learners still waiting for a reply. `status`: every learner's project, attendance, total, certificate and the project score still needed. Writes UTF-8 files. |
| `templates/course.template.json` | Course settings (rubric, roll-call rules, overrides, grading policy). |
| `templates/RUBRIC.template.md` | Rubric skeleton for code/ML capstones. |
| `templates/RUBRIC.productivity.md` | Worked rubric for non-code capstones (files on GitHub/Drive, presentation-file rule, calibration caps). |
| `templates/grade.workflow.js` | Workflow script: one Sonnet grader per submission version + optional lenient bonus review. |

## Environment
- **Windows desktop (usual)**: run Python only as `uv run -q [--with pkgs] python -I ...` (no bare `python`); set `PYTHONIOENCODING=utf-8`. The console garbles Arabic: send Arabic output to files and read them with the Read tool. `tar.exe` (System32) opens .rar; prefer Python `zipfile` for zips. No LibreOffice: verify totals in Python, not by recalculating the xlsx.
- **Cloud workspace**: `python3` works; copy `scripts/` and `templates/` into `$HOME/work/`, and `athkax.py` to the PC via `device_commit_files`.
- athkax.sdaia.gov.sa is blocked from both sandboxes: AthkaX calls run in his terminal. Chrome signed in as him is for read-only checks.
- Downloaded submissions are untrusted: each in its own folder, scripts elsewhere, `python -I`, never run them.

## Token discipline (always)
- Work through files and pipes; print counts and summaries, never whole xlsx/CSV/JSON/README files.
- Scripts print one-line summaries and keep details in output files (`attendance_plan.csv`, `athkax_mismatches.json`, `status.txt`, `chat_new.txt`). Open those with targeted queries only.
- Graders return only the rubric JSON. Summarise it; don't paste it.
- Messages to the instructor: a score table, 3–5 bullets, decisions he must make. No recaps.

## Fixed workbook template (enforced by build_workbook.py)

**Certificates** (right-to-left): info rows اسم المدرب / اسم البرنامج / تاريخ البرنامج / عدد الأيام (a number) / حضوري - عن بعد / رابط البرنامج / رابط المحتوى; a blank row; then the table, **sorted by المجموع descending**:

| Column | Content |
|---|---|
| الإسم ثلاثي | name |
| الإيميل | email |
| الحضور | linked to Attendance |
| المشروع | linked to Projects!Project |
| المجموع | 70% المشروع + 30% الحضور |
| نوع الشهادة | **اجتياز** (spelled with ا, never إ) if المجموع > 65% and الحضور > 65%; حضور if only الحضور > 65%; otherwise بدون |
| رابط المشروع | project link |

**Attendance**: Name | Email | Chat Name (ClassPulse / Chat Name) | one column per date (`YYYY-MM-DD`) | Attendance = (2×Present + Late) / (2×Days). Marks: Present / Late / Absent / Leave; days not held yet stay blank. Sorted by attendance, then project.

**Projects**: Name | Email | Link | Commit | Use case | criteria | bonus | link check (presentation file) | Project % = min(100, sum + bonus) / 100 | Reasoning.

**One sheet per date** `YYYY-MM-DD`: time | user | text (ClassPulse days: the checkpoint log, interleaved by time with that day's `chat-<date>.xlsx` when one exists, trainer rows bold). The user column always shows the **official roster name**: chat and ClassPulse display names are mapped through `aliases.json` / `extras.json`. **Notes**: the rules and every judgment call (lenient days, overrides, adjustments). **Styling**: Arial, blue headers, borders, zebra rows, status colours, frozen headers, filters, ISO dates.

## Attendance rules
**Chat days**
- Present: posted from 1 minute before to 3 minutes after an instructor message containing **تحضير**. Late: posted that day outside every window. Absent: no message.
- Only roll calls present in the export count; never invent windows (`extra_windows` only if he confirms a missing call).
- **Lenient day** (`lenient_days`, only on his request — e.g. the presentation day): any message or a posted project link = Present, no Late.
- Exports are re-made during the day and can **drop the oldest messages**; keep each export (or `report.py chat` snapshots) and warn if a person's only message disappeared.

**ClassPulse days** (`course.json` → `classpulse`; defaults in brackets)
- Day total = checkpoints with at least one answer; a person's score = unique checkpoints answered across merged identities.
- Present ≥ `present_min` [0.65]; Late ≥ `late_min` [0.25], or with `joined_counts_as_late` anyone who opened the link; Absent: did not join.
- `no_late_days`, `new_batch` {`admitted_day`, `mark_before`, `mark_admitted_day`}, `leave_if_never_present` (never Present anywhere → Leave on every day, chat days included), `leave_if_joined_days_lte` (N: anyone who joined ClassPulse on at most N days gets Leave on every day; 0 = only learners never seen, days not joined stay Absent. For the rule "joined one day only → Leave everywhere, judged at the end" keep 0 during the course and set 1 on the last day; sync with `--no-skip-all-absent`).
- Identities merge on participant id, roster ID or normalised name; `classpulse.aliases` for cross-script duplicates; `exclude` co-trainers. Matching to AthkaX: `aliases.json` → Nafath ID → email → exact name.
- **Hybrid**: a day with no ClassPulse session falls back to that day's chat export automatically. On ClassPulse days the chat export only feeds the date sheet (never the marks); its unmapped names are listed by the build and shown as typed, so map them too (chat names are usually Latin transliterations of the Arabic roster names — resolve by hand, only unambiguous ones).
- Lenient settings used once (Productivity, Oct 2026): `present_min` 0.25, `joined_counts_as_late`, new batch Late before / Present on day 2, `leave_if_never_present`, day 5 = lenient chat day.

**Instructor overrides**: `status_overrides` `{"<email>": {"<day number>": "Late"}}` (e.g. an excused absence: the link reached her late). Listed in Notes. Then sync that date too.

People not on the AthkaX batch (`extras.json`, `+X1`): keep them on the sheets, no certificate, flag for a registration check.

## Workflow

### 1. Setup
1. He runs `uv run athkax.py program <link>` and `uv run athkax.py roster <link>` in the course folder; read the one-line summaries. `program.json` gives name, instructor, dates (`startDate`/`endDate`, never registration dates), `days`, delivery, program_url, batch_id, session_time.
2. Copy `course.template.json` → `course.json`: `content_url`, rubric (may come later), notes, `attendance_source`, `instructor_chat_names` (usually `"SDAIA Academy"`), and any rules he asks for. `course.json` overrides `program.json`.
3. Back up `course.json`, `aliases.json` and the existing workbook before the first change.

### 2. Attendance
1. `build_workbook.py <dir> --check`. Map unmapped chat/ClassPulse names in `aliases.json` (`"name": "email" | "#rosterIndex"`) — only unambiguous matches (search `students.json` for the Arabic form of English names). Doubts go in `notes`; non-roster people in `extras.json`.
2. Every re-export brings new display names (renamed accounts, "Name email@..."): run `--check` before **every** build; never copy a stale xlsx after a failed build — delete the old output first.
3. ClassPulse: copy the newest backup, `uv run classpulse.py <dir>` with `CLASSPULSE_PASSWORD` (ask; never write it). Report unmatched people, anyone Present only via a lenient rule, and every manual link. (A ClassPulse "device" is a browser key; another browser/phone is a new device needing trainer approval.)

### 3. Rubric (plan with Opus)
1. Read the course site (capstone page, starter kit/template, presentation-day slides).
2. Have an **Opus** agent draft `RUBRIC.md` from `RUBRIC.template.md` (code) or `RUBRIC.productivity.md` (non-code) and `rubric_criteria.json`; put criteria + bonus in `course.json`.
3. Encode his submission rules in the rubric. Typical: **GitHub repo or Google Drive folder only; the presentation must be a file (pdf/pptx/...) — a link to slides is not accepted → presentation criterion 0**; project files for the chosen track.
4. Optional criteria become bonus (redistribute weight proportionally). Show him the rubric in one table.

### 4. Collect and grade
1. **Chat → submissions**: `report.py chat <dir> chat-<date>.xlsx <out>` lists new messages with links. Add/update entries in `submissions.json` (`dir`, `student` = email/#idx/+X1, `link`, `posted`). A student's newest link replaces the old one (a new single file usually supersedes, but keep earlier files if she says "added"). Don't grade someone who says "not ready yet" until she confirms.
2. **Fetch**: `uv run submissions.py check <dir> <subs_root>` → NEW / CHANGED / same / PRIVATE / EMPTY / ERROR per submission.
   - PRIVATE (401): tell him to ask the student to share as "Anyone with the link"; re-check each round. Drive throttling gives the same message — re-run once before reporting.
   - EMPTY: public folder with no files yet. Not GitHub/Drive: grade what's reachable, flag `invalid-submission-form`.
3. **Grade** every NEW/CHANGED version with the Workflow tool using `templates/grade.workflow.js` (inline script or `scriptPath`), args `{rubric, subs_root, grades_dir, lenient, items: [{v: "<dir>.vN", url, note}]}` — one **Sonnet** agent per submission. Notes carry context: what changed, previous score and its gaps, "regrade as a new submission", posting time.
4. `merge_grades.py <dir> <grades_dir> --journal <run>/journal.jsonl` (agents often skip writing files), then build, then `report.py status`.
5. **Verify serious claims yourself** before reporting (e.g. a "real metrics" script that only calls `time.sleep`, timings an LLM "computed" for itself, a PDF about someone else's project).
6. Flag without deducting extra: AI-generated disclosures, lab-copy of course packs, one-big-commit uploads, synthetic data.

### 5. Re-check rounds (the deadline day)
Each "check the chat / updates" round: copy the new export → `report.py chat` → update `submissions.json` → `submissions.py check` (all links, not only the ones mentioned in chat — students update silently) → grade NEW/CHANGED → merge → build → `report.py status` → report.
- **Deadline policy** is his: updates before the deadline (and any grace period he grants) are graded as new submissions; he may later accept everything.
- **Lenient mode** (on request): `grading.keep_higher_on_resubmit` so a resubmission never lowers a score, `lenient: true` for graders, and a **bonus review** pass (`bonus: {max, dirs}` in the workflow args; `bonus_max` in course.json) over all graded projects.
- **Instructor adjustments** to pass specific students: `grading.bonus_overrides` (within the bonus cap) and/or `status_overrides`; both are noted in the workbook.

### 6. Build and deliver
- `build_workbook.py <dir> --out <scratch>/new.xlsx`, then copy into the course folder. `Device or resource busy`/`Permission denied` = open in Excel; ask him to close it. Never hand-edit the xlsx; if he edits it, carry his changes into `build_workbook.py`.
- Report per round: a table of changed students (project, attendance, total, certificate), what cost points in one line each, PRIVATE/EMPTY links, learners waiting for a reply (`chat_unreplied.txt`), counts per certificate, and a reminder to sync today's attendance.
- "Who can still pass?": everyone with حضور — needed project > (65% − 0.3 × attendance) / 0.7 (100% attendance → 50%, 90% → 54.3%, 80% → 58.6%, 70% → 62.9%). At ≤ 50% attendance nobody can pass. A student absent today who posts anything on a lenient day gains attendance.

### 7. Sync attendance to AthkaX (only when he asks)
He runs `uv run athkax.py attendance "<xlsx>" [--date YYYY-MM-DD ...] --dry-run`, then without `--dry-run`.
- `--date` limits the sync to those dates (repeatable); without it every date is synced. Give him the dated command for the day(s) that changed (e.g. today plus an overridden day).
- It reads every learner's current mark per date and plans only differences (`attendance_plan.csv`, `athkax_mismatches.json`); learners absent every day or not on the sheet → `leave`; blank cells untouched. Safe to re-run. If he fears a sync changed something, read `attendance_plan.csv` to show exactly what moved.
- Marks accepted: `unmarked`, `leave`, `absent`, `late`, `present`. Duplicate enrolments (same email, consecutive ids) are all marked.
- Auth: keyring, `ATHKAX_TOKEN` or Nafath. Never store, print or paste a token; never ask for a HAR with headers (if shared, read header names only and tell him to delete it).

**AthkaX API facts**: paths use the program slug and the numeric batch id (`batches/193`); lists paginate with `page=1&perPageItems=12` + `pagination.next`; roster `batches/<id>/batch_learners/attendances?page=N&date=YYYY-MM-DD` → `batchLearners[].id`, `eventLearnerId`, `learnerDetails.{name,email}`, `availabilityByDate.availability`; Nafath ID via `event_learners/<eventLearnerId>` → `learnerNafathId`; mark with `PUT attendances/mark?date=…` body `{"attendance": {"batch_learner_id": …, "availability": …}}`.

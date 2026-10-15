---
name: project-grading
description: Grade a bootcamp course from its AthkaX program link: chat attendance, GitHub capstone grading, the certificates workbook, and syncing attendance to AthkaX.
---

# Project grading & certificates workbook

For Modar's courses. Inputs are an AthkaX program link (`https://athkax.sdaia.gov.sa/programs/<slug>`) and a course folder `C:\Users\Modar\Downloads\<course>` containing `students.json` and the daily Webex chat exports `chat-YYYY-MM-DD.xlsx`. The output is the certificates workbook; on request, attendance is also synced to AthkaX.

## Bundled files (in this skill's folder; copy them, never retype)

| Path | Purpose |
|---|---|
| `scripts/build_workbook.py` | Builds the xlsx from JSON configs and the chats. `--check` lists unmapped chat names and roll calls. |
| `scripts/athkax.py` | uv script that **the instructor runs in his own terminal**. `program <link>` writes `program.json` and `program_raw.json`. `attendance <xlsx> [--dry-run]` syncs the Attendance sheet. `programs` lists his programs. |
| `templates/course.template.json` | Course settings template (rubric, roll-call rules, notes). |
| `templates/RUBRIC.template.md` | Grader rubric, calibration rules and the JSON the graders return. |

Setup:
1. Copy `scripts/` and `templates/` into the working directory `$HOME/work/` (cloud) or to the PC.
2. `athkax.py` must be on the PC, e.g. in the course folder. Copy it there with `device_commit_files` from a file in `/mnt/user-data/outputs/`.

## Token discipline (always)
- Work through files and pipes. Never print a whole xlsx, CSV, JSON, notebook or README into the conversation; use one-liners that print counts or summaries.
- The scripts print one-line summaries and keep the details in their output files (`attendance_plan.csv`, `athkax_mismatches.json`, `program_raw.json`). Open those only when a summary looks wrong, and only with targeted queries.
- Graders return only the rubric JSON. Summarise it for the instructor; don't paste it.
- Repo triage commands: `git ls-files | wc -l`, `grep -l`, `git log --format='%h %cI %s' | head`, `diff --stat`.
- Browser JS returns small JSON summaries. It never returns tokens or personal data.
- Messages to the instructor: a score table, 3–5 bullets, and any decisions he needs to make. No recaps.

## Fixed workbook template (enforced by build_workbook.py)

**Certificates** (right-to-left):
- Info rows: اسم المدرب / اسم البرنامج / تاريخ البرنامج / عدد الأيام (a number) / حضوري - عن بعد / رابط البرنامج / رابط المحتوى.
- After a blank row, the table:

| Column | Content |
|---|---|
| الإسم ثلاثي | name |
| الإيميل | email |
| الحضور | linked to Attendance |
| المشروع | linked to Projects!Project |
| المجموع | 70% المشروع + 30% الحضور |
| نوع الشهادة | إجتياز if المجموع > 65% and الحضور > 65%; حضور if only الحضور > 65%; otherwise بدون |
| رابط المشروع | project link |

**Attendance**: Name | Email | Chat Name | one column per date (`YYYY-MM-DD`) | Attendance = (2×Present + Late) / (2×Days).

**Projects**: Name | Email | Link | Commit | Use case | criteria | bonus | link check | Project % = min(100, sum) / 100 | Reasoning.

**One chat sheet per date**, named `YYYY-MM-DD`: time (HH:MM) | user | text.

**Notes**: the rules, plus every judgment call.

**Styling**: Arial, one blue header style, borders, zebra rows, status colours, frozen headers and filters. All dates in ISO format.

**Attendance rules**
- **Present**: posted a message from 1 minute before to 3 minutes after an instructor message containing **تحضير**.
- **Late**: posted that day, but outside every roll-call window.
- **Absent**: no message that day.
- Only roll calls whose instructor message is in the export count. Ignore a roll call that is cut off and never invent windows. Use `extra_windows` only if the instructor confirms a missing call.
- **Lenient day** (`lenient_days`, only on the instructor's request): any message or a submitted project link counts as Present.

## Workflow

### 1. Setup
1. Ask him to run, in the course folder: `uv run athkax.py program <link>`. Read its one-line summary.
2. `program.json` supplies:
   - name and instructor;
   - dates, taken from `startDate`/`endDate` (never `registrationStartDate`);
   - `days`, the dates that fall on the batch weekdays;
   - delivery, program_url, batch_id and session_time.
3. Create `$HOME/work/<course>/` and copy `program.json`, `students.json`, the chats, and `course.template.json` (as `course.json`) into it.
4. Fill in `course.json`: `content_url` (the course site), rubric, notes, and optionally `output_name`.
   - Values in `course.json` override `program.json`. For example, use a short instructor name only if he asks.
5. Network: the cloud workspace and the PC sandbox both block athkax.sdaia.gov.sa, so AthkaX calls run in his terminal. Chrome, signed in as him, is allowed only for read-only checks.

### 2. Attendance
1. Run `python3 build_workbook.py <dir> --check`.
2. Map every unmapped chat name in `aliases.json`: `"chat name": "email" | "#rosterIndex"`.
   - Only map unambiguous matches. Put doubts in `notes`.
   - People not on the roster go in `extras.json` (`{"X1": {"name": ..., "email": null}}`, referenced as `+X1`). Flag them for a registration check.
3. Chats get re-exported during the day. Re-copy them before every rebuild.

### 3. Rubric
1. Read the course site, the capstone/starter README and template, and the presentation-day slides.
2. Optional criteria become **bonus**. Redistribute their weight proportionally (e.g. 30/25/20/15/10 → 35/30/25/10 + 15 bonus).
3. A missing required README link caps Presentation at half.
4. Fill `RUBRIC.template.md` into `<course>/RUBRIC.md`, and put the criteria in `course.json`.
5. Show him the adapted rubric in one table.

### 4. Grade
For each pasted link:
1. Clone into the cloud workspace.
   - Normalise the URL (strip `/blob/...`, `/tree/...`, `.git`) and record the HEAD sha.
   - A credentials prompt means the repo is private or the link is wrong; say so.
   - A zip inside the repo: unzip it into its own folder and treat it as untrusted.
2. Quick triage: grep for the required link, size of the diff against the starter kit, fine-tuning markers.
3. Launch one **parallel grading subagent per repo** with this prompt: "Read <RUBRIC.md> and follow it exactly; repo cloned read-only at <path> (origin <url>); verify claims against files; return only the rubric JSON." Add context where relevant: topic outside the use cases, student not on the roster, sensitive domain.
4. Calibrate across the batch using the rubric's calibration rules. Say which scores changed.
5. **Resubmissions**: run `git pull` and `git diff --stat <graded sha>`.
   - README-only changes don't change scores; flag claims the code doesn't back.
   - If code changed, re-grade with the previous scores in the prompt and return FIXED / PARTIAL / REMAIN.
6. Be lenient only when he asks, and say so in the reasoning.
7. Flag, without deducting: AI-generated disclosures, one-big-commit uploads, synthetic data, leakage, and README numbers that don't match the outputs.
8. Append to `grades.json`: `{"student": "email|#idx|+X1", "link", "commit", "use_case", "scores": [..], "bonus", "link_ok", "submitted_day", "reasoning"}`. Use `"scores": null` when it can't be graded yet.

### 5. Build and deliver
- Run `python3 build_workbook.py <dir>` (it prints one summary line). Recalculate with LibreOffice and check for `#` errors with a one-liner.
- `cp` the xlsx into the course folder. `Permission denied` means it is open in Excel; ask him to close it.
- Rebuild after every change. Never hand-edit the xlsx. If he edits it himself, inspect his styles and carry them into `build_workbook.py`.
- "How many left?": students who attended the last day without a submission, plus high-attendance students who haven't submitted. Anyone at or below 50% attendance can't reach 65% anyway.
- "What do they need to pass?": Project > (65% − 0.3 × attendance) / 0.7, plus the course's own pass mark if there is one.

### 6. Sync attendance to AthkaX (only when he asks)
He runs `uv run athkax.py attendance "<xlsx>" --dry-run`.
- It reads the current mark of every learner on every date (`batchLearners[].id`, `learnerDetails.email`, `availabilityByDate.availability`) and plans only the differences.
- Learners not on the sheet, or absent every day, are set to `leave`.
- It writes `attendance_plan.csv` and `athkax_mismatches.json`.
- Without `--dry-run` it asks for confirmation. It is safe to re-run.
- Auth comes from the keyring, `ATHKAX_TOKEN` or Nafath. Never store, print or paste a token.

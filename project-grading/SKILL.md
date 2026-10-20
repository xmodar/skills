---
name: project-grading
description: Grade a bootcamp course from its AthkaX program link: attendance from Webex chats or ClassPulse checkpoint backups, GitHub capstone grading, the certificates workbook, and syncing attendance to AthkaX.
---

# Project grading & certificates workbook

For Modar's courses. Inputs are an AthkaX program link (`https://athkax.sdaia.gov.sa/programs/<slug>`) and a course folder `C:\Users\Modar\Downloads\<course>` containing `students.json` and one attendance source: the daily Webex chat exports `chat-YYYY-MM-DD.xlsx`, **or** a ClassPulse backup `classpulse-<course>-<date>.cpbackup` (one backup holds every session). The output is the certificates workbook; on request, attendance is also synced to AthkaX.

## Bundled files (in this skill's folder; copy them, never retype)

| Path | Purpose |
|---|---|
| `scripts/build_workbook.py` | Builds the xlsx from JSON configs and the chats or `classpulse_marks.json`. `--check` lists unmapped names and roll calls. |
| `scripts/classpulse.py` | uv script: decrypts the newest `classpulse-*.cpbackup` and writes `classpulse_marks.json` (per-person, per-day marks + checkpoint logs) using the `classpulse` rules in `course.json`. Password from `CLASSPULSE_PASSWORD` or a prompt; never stored. |
| `scripts/athkax.py` | uv script that **the instructor runs in his own terminal**. `program <link>` writes `program.json` and `program_raw.json`. `roster <link>` writes `students.json` (batch-learner id, official name, email, Nafath ID). `attendance <xlsx> [--dry-run]` syncs the Attendance sheet. `programs` lists his programs. |
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

**Attendance**: Name | Email | Chat Name (ClassPulse Name) | one column per date (`YYYY-MM-DD`) | Attendance = (2×Present + Late) / (2×Days). Marks: Present / Late / Absent / Leave; days not held yet stay blank.

**Projects**: Name | Email | Link | Commit | Use case | criteria | bonus | link check | Project % = min(100, sum) / 100 | Reasoning.

**One chat sheet per date**, named `YYYY-MM-DD`: time (HH:MM) | user | text. With ClassPulse it holds the checkpoint log (trainer rows bold).

**Notes**: the rules, plus every judgment call.

**Styling**: Arial, one blue header style, borders, zebra rows, status colours, frozen headers and filters. All dates in ISO format.

**Attendance rules**
- **Present**: posted a message from 1 minute before to 3 minutes after an instructor message containing **تحضير**.
- **Late**: posted that day, but outside every roll-call window.
- **Absent**: no message that day.
- Only roll calls whose instructor message is in the export count. Ignore a roll call that is cut off and never invent windows. Use `extra_windows` only if the instructor confirms a missing call.
- **Lenient day** (`lenient_days`, only on the instructor's request): any message or a submitted project link counts as Present.

**ClassPulse attendance rules** (`course.json` → `classpulse`; defaults in brackets)
- A day's total = its checkpoints that got at least one answer. A person's score = unique checkpoints answered by any of their merged identities.
- **Present**: answered ≥ `present_min` [0.65]. **Late**: answered ≥ `late_min` [0.25]; with `joined_counts_as_late`, also anyone who opened the link that day (admitted, waiting or rejected). **Absent**: did not join.
- `no_late_days` [none]: Late counts as Present on those days. `new_batch` {`admitted_day`, `mark_before`, `mark_admitted_day`}: people who first joined on `admitted_day` (admitted late) get those marks.
- `leave_if_never_present`: anyone not Present on any session day is **Leave** on all of them; AthkaX learners never seen in ClassPulse are Leave too.
- Identities merge on ClassPulse participant id, roster ID, or normalised name; `aliases` link cross-script or shortened names (`{"ClassPulse name": "other ClassPulse name"}`); `exclude` drops co-trainers. Matching to AthkaX: `aliases.json` → Nafath ID → email → exact name.
- People not on the AthkaX batch stay on the Attendance sheet with no email (never synced) and get no certificate; flag them for a registration check.
- Lenient settings used once (Productivity, Oct 2026, first ClassPulse run): `present_min` 0.25, `joined_counts_as_late`, new batch Late before / Present on day 2, `leave_if_never_present`.

## Workflow

### 1. Setup
1. Ask him to run, in the course folder: `uv run athkax.py program <link>`. Read its one-line summary.
2. `program.json` supplies:
   - name and instructor;
   - dates, taken from `startDate`/`endDate` (never `registrationStartDate`);
   - `days`, the dates that fall on the batch weekdays;
   - delivery, program_url, batch_id and session_time.
3. For the official roster, ask him to run `uv run athkax.py roster <link>` (writes `students.json` with official names, emails and Nafath IDs; read its one-line summary).
4. Create `$HOME/work/<course>/` and copy `program.json`, `students.json`, the chats or the ClassPulse backup, and `course.template.json` (as `course.json`) into it.
5. Fill in `course.json`: `content_url` (the course site), rubric (may come later; attendance-only builds work without it), notes, and optionally `output_name`. For ClassPulse also set `"attendance_source": "classpulse"` and the `classpulse` rules he asks for.
   - Values in `course.json` override `program.json`. For example, use a short instructor name only if he asks.
6. Network: the cloud workspace and the PC sandbox both block athkax.sdaia.gov.sa, so AthkaX calls run in his terminal. Chrome, signed in as him, is allowed only for read-only checks.

### 2. Attendance
1. Run `python3 build_workbook.py <dir> --check`.
2. Map every unmapped chat name in `aliases.json`: `"chat name": "email" | "#rosterIndex"`.
   - Only map unambiguous matches. Put doubts in `notes`.
   - People not on the roster go in `extras.json` (`{"X1": {"name": ..., "email": null}}`, referenced as `+X1`). Flag them for a registration check.
3. Chats get re-exported during the day. Re-copy them before every rebuild.

### 2b. Attendance from ClassPulse (instead of chats)
1. Copy the newest backup into the course folder (each backup holds all sessions so far), then `uv run classpulse.py <dir>` with the password in `CLASSPULSE_PASSWORD` (ask him; never write it to a file). Read its one-line summary: people, merged identities, checkpoints per day, marks per day.
2. `python3 build_workbook.py <dir> --check` lists ClassPulse people not matched to `students.json`, with name candidates.
   - English vs Arabic names won't fuzzy-match: search `students.json` for the Arabic form yourself, then map confirmed ones in `aliases.json` (`"ClassPulse name": "official email"`). Only map unambiguous matches.
   - Same-person ClassPulse duplicates the merge missed (cross-script, shortened names) go in `classpulse.aliases`; re-run `classpulse.py`.
3. Report to him: unmatched people (likely not registered), anyone below Present only through a lenient rule, and every manual link.
4. ClassPulse identity: a "device" is a browser key in that browser's storage, so another browser, private window or phone is a new device. A known roster ID on a new device raises a second-device request the trainer must approve; there is no IP or hardware check.

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
- Learners not on the sheet, or absent every day, are set to `leave`. A `Leave` cell is sent as `leave`; blank cells are left alone.
- The platform accepts only `unmarked`, `leave`, `absent`, `late`, `present`.
- AthkaX can enrol one person twice (same Nafath ID/email, consecutive batch-learner ids). The sheet lists them once; the sync marks every record with that email.
- It writes `attendance_plan.csv` and `athkax_mismatches.json`.
- Without `--dry-run` it asks for confirmation. It is safe to re-run.
- Auth comes from the keyring, `ATHKAX_TOKEN` or Nafath; a refused saved session triggers a fresh Nafath login. Never store, print or paste a token, and never ask for a HAR file with headers in it — if he shares one, read only header names and tell him to delete it.

**AthkaX API facts** (from the web app):
- Paths use the program slug (`/instructor/events/<slug>/…`) and the **numeric** batch id (`batches/193`), not the batch slug.
- List endpoints are paginated like the web app: `page=1&perPageItems=12`, then follow `pagination.next`. `/instructor/events/ongoing` without `perPageItems` was refused with 403.
- Roster: `batches/<id>/batch_learners/attendances?page=N&date=YYYY-MM-DD` → `batchLearners[].id` (used to mark), `eventLearnerId`, `learnerDetails.{name,email}`, `availabilityByDate.availability`.
- Nafath ID: `event_learners/<eventLearnerId>` → `learnerNafathId` (not the batch-learner id).
- Mark: `PUT attendances/mark?date=…` body `{"attendance": {"batch_learner_id": …, "availability": …}}`.

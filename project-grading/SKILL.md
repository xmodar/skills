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
| `scripts/chat_day.py` | **Run after every new Webex export, before `--check`/build.** Archives the raw export (`backup/chat-<date>.raw-HHMMSS.xlsx`), converts the new 12-column / time-only format, and rebuilds `chat-<date>.xlsx` as the union of all raw exports of the day (re-exports drop the oldest messages; newest export wins per timestamp+text, so senders he renamed keep the corrected name). `--since HH:MM --out f` lists the new messages. |
| `scripts/recover_grades.py` | Writes missing `<dir>.vN.json` / `.bonus.json` from a workflow `journal.jsonl`, matching results by `submission` or repo URL (graders often skip writing files or the `submission` field, which `merge_grades.py --journal` then misses). |
| `scripts/score_table.py` | `table`: the per-round report table, ordered by posting time (see 6). `whatif --present-min 0.40`: recomputes ClassPulse days with other thresholds and lists mark and certificate changes, without touching the workbook. |
| `scripts/classpulse_fix.py` | uv script **he runs in his terminal** (password prompt): `inspect <dir> <out> <keys…>` dumps roster entries, joins, device requests/approvals and the device of every answer for names/IDs/devices; `move-device <dir> <device> <fromRosterId> <toRosterId>` moves a wrongly approved device and its events to the right learner, re-encrypts, keeps the original in `backup/`, reruns classpulse.py. |
| `templates/course.template.json` | Course settings (rubric, roll-call rules, overrides, grading policy). |
| `templates/RUBRIC.template.md` | Rubric skeleton for code/ML capstones (output JSON includes `missing` keywords for the table). |
| `templates/RUBRIC.productivity.md` | Worked rubric for non-code capstones (files on GitHub/Drive, presentation-file rule, calibration caps). |
| `templates/RUBRIC.agentic.md` | Worked rubric for a code capstone with **no live demo**: individual public GitHub repo, AI-assisted code allowed, demo judged from code + saved run evidence, presentation/analysis judged from README.md, README must cite the course name + link (else presentation ≤ half). |
| `templates/grade.workflow.js` | Workflow script: one Sonnet grader per submission version, then the lenient bonus review of **every** graded version (default; `bonus: false` skips). Copy it to the scratchpad and pass that path as `scriptPath` (the skill folder is not readable by the Workflow tool). |

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

**Attendance**: Name | Email | Chat Name (ClassPulse / Chat Name) | one column per date (`YYYY-MM-DD`) | Attendance = (2×Present + Late) / (2×Days). Marks: Present / Late / Absent / Leave; days not held yet stay blank. **Rows sorted by total attendance descending** (then project, then roster order); **Certificates sorted by المجموع descending**.
- **ClassPulse day cells are formulas**: a learner who joined gets `=answered/total` (e.g. `=4/6`) with the number format `[>=present_min]"Present";[>=late_min]"Late";"Absent"`, so the cell shows the mark and keeps the evidence; **all mark colouring is conditional formatting** (no static fills on mark cells): one rule per status — Present green / Late yellow / Absent red / Leave grey — matching the text or the ratio against the same thresholds, so a mark edited in Excel recolours itself. Conditional fills must set both colours (`PatternFill(fill_type="solid", start_color=c, end_color=c)`): Excel paints a conditional solid fill from bgColor, so an fgColor-only fill shows nothing. Text marks remain for overrides, Leave, days not joined (Absent) and chat days. The Attendance total formula counts both (`COUNTIF "Present"` + `COUNTIF ">=present_min"`, Late likewise). `athkax.py` and `score_table.py` evaluate the ratio through the cell's own number format (openpyxl-written formulas have no cached value), so the thresholds live in the workbook.

**Projects**: Name | Email | Link | Commit | Use case | criteria | bonus | link check (presentation file) | Project % = min(100, sum + bonus) / 100 | Reasoning.

**One sheet per date** `YYYY-MM-DD`: time | user | text (ClassPulse days: the checkpoint log, interleaved by time with that day's `chat-<date>.xlsx` when one exists, trainer rows bold). The user column always shows the **official roster name**: chat and ClassPulse display names are mapped through `aliases.json` / `extras.json`. **Notes**: the rules and every judgment call (lenient days, overrides, adjustments). **Styling**: Arial, blue headers, borders, zebra rows, status colours, frozen headers, filters, ISO dates.

## Attendance rules
**Chat days**
- Present: posted from 1 minute before to 3 minutes after an instructor message containing **تحضير**. Late: posted that day outside every window. Absent: no message.
- Only roll calls present in the export count; never invent windows (`extra_windows` only if he confirms a missing call).
- **Lenient day** (`lenient_days`, only on his request — e.g. the presentation day): any message or a posted project link = Present, no Late.
- Exports are re-made during the day and **drop the oldest messages** (Oct 2026: a learner's only early message vanished and she turned Absent). Always run `chat_day.py <dir> <date>` on each new export so the day's sheet is the union of every export; never build from a single re-export.
- Two learners with the same display name (e.g. "Khaled"): ask him to have them rename; he may correct the export by hand. Map the shared name to whoever keeps it on every day, give the other his own alias, and check that the mapping does not change ClassPulse chat credit on earlier days (it usually doesn't when the messages fall outside open checkpoints).
- Instructor messages that contain تحضير (e.g. "مشكلتك في التحضير") are detected as roll calls; harmless on a lenient day, but on a normal chat day confirm with him which ones were real calls.

**ClassPulse days** (`course.json` → `classpulse`; defaults in brackets)
- Day total = checkpoints with at least one answer; a person's score = unique checkpoints answered across merged identities.
- `chat_checkpoint_credit` (on request): a Webex chat message posted while a checkpoint was open (opening minute to closing minute) counts as answering it. Needs `chat-<date>.xlsx` for each day and the chat names mapped in `aliases.json` first (run `build_workbook.py --check`, map, then rerun `classpulse.py`). A chat-only participant counts as joined that day.
- Present ≥ `present_min` [0.65]; Late ≥ `late_min` [0.25], or with `joined_counts_as_late` anyone who opened the link; Absent: did not join.
- `no_late_days`, `new_batch` {`admitted_day`, `mark_before`, `mark_admitted_day`}, `leave_if_never_present` (never Present anywhere → Leave on every day, chat days included), `leave_if_joined_days_lte` (N: anyone who joined ClassPulse on at most N days gets Leave on every day; 0 = only learners never seen, days not joined stay Absent. For the rule "joined one day only → Leave everywhere, judged at the end" keep 0 during the course and set 1 on the last day; sync with `--no-skip-all-absent`).
- Identities merge on participant id, roster ID or normalised name; `classpulse.aliases` for cross-script duplicates; `exclude` co-trainers. Matching to AthkaX: `aliases.json` → Nafath ID → email → exact name.
- **Hybrid**: a day with no ClassPulse session falls back to that day's chat export automatically. On ClassPulse days the chat export only feeds the date sheet (never the marks); its unmapped names are listed by the build and shown as typed, so map them too (chat names are usually Latin transliterations of the Arabic roster names — resolve by hand, only unambiguous ones).
- Lenient settings used once (Productivity, Oct 2026): `present_min` 0.25, `joined_counts_as_late`, new batch Late before / Present on day 2, `leave_if_never_present`, day 5 = lenient chat day.
- Lenient settings used once (Agentic AI, Oct 2026, decided on the last day): `present_min` 0.40, `late_min` 0.0001 (= at least one checkpoint answered; chat credit counts), day 5 = lenient chat day. Defaults stay 0.65 / 0.25; change them only when he asks, then rerun classpulse.py, rebuild and sync **all** dates.
- **End-of-program Leave rule** (course.json `leave_if_attended_days_lte`, set to 1 on the last day, applied by build_workbook.py): anyone who joined on at most N days over the whole program — a ClassPulse day joined (even with no answer) or a chat day with a message — is Leave on every held day, chat days included; overrides still win. Keep `classpulse.leave_if_joined_days_lte` at 0 (never-seen learners Leave on ClassPulse days during the course). The build prints how many joined-once learners became Leave; sync all dates afterwards.

**Instructor overrides**: `status_overrides` `{"<email>": {"<day number>": "Late"}}` (e.g. an excused absence: the link reached her late; "ClassPulse would not admit me until you fixed it" → Present that day). Listed in Notes. Then sync that date too.

**Attendance claims on the deadline day** ("I attended but it shows Absent / someone else's name"): check `classpulse_marks.json` (`why` per day), then run `classpulse_fix.py inspect` for the claimant and the named person. A device approved under the wrong learner shows as a `p.deviceRequest` + approved `p.device` on the other learner's identity, joining in step with the claimant's own device. Fix with `move-device`, diff `classpulse_marks.json` against the copy in `backup/`, rebuild, and remind him to re-import the fixed backup. Always state the claim's effect on the certificate (e.g. "even at 100% attendance her project is 3 points short").

**What-if thresholds**: when he asks "what if Present were 40%?", run `score_table.py whatif --present-min 0.40` and report only the certificate changes (and anyone whose pending project could flip). Apply nothing until he decides; if he does, set `classpulse.present_min`, rerun classpulse.py (password), rebuild and re-sync **all** ClassPulse dates.

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
3. **Grade** every NEW/CHANGED version with the Workflow tool using `templates/grade.workflow.js` (copied to the scratchpad, `scriptPath`), args `{rubric, subs_root, grades_dir, lenient, items: [{v: "<dir>.vN", url, note}]}` — one **Sonnet** agent per submission, then the bonus review of the same versions. Notes carry context: what changed, previous score and its gaps, "regrade as a new submission", a sub-folder to grade (`/tree/main/<path>` links into a copy of the course repo), team/posted-by-someone-else, a zip inside the repo.
4. `recover_grades.py <grades_dir> <run>/journal.jsonl <v1,v2,…>` (writes grade and bonus files the agents did not), then `merge_grades.py <dir> <grades_dir>`, then build.

**Grading policy (default, Modar):**
- **Lenient bonus up to +10 for every project**: each graded version gets the bonus review (`bonus_max` 10). Final = min(100, criteria + max(grader bonus, review bonus)); the bonus never exceeds 10.
- **Several repos from one student** (e.g. "first submission … and if time permits, a second"): grade all, keep the best score; drop the other from `submissions.json` and note both scores in Notes.
- A repo that later turns **private or deleted** keeps the grade it got while public; tell him so he can ask the student to reopen it.
- A team repo posted by one member is credited to the poster and flagged `team`; a teammate who later posts her own repo is graded on that.
- A link that is not a repository (Codespaces `app.github.dev` preview, slide link): not graded until a repo is posted; note it.
- `submissions.py` handles repo names that really end in "." and Windows long paths (`core.longpaths`); if a clone still fails with a path error, clone by hand with `git -c core.longpaths=true clone` into `<subs_root>/<dir>.vN` and set that version in `submissions_state.json`.
5. **Verify serious claims yourself** before reporting (e.g. a "real metrics" script that only calls `time.sleep`, timings an LLM "computed" for itself, a PDF about someone else's project).
6. Flag without deducting extra: AI-generated disclosures, lab-copy of course packs, one-big-commit uploads, synthetic data.

### 5. Re-check rounds (the deadline day)
Each "check the chat / updates" round ("updated the chat", "check updates"), usually every 10–20 minutes until the deadline:
1. `chat_day.py <dir> <date> --since <last HH:MM>` → read the new messages (exports can land mid-round: if a build fails on "time data 'HH:MM'", a new raw export arrived — rerun `chat_day.py`).
2. Map new chat names (`--check`), add new links to `submissions.json` (with `posted`, `day`, `chat_name`), note attendance claims and questions.
3. `submissions.py check` over **all** links (students update silently) → grade NEW/CHANGED (bonus review included) → `recover_grades.py` → `merge_grades.py` → build → copy into the course folder.
4. `score_table.py table` → report (see 6). Keep the order: attendance first, then grading.
- **Deadline policy** is his: updates before the deadline (and any grace period he grants) are graded as new submissions; he may later accept everything.
- **Extra leniency** (on request, on top of the default +10 bonus review): `grading.keep_higher_on_resubmit` so a resubmission never lowers a score, and `lenient: true` for graders.
- **Instructor adjustments** to pass specific students: `grading.bonus_overrides` (within the bonus cap) and/or `status_overrides`; both are noted in the workbook.

### 6. Build and deliver
- `build_workbook.py <dir> --out <scratch>/new.xlsx`, then copy into the course folder. `Device or resource busy`/`Permission denied` = open in Excel; ask him to close it. Never hand-edit the xlsx; if he edits it, carry his changes into `build_workbook.py`.
- **Report table** (`score_table.py table`), ordered by the time the link was posted in the chat:

  | # | chat name | project score | remaining | notes |
  |---|---|---|---|---|
  | 1 | سها … | 87 | 0 | |
  | 21 | Ziyad … | 46 | 5 | evals.py, tasks.jsonl (≥15), A/B CSVs, error analysis counts, real MCP server |
  | 24 | غاليه … | 66 | — | attendance 50% |

  `remaining` = 0 when the certificate is اجتياز; otherwise the project points still needed to pass; "—" when attendance ≤ 65% (no project can pass). `notes` = short keyword list of what would get them to pass (the grader's `missing`), empty when passing. The first round shows the full table; later rounds show **only the deltas** (new or changed rows; keep the previous `t.md` and `diff` it) plus "everyone else unchanged" and the pass count (e.g. "30 of 37 reach اجتياز"). Post the full table only when he asks.
- Under the table, 3–5 bullets: attendance claims and their effect, links that aren't repos / private / team, unanswered questions from the chat, and anything that needs his decision. Remind him which dates changed and need syncing.
- "Who can still pass?": everyone with حضور — needed project > (65% − 0.3 × attendance) / 0.7 (100% attendance → 50%, 90% → 54.3%, 80% → 58.6%, 70% → 62.9%). At ≤ 50% attendance nobody can pass. A student absent today who posts anything on a lenient day gains attendance.

### 7. Sync attendance to AthkaX (only when he asks)
He runs `uv run athkax.py attendance "<xlsx>" [--date YYYY-MM-DD ...] --dry-run`, then without `--dry-run`.
- `--date` limits the sync to those dates (repeatable); without it every date is synced. Give him the dated command for the day(s) that changed (e.g. today plus an overridden day).
- It reads every learner's current mark per date and plans only differences (`attendance_plan.csv`, `athkax_mismatches.json`); learners absent every day or not on the sheet → `leave`; blank cells untouched. Safe to re-run. If he fears a sync changed something, read `attendance_plan.csv` to show exactly what moved.
- Marks accepted: `unmarked`, `leave`, `absent`, `late`, `present`. Duplicate enrolments (same email, consecutive ids) are all marked.
- Auth: keyring, `ATHKAX_TOKEN` or Nafath. Never store, print or paste a token; never ask for a HAR with headers (if shared, read header names only and tell him to delete it).

**AthkaX API facts**: paths use the program slug and the numeric batch id (`batches/193`); lists paginate with `page=1&perPageItems=12` + `pagination.next`; roster `batches/<id>/batch_learners/attendances?page=N&date=YYYY-MM-DD` → `batchLearners[].id`, `eventLearnerId`, `learnerDetails.{name,email}`, `availabilityByDate.availability`; Nafath ID via `event_learners/<eventLearnerId>` → `learnerNafathId`; mark with `PUT attendances/mark?date=…` body `{"attendance": {"batch_learner_id": …, "availability": …}}`.

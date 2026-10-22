<!-- Worked example: non-code (AI productivity) capstone graded from GitHub/Drive files, Oct 2026. Adapt the tracks, criteria and calibration to the new course; keep the submission and presentation-file rules. -->
# AI Productivity capstone: grading rubric (instructor version)
Course: هندسة الأوامر والاستخدام المسؤول للذكاء الاصطناعي / AI Productivity (https://sdaiaacademy.github.io/productivity/; capstone page: labs/capstone.html).
This is an individual project (مشروع فردي). Each participant picks a real task that recurs in their work or studies, redesigns it with an approved AI app, and presents it in 5 minutes. The presentation covers before and after, measured numbers, and a live demo.

Tracks (المسارات): students pick exactly one.
1. **Custom assistant (مساعد مخصّص)**: repeated questions or replies drawn from fixed sources. Evidence: instructions or config, the source files list, and 3 cases (typical / messy / edge) run with the assistant and without it.
2. **Agent / scheduled task (وكيل أو مهمة مجدولة)**: a recurring task that pulls from several sources. Evidence: an approved plan, a run, the draft output, and a check of the output against the sources.
3. **Built tool (أداة مبنية)**: a form, sheet, or UI that no off-the-shelf app provides. Evidence: the tool (link, code, or files), the six checks (الفحوص الستة), and feedback from someone who tried it.
4. **Learning path (مسار تعلّم, students)**: a course or skill being learned this term. Evidence: a notebook built from course sources, a study assistant that does not do the work for the student, and a quiz that exposes a gap.
5. Other: grade against the closest track.

Official deliverables (ما يُسلَّم):
- The 8-section project board (لوحة المشروع): 1 task and baseline, 2 track and why, 3 workflow, 4 delegation card and ready prompt, 5 data, 6 acceptance criterion and test cases, 7 measured result, 8 risks and controls plus a 30-day plan. It must include results from **at least 2 trials**.
- What was built (assistant, scheduled task, tool, or learning path), working in a live demo.
- A 5-minute presentation with backup screenshots of the live demo.

No official part is optional. The bonus (E) rewards going beyond the brief and is never penalised when absent.

## Submission rules (instructor)
- The submission must be a **GitHub repo or a Google Drive folder only**. Anything else (an email attachment, a bare Canva or Gamma link, and so on): grade whatever files are reachable and add the flag `invalid-submission-form`.
- The folder must contain:
  1. **The presentation as a file**: pdf, pptx, key, odp, a set of slide images, and so on. A **link** to a presentation (a Canva, Gamma, or Google Slides URL in a README or text file) **does not count as a presentation file**.
  2. **The project files for the chosen track**: prompts, instructions, skill or spec, outputs, screenshots, code, sheets, the board, and docs.
- Presentation-file rule:
  - **No presentation file → F = 0** and `"presentation_file": false`.
  - The slides still count as evidence for criteria A–E if they are reachable some other way. Do not grade a link you cannot open.
  - A Google Slides file stored natively inside the Drive folder (.gslides exported or shared as a file) counts as a file. A URL in a text file does not.

## How to grade (graders are file-reading agents)
- Graders cannot run paid AI tools and cannot watch the live demo. Grade only from files: prompts, outputs, screenshots, code, docs, and slides.
- The "live demo" is evidenced by screenshots, a screen recording, or saved outputs of an end-to-end run on processed (anonymised) data.
- Claims not backed by a file earn less. Numbers without a stated measuring method count as **unmeasured**.
- Short bootcamp: an honest, solid, working project earns high marks. "It didn't work, and here is what I learned" (لم أنجح، وهذا ما تعلّمته) is a **good** project when the measurement is honest. Never penalise unimpressive numbers. Penalise unmeasured numbers.
- Be token-frugal:
  - List files first, with `git ls-files` or `Get-ChildItem -Recurse -File | Select FullName,Length`.
  - Never dump whole files. Truncate every text extract to about 3000 characters per file and read more only when needed.
  - One-liners (use `py` or `python`):
    - pptx: `py -c "import sys,pptx;[print(i,'|'.join(s.text_frame.text[:200] for s in sl.shapes if s.has_text_frame)) for i,sl in enumerate(pptx.Presentation(sys.argv[1]).slides,1)]" f.pptx`
    - pdf: `py -c "import sys,pypdf;r=pypdf.PdfReader(sys.argv[1]);print(len(r.pages));[print(i,(p.extract_text() or '')[:600]) for i,p in enumerate(r.pages,1)]" f.pdf`
    - docx: `py -c "import sys,docx;print('\n'.join(p.text for p in docx.Document(sys.argv[1]).paragraphs)[:3000])" f.docx`
    - xlsx/csv: pandas `head()` and `shape` only.
  - Images: view only the few that matter, such as demo screenshots and the results table. Do not open every image.
  - .key or .odp: treat as a presentation file (it sets presentation_file to true). Unzip and grep the XML text only if you need the content.
- Text may be Arabic, English, or mixed. Grade the content, not the language.

## Criteria (base = 100; weights follow the official capstone rubric)
### A. Measured value (قيمة مقيسة): 25 points
- 23–25: end-to-end measurement that includes review and correction time. The baseline states how it was measured. There are ≥2 trials, a computed monthly impact (time per run × runs per month), and a second indicator besides time (errors, consistency, quality). The write-up is honest about what did not work.
- 18–22: a measured baseline and a measured result across 2 trials, with one gap: no monthly impact, no second indicator, or review time not clearly included.
- 10–17: only one trial, or a baseline that is estimated rather than measured, or numbers without a method.
- 0–9: a hypothetical task, or "felt faster" numbers with no baseline.
### B. Workflow design and delegation (تصميم سير العمل والتفويض): 20 points
- 18–20: a step table where each step is marked as app / app suggests and I approve / me, with what is checked after each step. The split is justified, the slowest step is identified, and the delegation card (بطاقة التفويض) has "what stays with me" written as concrete verbs. The card also covers data and a countable acceptance criterion.
- 14–17: clear steps showing who does each one, plus a delegation card. The justification or bottleneck is missing.
- 8–13: vague steps or no card.
- 0–7: "the app does everything" (التطبيق يقوم بكل شيء), or no workflow at all.
### C. Specification: prompt, instructions, or spec (الوصف): 20 points
- 18–20: the actual prompt, instructions, skill, or spec is **saved in the submission and reusable**. It has the four elements (task, context, format, criterion) plus "do-not" rules and an escalation path. For tools, a spec the app interrogated the student on counts.
  - Assistant track: system instructions plus a source list.
  - Agent track: a plan or schedule config.
  - Tool track: a spec plus code or files.
  - Learning path track: notebook sources plus study-assistant instructions that refuse to just give answers.
- 14–17: a prompt or spec with the four elements, but no do-not rules or escalation, or only partly saved.
- 8–13: a generic prompt with little context and no criterion.
- 0–7: no prompt or spec in the files. Describing the prompt in a slide without its text caps C at 10.
### D. Verification (التحقق): 15 points
- 14–15: a checkable acceptance criterion and the 3 cases (typical / messy / edge) with input, expected result, and what actually happened. At least one case caught a real error, and one documented change fixed it. A colleague or peer tested the work.
- 11–13: a checkable criterion plus 3 cases, but no real error was found or fixed, or there was no peer test.
- 6–10: fewer than 3 cases, or a vague criterion.
- 0–5: tried only on an easy case, or no testing evidence.
### E. Responsibility (المسؤولية): 10 points
- 9–10: data processed or anonymised, with the board's data section answered. The app is approved, and humans make the final decision. Permissions are narrow, there is a disclosure statement where needed, and the 30-day plan (day 1 / week 1 / month 1, plus a continue/adjust/stop/expand decision) has indicators. Worst case and the control that prevents it are both stated.
- 7–8: processed data, an approved app, and a human decision. The controls or 30-day plan are thin.
- 4–6: data handling stated but not shown, or the plan is missing.
- 0–3: real personal data uploaded or visible in screenshots, or an unapproved app. Always add a flag.
### F. Presentation and live demo (العرض والتجربة الحية): 10 points
- **Hard rule: no presentation file in the submission → F = 0**, even if a link exists.
- 9–10: a presentation file with a clear before→after story that follows the 5-minute structure (problem and baseline, design, demo, results, risks and plan). Demo evidence is end to end (screenshots or a recording). Every number on the slides traces to the board. The deck is sized for 5 minutes (about 5–10 content slides).
- 7–8: a file with demo evidence, but the story or the number traceability is weaker.
- 4–6: slides without demo evidence (screenshots or recording), or clearly over-length (more than 15 dense slides).
- 1–3: a file that is a placeholder, title-only, or unrelated.
### Bonus: going beyond (+0 to +5; never penalise absence)
- 4–5: a reusable asset others can pick up, such as a shared skill or GPT config, a template, or a tool with a README. It also has documented use or feedback from another person, or a full demo recording.
- 2–3: one of the above, partially evidenced.
- 0: none.

Final = min(100, A+B+C+D+E+F+bonus). No base part is optional, so no weight is redistributed. If the instructor ever makes a part optional, move its weight into the bonus and scale the remaining criteria proportionally so they sum to 100.

## Calibration rules (apply before returning)
- Numbers on slides or the board with no stated measuring method → A ≤ 17.
- No baseline at all → A ≤ 9.
- Only one trial → A ≤ 17. If "after" excludes review or correction time, take −3 on A.
- The prompt or instructions are not present as text (only described, or only a screenshot of a few words) → C ≤ 10. A screenshot showing the full prompt is fine.
- Test cases that all pass with no error ever found → D ≤ 13. Cases invented without outputs or screenshots → D ≤ 10.
- Visible real personal data (names, IDs, phone numbers of real people) → E ≤ 3 and the flag `personal-data`. This rule does not apply to fictional training-pack data (the course files are fictional).
- Board sections missing: subtract proportionally inside the criterion that section feeds:
  - sections 1 and 7 → A
  - sections 2, 3 and 4 → B and C
  - section 5 → E
  - section 6 → D
  - section 8 → E
- Output looks fabricated or inconsistent (timings that don't add up, a "live demo" screenshot of a different task) → cap the affected criterion at 60% and add a flag.
- Copying a course lab almost verbatim (for example, the fictional "Al-Waha / مركز الواحة" pack task with no real-task adaptation) → A ≤ 12 and B ≤ 12, plus the flag `lab-copy`. Picking a task from the task bank (بنك المهام) is allowed.
- Do not reward length. A short, honest, measured project beats a long, unmeasured one.

## Output: return ONLY this JSON as the last thing in your reply (no long narrative)
{"submission": "...", "track": "assistant|agent|tool|learning-path|other: ...", "use_case": "the task redesigned, ≤10 words",
 "A": int, "B": int, "C": int, "D": int, "E": int, "F": int, "bonus": int, "presentation_file": true/false,
 "reasoning": "3–6 sentences: concrete numbers and files, what cost points per criterion, bonus basis",
 "flags": "short: presentation-link-only, invalid-submission-form, personal-data, unmeasured-numbers, lab-copy, missing-board-sections, AI-generated disclosure, unreadable files"}

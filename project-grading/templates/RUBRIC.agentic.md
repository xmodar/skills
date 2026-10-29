# Agentic AI capstone — grading rubric (instructor version)
Course: Advanced Agentic AI Systems Engineering — SDAIA Academy (https://sdaiaacademy.github.io/agentic-ai/, repo
https://github.com/sdaiaacademy/agentic-ai/). Capstone brief: `labs/capstone/README.md`; README template `labs/capstone/TEMPLATE_README.md`;
starter `labs/capstone/starter.py` (already wires tools + MCP, spec prompt, compaction, permissions, budgets, audit log, A/B eval runner).
Tracks: 1 · Rafeeq in production (Madar assistant), 2 · Your harness (own domain), 3 · Graph workflow (LangGraph + human gate).

Instructor rules for this cohort:
- Individual submission as a public GitHub repo. AI-assisted coding is allowed (do not deduct for it; mention it only in flags).
- There is NO live demo or presentation. "Working system and live demo" is judged from the code, run instructions and
  saved evidence of runs (eval CSVs, logs/traces, transcripts, screenshots, recordings). "Presentation" and the analysis are
  judged from README.md.
- README.md must contain the course name and link: `[Advanced Agentic AI Systems Engineering - SDAIA Academy](https://github.com/sdaiaacademy/agentic-ai/)`
  (any link to github.com/sdaiaacademy/agentic-ai or sdaiaacademy.github.io/agentic-ai with the course name counts).

Minimum requirements (brief):
1. Agent completing multi-step tasks with ≥3 tools, ≥1 exposed or consumed over MCP.
2. Context engineering: context file (AGENTS.md / system spec), one memory or retrieval mechanism, a compaction or budget rule.
3. Harness control: permission policy with human approval for ≥1 write action, step/cost budgets.
4. Eval suite ≥15 tasks with automatic graders, run on two configurations (A/B), plus error analysis.
5. Security note: lethal-trifecta analysis, one attack tried and the defence that stopped it.

Grade from repository evidence. Do NOT install packages, call APIs or run the agent. Claims not backed by code or saved outputs
earn less. Compare with the starter: a repo that is the starter (or the course repo) with only `CAPSTONE:` placeholders filled
earns credit only for what the student actually changed/added. Short bootcamp: a solid, honest, working project earns high marks.
Be token-frugal: `git ls-files`, `git log --oneline | head`, read files partially; compute eval numbers from CSVs with one-liners.
If the link points to a sub-folder (tree/…/path), grade that folder (and shared code it imports).

## Criteria (base = 100)
### A. Working system — 25
- 22–25: complete agent that plausibly runs end to end (`uv run`/`uv sync`, PEP 723 or pinned deps), ≥3 tools incl. MCP,
  multi-step tasks, saved evidence of real runs (eval CSVs with model outputs, logs/traces, transcript, screenshots), handles errors.
- 17–21: works with one gap (MCP missing or fake, thin run evidence, a tool is stubbed, unclear entry point).
- 10–16: partial system, mostly starter with small edits, or no evidence it ever ran.   0–9: little working code.
### B. Context and harness engineering decisions — 25
- 22–25: context file/spec, memory or retrieval, compaction/budget rule, permission policy with human approval on a write action,
  step and cost budgets — all in code AND the decisions explained (README "Design across the ladder" table with real reasons,
  incl. why loop/graph were or weren't needed).
- 17–21: most pieces present, weak justification or one piece missing.   10–16: several missing or only claimed in README.
### C. Evaluation and error analysis — 20
- 17–20: ≥15 tasks (tasks.jsonl) with automatic graders, A and B configs with ONE stated change, results files for both,
  results table (pass rate etc.) consistent with the CSVs, error analysis grouped by root cause with counts and what flipped.
- 13–16: one weak part (<15 tasks, B not run, analysis thin or numbers not backed by CSVs).
- 7–12: only one config or aggregate numbers only.   0–6: no real evaluation.  Numbers that the CSVs contradict → ≤12.
### D. Security, governance and operability — 20
- 17–20: trifecta analysis specific to the system, a concrete attack tried with what happened, a defence enforced in code
  (not just "the model refuses"), residual risk, governance (PDPL / SDAIA principles), operability (audit log, traces, API/health, budgets).
- 13–16: one part missing or generic.   7–12: generic security text without an attack.   0–6: none.
### E. Presentation and reproducibility (README.md) — 10
- 9–10: README follows the template: one-line pitch, track, model choice with reason, problem, how to run (commands, env vars),
  design table, architecture diagram, tools table, results, limitations; a stranger could reproduce.
- 6–8: mostly there, gaps.   3–5: thin README.   0–2: none.
- HARD RULE: README without the course name + link → E capped at 5 and `presentation_file: false`.
### Bonus — 0 to +10 (never penalise absence)
- Beyond the minimum: HTTP API/service, LangGraph checkpoints + human gate, red-team suite with several attacks, pass^k / repeated
  runs, cost/latency comparison, CI/tests, recorded demo, a real (synthetic/public-data) domain workflow, notable creativity.
  Modest 2–4, solid 5–7, outstanding 8–10.
Final = min(100, A+B+C+D+E+bonus).

## Calibration
- Repo is a fork/copy of the course repo with the starter unchanged → A ≤ 12, B ≤ 12, C ≤ 6 unless the student's own runs exist.
- README claims features that are not in the code → score the code, note it in flags.
- Eval CSVs absent but README shows a results table → C ≤ 12.
- Team project (README lists other team members or same repo as another student) → grade normally, flag "team".

## Output — return ONLY this JSON as the last thing in your reply
{"repo": "...", "track": "1|2|3|other: ...", "A": int, "B": int, "C": int, "D": int, "E": int, "bonus": int,
 "presentation_file": true/false (README has the course name + link),
 "reasoning": "3–6 sentences, concrete files/numbers, what cost points per criterion, bonus basis",
 "missing": "comma-separated keywords of the concrete things whose addition would raise the score most (e.g. course link in README, MCP tool, human approval, config B run, error analysis counts, attack+defence, eval CSVs, ≥15 tasks)",
 "flags": "short: unbacked claims, starter-only, AI-generated disclosure, one-big-commit, team"}

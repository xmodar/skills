# <Course> capstone — grading rubric (instructor version)
Course: <name> (<site>). Students chose: <use cases>. Starter kit at <path> — compare to judge own work.
Official minimum requirements: <list; mark optional ones "(OPTIONAL — bonus only)">.
Grade from repository evidence: code, README, saved notebook outputs, results files. Do NOT train models or install heavy
packages. Claims not backed by code or saved outputs earn less. Short bootcamp: a solid, honest, working project earns high marks.
Be token-frugal: list files with `git ls-files`, read notebooks via a python one-liner that prints only cell sources/outputs you
need (truncate long outputs), compute metrics with pandas one-liners — never dump whole CSVs/notebooks.

## Criteria (base = 100)
### A. Functional end-to-end — <w> ("Runs live on unseen input; handles errors, abstains gracefully")
- 90–100% of w: complete pipeline + demo (app or notebook UI with saved outputs) on new input; embeddings + decision/generation;
  handles bad/empty input or abstains on low confidence.
- 70–89%: works end to end with one gap (no abstention/error handling, demo on fixed examples only, missing artefact).
- 40–69%: partial pipeline, demo missing/unrunnable, or mostly starter kit.   Below: little working code.
### B. Model selection & implementation — <w> ("Choice justified by quality and latency/cost; clean, modular code")
- 90–100%: baseline + ≥1 improvement on the SAME held-out test set; quality AND latency/cost evidence; modular code beyond starter.
- 70–89%: comparison exists but quality-only, or monolithic notebook.   40–69%: single model / different test sets / validation only.
### C. Evaluation & error analysis — <w> ("Held-out test, baseline, slices (EN/AR), categorized failures")
- 90–100%: held-out test; baseline vs improvement; slices; ≥10 failures grouped into categories WITH counts; ideally CIs.
- 70–89%: one weak part.   40–69%: aggregate metrics only.   Below: no real evaluation.
### D. Presentation & reproducibility — <w> ("README lets a stranger reproduce results")
- setup, data source, commands, pinned deps, sample I/O. HARD RULE: README must link <required link>, else cap D at half.
### E. <optional part> bonus — 0 to +<b> (never penalise absence)
- 80–100% of b: done with before/after on the same test set.   40–67%: evidence-based case for not doing it, or weak comparison.
- 7–33%: attempted without comparison, or justification without evidence.   0: none.
Final = min(100, A+B+C+D+E).

## Calibration rules (apply before returning)
- broken / below-chance fine-tune → E ≤ 5; fine-tuned model compared only to a different baseline → E ≤ 10.
- abstention that never or always fires → −2 on A; error categories assigned mechanically (by language / pre-labelled column) → not real error analysis.
- comparison only on validation or on a test set of a few rows → B in the 40–69% band at most.
- notebook whose saved outputs are errors / cannot run top-to-bottom → A ≤ 80% of w.

## Output — return ONLY this JSON as the last thing in your reply (no long narrative)
{"repo": "...", "use_case": "1|2|3|other: ...", "A": int, "B": int, "C": int, "D": int, "E": int, "sdaia_link": true/false,
 "reasoning": "3–6 sentences, concrete numbers/files, what cost points per criterion, bonus basis",
 "flags": "short: unbacked claims, leakage, AI-generated disclosure, one-big-commit, missing files, team names"}

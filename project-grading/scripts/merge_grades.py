"""Merge grader outputs into grades.json (the file build_workbook.py reads).

    python -I merge_grades.py <course_dir> <grades_dir> [--journal <workflow journal.jsonl> ...]

Reads <course_dir>/submissions.json + submissions_state.json (from submissions.py) and, for each submission, the grade
file of its CURRENT version: <grades_dir>/<dir>.v<N>.json (rubric JSON: one integer per criterion letter A, B, ...,
"bonus", "presentation_file", "use_case"/"track", "reasoning", "flags"). Optional <dir>.v<N>.bonus.json
({"bonus": int, "reason": str}) from a bonus-review pass raises the bonus (never lowers it).

--journal recovers grade/bonus JSON that workflow agents returned but did not write to disk.

course.json "grading" (all optional):
  "keep_higher_on_resubmit": true   a resubmission keeps the higher criteria total of all its versions (lenient)
  "bonus_max": 10                   cap for any bonus
  "bonus_overrides": {"<student>": 7, ...}   instructor adjustments (applied last, noted in the reasoning)
  "notes": {"<student>": "text appended to the reasoning"}
Ungraded submissions (private / empty / unreachable, no earlier version) get "scores": null with the reason.
Prints one ASCII summary line; details go to grades.json.
"""
import argparse, glob, json, os, re, sys


def load(p, default=None):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else default


def recover(journals, gdir):
    n = 0
    for jp in journals:
        for line in open(jp, encoding="utf-8"):
            o = json.loads(line)
            if o.get("type") != "result":
                continue
            v = o.get("value", o.get("result"))
            items = v if isinstance(v, list) else [v]
            for it in items:
                if isinstance(it, dict) and "results" in it:
                    items += it["results"]
                    continue
                s = it if isinstance(it, str) else json.dumps(it, ensure_ascii=False)
                m = re.search(r'\{\s*"submission".*\}', s, re.S)
                if not m:
                    continue
                try:
                    j = json.loads(m.group(0))
                except json.JSONDecodeError:
                    continue
                name = j["submission"] + (".bonus" if "A" not in j and "bonus" in j else "")
                p = os.path.join(gdir, name + ".json")
                if not os.path.exists(p):
                    json.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False)
                    n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("course")
    ap.add_argument("grades_dir")
    ap.add_argument("--journal", action="append", default=[])
    a = ap.parse_args()
    cfg = load(os.path.join(a.course, "course.json"), {})
    gcfg = cfg.get("grading", {})
    letters = "ABCDEFGHIJ"[:len((cfg.get("rubric") or {}).get("criteria", [])) or 6]
    bmax = gcfg.get("bonus_max", ((cfg.get("rubric") or {}).get("bonus") or [None, 10])[1])
    subs = load(os.path.join(a.course, "submissions.json"), {})
    state = load(os.path.join(a.course, "submissions_state.json"), {})
    rec = recover(a.journal, a.grades_dir)
    out, missing, ungraded = [], [], 0
    for d, sub in subs.items():
        st = state.get(d, {})
        who = sub["student"]
        base = {"student": who, "link": sub["link"], "submitted_day": sub.get("day"), "bonus": 0}
        v = st.get("version")
        if not v:
            ungraded += 1
            why = {"private": "the link is private (access denied); ask the student to share it as 'Anyone with the link'",
                   "empty": "the folder has no files yet", "error": "the link could not be downloaded"}.get(st.get("status"), "not fetched yet")
            out.append(base | {"commit": st.get("status", "-"), "use_case": "-", "scores": None, "link_ok": False,
                               "reasoning": f"Not graded: {why}. {st.get('last_problem', '')}".strip()})
            continue
        g = load(os.path.join(a.grades_dir, f"{d}.v{v}.json"))
        if not g:
            missing.append(f"{d}.v{v}")
            continue
        scores = [int(g[k]) for k in letters]
        reasoning = g.get("reasoning", "")
        if v > 1:
            reasoning = f"Regraded as a new submission (version {v}{', posted ' + sub['posted'] if sub.get('posted') else ''}). " + reasoning
        if gcfg.get("keep_higher_on_resubmit"):
            for pv in range(1, v):
                pg = load(os.path.join(a.grades_dir, f"{d}.v{pv}.json"))
                if pg and sum(int(pg[k]) for k in letters) > sum(scores):
                    reasoning += f" Lenient policy: kept the higher criteria total {sum(int(pg[k]) for k in letters)} of version {pv} instead of {sum(scores)}."
                    scores = [int(pg[k]) for k in letters]
        bonus = min(bmax, int(g.get("bonus") or 0))
        b = load(os.path.join(a.grades_dir, f"{d}.v{v}.bonus.json"))
        if b and int(b["bonus"]) > bonus:
            bonus = min(bmax, int(b["bonus"]))
            reasoning += f" Bonus +{bonus} (bonus review): {b.get('reason', '')}"
        if who in gcfg.get("bonus_overrides", {}):
            nb = int(gcfg["bonus_overrides"][who])
            reasoning += f" Instructor adjustment: bonus set to +{nb} (was +{bonus})."
            bonus = nb
        if g.get("flags"):
            reasoning += f" Flags: {g['flags']}"
        if gcfg.get("notes", {}).get(who):
            reasoning += " " + gcfg["notes"][who]
        out.append(base | {"commit": st.get("fingerprint", "-")[:7] if "github" in sub["link"] else "drive",
                           "use_case": ": ".join(str(x) for x in (g.get("track"), g.get("use_case")) if x) or "-",
                           "scores": scores, "bonus": bonus, "link_ok": bool(g.get("presentation_file", g.get("link_ok", True))),
                           "reasoning": reasoning})
    json.dump(out, open(os.path.join(a.course, "grades.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"grades.json: {len(out)} entries | graded {len(out) - ungraded} | ungraded {ungraded} | recovered from journal {rec}"
          + (f" | MISSING grade files: {', '.join(missing)}" if missing else ""))
    if missing:
        sys.exit(2)


if __name__ == "__main__":
    main()

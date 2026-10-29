"""Write grade and bonus files from a grade.workflow.js run's journal when the agents did not write them.

    python -I recover_grades.py <grades_dir> <journal.jsonl> <dir.vN>[,<dir.vN>...]

Graders often return the rubric JSON without writing <grades_dir>/<dir>.vN.json, or without its "submission" field
(merge_grades.py --journal then misses them). This matches each returned rubric JSON to one of the given versions by
"submission" or by the repo URL, writes the missing files, and writes <dir>.vN.bonus.json from the bonus phase
({"results": [...]}). Existing grade files are kept. Prints one line per version: grade? bonus?
"""
import json, os, re, sys

G, J, vs = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
dec = json.JSONDecoder()
key = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
base = {v: key(v.rsplit(".v", 1)[0]) for v in vs}

for line in open(J, encoding="utf-8"):
    j = json.loads(line)
    if j.get("type") != "result":
        continue
    r = j.get("result")
    r = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
    try:
        x = json.loads(r)
        if isinstance(x, list):
            x = {"results": x}
        if isinstance(x, dict) and "results" in x:
            for b in x["results"]:
                json.dump({"bonus": b["bonus"], "reason": b["reason"]},
                          open(os.path.join(G, b["submission"] + ".bonus.json"), "w", encoding="utf-8"), ensure_ascii=False)
            continue
    except (ValueError, KeyError, TypeError):
        pass
    best = None
    for m in re.finditer(r"\{", r):
        try:
            o, _ = dec.raw_decode(r[m.start():])
        except ValueError:
            continue
        if isinstance(o, dict) and "A" in o:
            best = o
    if not best:
        continue
    v = best.get("submission")
    if v not in vs:
        repo = key(re.sub(r"\.git$", "", best.get("repo", "").replace("https://github.com/", "").split("/tree/")[0]))
        hits = [v for v, b in base.items() if repo and (b == repo or b.startswith(repo) or repo.startswith(b))]
        v = hits[0] if len(hits) == 1 else None
    if not v:
        print("unmatched result:", best.get("repo"))
        continue
    p = os.path.join(G, v + ".json")
    if not os.path.exists(p):
        best["submission"] = v
        json.dump(best, open(p, "w", encoding="utf-8"), ensure_ascii=False)
for v in vs:
    print(v, "grade" if os.path.exists(os.path.join(G, v + ".json")) else "NO GRADE",
          "bonus" if os.path.exists(os.path.join(G, v + ".bonus.json")) else "no bonus")

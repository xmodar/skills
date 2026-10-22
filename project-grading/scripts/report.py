"""Instructor-facing summaries. Output goes to UTF-8 files (Windows consoles mangle Arabic); stdout gets one ASCII line.

    python -I report.py chat   <course_dir> <chat-YYYY-MM-DD.xlsx> <out_dir>
        New messages since the previous run (with their links), and messages still waiting for an instructor reply.
        -> <out_dir>/chat_new.txt, <out_dir>/chat_unreplied.txt ; snapshot kept in <out_dir>/<chat name>.last.txt
    python -I report.py status <course_dir> <workbook.xlsx> <out_dir>
        Every learner: project, attendance, total, certificate, and the project score still needed for اجتياز.
        -> <out_dir>/status.txt (sorted by certificate then total)

Webex exports put a threaded reply directly under its parent, so "unreplied" = a learner message with a link or a
question that is not followed by an instructor message. Exports can drop the oldest messages; compare snapshots, not
line counts.
"""
import json, os, re, sys

import openpyxl

LINK = re.compile(r"https?://\S+")


def chat(course, xlsx, out):
    cfg = json.load(open(os.path.join(course, "course.json"), encoding="utf-8"))
    instr = set(cfg.get("instructor_chat_names", []))
    rows = [r for r in openpyxl.load_workbook(xlsx, read_only=True).active.iter_rows(min_row=2, values_only=True) if r and r[1]]
    lines = [f"{str(r[0])[:16]}\t{r[1]}\t{str(r[2] or '').replace(chr(10), ' / ')}" for r in rows]
    snap = os.path.join(out, os.path.basename(xlsx) + ".last.txt")
    prev = set(open(snap, encoding="utf-8").read().splitlines()) if os.path.exists(snap) else set()
    new = [l for l in lines if l not in prev]
    with open(os.path.join(out, "chat_new.txt"), "w", encoding="utf-8") as f:
        for l in new:
            t, u, txt = l.split("\t", 2)
            f.write(l + ("\n    links: " + " ".join(LINK.findall(txt)) if LINK.search(txt) else "") + "\n")
    last = {}                                                # learner -> their latest link/question and whether it got a reply
    for i, (t, u, txt) in enumerate(l.split("\t", 2) for l in lines):
        if u in instr or not (LINK.search(txt) or "?" in txt or "؟" in txt):
            continue
        nxt = lines[i + 1].split("\t", 2)[1] if i + 1 < len(lines) else None
        last[u] = (nxt in instr, f"{t}\t{u}\t{txt[:200]}")
    waiting = [line for replied, line in last.values() if not replied]
    open(os.path.join(out, "chat_unreplied.txt"), "w", encoding="utf-8").write("\n".join(waiting))
    open(snap, "w", encoding="utf-8").write("\n".join(lines))
    print(f"chat: {len(lines)} messages | new {len(new)} ({sum(bool(LINK.search(l)) for l in new)} with links) | waiting for reply {len(waiting)}")


def status(course, xlsx, out):
    extras = json.load(open(os.path.join(course, "extras.json"), encoding="utf-8")) if os.path.exists(os.path.join(course, "extras.json")) else {}
    xname = {v["name"]: f"+{k}" for k, v in extras.items()}
    grades = {g["student"]: g for g in json.load(open(os.path.join(course, "grades.json"), encoding="utf-8"))}
    ws = openpyxl.load_workbook(xlsx)["Attendance"]
    head = [c.value for c in ws[1]]
    dcols = [i for i, h in enumerate(head) if isinstance(h, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", h)]
    rows, counts = [], {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r[0]:
            continue
        marks = [r[i] or "" for i in dcols]
        att = (2 * marks.count("Present") + marks.count("Late")) / (2 * len(dcols))
        g = grades.get(r[1]) or grades.get(xname.get(r[0]))
        proj = min(100, sum(g["scores"]) + (g.get("bonus") or 0)) if g and g.get("scores") else 0
        sub = "-" if not g else ("ungraded" if g.get("scores") is None else "yes")
        tot = 0.7 * proj + 30 * att
        cert = "اجتياز" if tot > 65 and att > 0.65 else "حضور" if att > 0.65 else "بدون"
        if cert == "بدون" and sub == "-" and not any(m in ("Present", "Late") for m in marks):
            continue                                         # never attended, never submitted: not worth listing
        counts[cert] = counts.get(cert, 0) + 1
        need = (65 - 30 * att) / 0.7
        rows.append((cert, -tot, f"{r[0]} | project {proj}% | attendance {att:.0%} | total {tot:.1f}% | {cert}"
                     + (f" | needs project > {need:.1f}%" if cert != "اجتياز" and need <= 100 else "") + f" | submission {sub} | {''.join(m[:1] or '.' for m in marks)}"))
    order = {"اجتياز": 0, "حضور": 1, "بدون": 2}
    rows.sort(key=lambda x: (order[x[0]], x[1]))
    open(os.path.join(out, "status.txt"), "w", encoding="utf-8").write("\n".join(x[2] for x in rows))
    print(f"status: pass {counts.get('اجتياز', 0)} | attendance-only {counts.get('حضور', 0)} | none {counts.get('بدون', 0)} -> status.txt")


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:]
    {"chat": chat, "status": status}[cmd](*rest)

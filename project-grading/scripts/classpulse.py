#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "cryptography>=42",
# ]
# ///
"""ClassPulse → attendance marks for the project-grading workbook.

    uv run classpulse.py COURSE_DIR [--backup FILE.cpbackup]

Reads the newest ClassPulse backup in COURSE_DIR (`classpulse-*.cpbackup`, or --backup) — a single backup holds
every session of the course — and writes COURSE_DIR/classpulse_marks.json, which build_workbook.py uses instead of
the chat exports. Rules come from the "classpulse" block of course.json (see templates/course.template.json).

Password: CLASSPULSE_PASSWORD environment variable, otherwise prompted. It is never written to disk.

Method:
- A session belongs to the course day of its start date (local time, `utc_offset_hours`, default +3).
- Only checkpoints that received at least one answer count toward the day's total.
- One person can appear several times (several devices, a missing or mistyped roster ID, Arabic vs English name).
  Identities are merged when they share a ClassPulse participant id, a roster ID or a normalised name, plus the
  manual `aliases`; each checkpoint answered by any of their identities counts once.
- Rejected or never-admitted joins are kept as "tried to join" evidence; `exclude` drops people (e.g. co-trainers).
"""
import argparse
import base64
import datetime as dt
import getpass
import glob
import json
import os
import re
import sys
import zlib

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

RANK = ["Absent", "Leave", "Late", "Present"]


def norm(s):
    s = re.sub(r"[ً-ْـ]", "", str(s or ""))  # strip tashkeel/tatweel
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", s).strip().lower()


def b64u(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def decrypt(path, password):
    """Envelope {format: classpulse-backup, salt, iter, data}: PBKDF2-SHA256 → AES-256-GCM(iv‖ct‖tag) → raw deflate → JSON."""
    with open(path, encoding="utf-8") as f:
        env = json.load(f)
    if env.get("format") != "classpulse-backup":
        raise SystemExit(f"{os.path.basename(path)} is not a ClassPulse backup")
    key = PBKDF2HMAC(hashes.SHA256(), 32, b64u(env["salt"]), env.get("iter", 310_000)).derive(password.encode())
    blob = b64u(env["data"])
    try:
        plain = AESGCM(key).decrypt(blob[:12], blob[12:], None)
    except Exception:  # noqa: BLE001
        raise SystemExit("Wrong ClassPulse password or damaged backup")
    data = json.loads(zlib.decompress(plain, -15))
    if data.get("format") != "classpulse-data":
        raise SystemExit("Unexpected backup contents")
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("course_dir")
    ap.add_argument("--backup", help="backup file (default: newest classpulse-*.cpbackup in COURSE_DIR)")
    a = ap.parse_args()
    D = a.course_dir
    load = lambda n, d=None: json.load(open(os.path.join(D, n), encoding="utf-8")) if os.path.exists(os.path.join(D, n)) else d
    cfg = load("course.json", {})
    prog = load("program.json", {})
    cp = cfg.get("classpulse", {})
    days = cfg.get("days") or prog.get("days") or []
    if not days:
        raise SystemExit("No course days (program.json or course.json 'days')")

    backup = a.backup or max(glob.glob(os.path.join(D, "classpulse-*.cpbackup")), key=os.path.getmtime, default=None)
    if not backup:
        raise SystemExit("No classpulse-*.cpbackup in the course folder")
    data = decrypt(backup, os.environ.get("CLASSPULSE_PASSWORD") or getpass.getpass("ClassPulse backup password: "))

    off = dt.timedelta(hours=cp.get("utc_offset_hours", 3))
    local = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc) + off
    by_day = {}
    for s in data["sessions"]:
        if s.get("startedAt"):
            d = local(s["startedAt"]).date().isoformat()
            if d in days:
                by_day.setdefault(d, []).append(s["id"])
    held = [d for d in days if d in by_day]
    present_min = cp.get("present_min", 0.65)
    late_min = cp.get("late_min", 0.25)
    joined_late = cp.get("joined_counts_as_late", False)
    no_late = {days[i - 1] for i in cp.get("no_late_days", [])}
    nb = cp.get("new_batch") or {}
    nb_day = days[nb["admitted_day"] - 1] if nb.get("admitted_day") else None
    exclude = {norm(x) for x in cp.get("exclude", [])}
    alias = {norm(k): norm(v) for k, v in cp.get("aliases", {}).items()}
    nkey = lambda n: alias.get(norm(n), norm(n))

    # ---- one entry per (day, ClassPulse participant)
    ents, totals, logs = [], {}, {}
    for d in held:
        sids = set(by_day[d])
        ev = sorted((e for e in data["events"] if e.get("sessionId") in sids), key=lambda e: e["t"])
        P, st, R = {}, {}, {}
        for e in ev:
            if e["type"] == "p.join":
                P[e["p"]["id"]] = e["p"]
            elif e["type"] in ("p.admit", "p.reject"):
                st[e["pid"]] = "admitted" if e["type"] == "p.admit" else "rejected"
            elif e["type"] == "resp":
                R.setdefault(e["r"]["cp"], set()).add(e["r"]["pid"])
        cps = [e for e in ev if e["type"] == "cp.open" and R.get(e["id"])]
        totals[d] = len(cps)
        num = {o["id"]: (i, o) for i, o in enumerate(cps, 1)}
        hm = lambda ms: local(ms).strftime("%H:%M")
        logs[d] = []
        for e in ev:
            if e["type"] == "cp.open" and e["id"] in num:
                logs[d].append([hm(e["t"]), "Trainer", f"Checkpoint {num[e['id']][0]} opened ({e.get('adhoc') or e['q'].get('type')})", True])
            elif e["type"] == "resp" and e["r"]["cp"] in num:
                i, o = num[e["r"]["cp"]]
                opts, ans = o["q"].get("options") or [], e["r"].get("answer")
                label = opts[ans] if isinstance(ans, int) and 0 <= ans < len(opts) else json.dumps(ans, ensure_ascii=False)
                who = (P.get(e["r"]["pid"]) or {}).get("name", e["r"]["pid"]).strip()
                if norm(who) not in exclude:
                    logs[d].append([hm(e["t"]), who, f"Checkpoint {i}: {label}", False])
        for p in P.values():
            if norm(p["name"]) in exclude:
                continue
            ents.append({"day": d, "pid": p["id"], "rid": (p.get("rosterId") or "").strip(),
                         "name": re.sub(r"\s+", " ", p["name"]).strip(), "known": bool(p.get("known")),
                         "status": st.get(p["id"], p.get("status")),
                         "cps": {o["id"] for o in cps if p["id"] in R[o["id"]]}})

    # ---- merge identities (union-find over participant id, roster ID, normalised name)
    par = list(range(len(ents)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    seen = {}
    for i, e in enumerate(ents):
        for k in filter(None, ["p:" + e["pid"], "n:" + nkey(e["name"]), "i:" + e["rid"].lower() if e["rid"] else None]):
            if k in seen:
                par[find(i)] = find(seen[k])
            else:
                seen[k] = i
    groups = {}
    for i, e in enumerate(ents):
        groups.setdefault(find(i), []).append(e)

    people = []
    for g in groups.values():
        best = sorted(g, key=lambda e: (e["status"] == "rejected", not e["rid"], not e["known"], -len(e["cps"])))[0]
        p = {"name": best["name"], "rosterIds": list(dict.fromkeys(e["rid"] for e in g if e["rid"])),
             "names": list(dict.fromkeys(e["name"] for e in g)), "days": {}, "marks": {}, "why": {}}
        for d in held:
            es = [e for e in g if e["day"] == d]
            if es:
                answered = len(set().union(*(e["cps"] for e in es)))
                p["days"][d] = {"answered": answered, "total": totals[d], "admitted": any(e["status"] == "admitted" for e in es)}
        new_batch = bool(nb_day) and not any(d in p["days"] for d in held if d < nb_day) and nb_day in p["days"]
        for d in held:
            x = p["days"].get(d)
            r = x["answered"] / x["total"] if x and x["total"] else 0
            if x and r >= present_min:
                m, why = "Present", f"{x['answered']}/{x['total']} answered"
            elif x and new_batch and d == nb_day and nb.get("mark_admitted_day"):
                m, why = nb["mark_admitted_day"], f"new batch admitted late ({x['answered']}/{x['total']} answered)"
            elif x and r >= late_min:
                m, why = ("Present", f"{x['answered']}/{x['total']} answered (no-Late day)") if d in no_late else ("Late", f"{x['answered']}/{x['total']} answered")
            elif x and joined_late:
                m, why = "Late", f"joined, {x['answered']}/{x['total']} answered" + ("" if x["admitted"] else " (never admitted)")
            elif not x and new_batch and d < nb_day and nb.get("mark_before"):
                m, why = nb["mark_before"], "new batch (not enrolled yet)"
            else:
                m, why = "Absent", "did not join" if not x else f"{x['answered']}/{x['total']} answered"
            p["marks"][d], p["why"][d] = m, why
        if cp.get("leave_if_never_present") and held and all(p["marks"][d] != "Present" for d in held):
            for d in held:
                p["why"][d] += f"; {p['marks'][d]} → Leave (never Present)"
                p["marks"][d] = "Leave"
        people.append(p)

    out = {"source": os.path.basename(backup), "days": held, "totals": totals, "people": people, "logs": logs}
    with open(os.path.join(D, "classpulse_marks.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    cnt = {d: {} for d in held}
    for p in people:
        for d in held:
            cnt[d][p["marks"][d]] = cnt[d].get(p["marks"][d], 0) + 1
    merged = sum(1 for p in people if len(p["names"]) > 1 or len(p["rosterIds"]) > 1)
    print(f"classpulse_marks.json: {len(people)} people ({merged} merged) | checkpoints {totals} | " +
          " | ".join(f"{d} " + " ".join(f"{k} {v}" for k, v in sorted(c.items())) for d, c in cnt.items()))
    missing = [d for d in days if d not in by_day and d <= max(held, default="")]
    if missing:
        print("no ClassPulse session on:", ", ".join(missing))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "cryptography>=42",
#   "openpyxl>=3.1",
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
- `chat_checkpoint_credit`: a Webex chat message (chat-<date>.xlsx) posted while a checkpoint was open counts as answering
  it (minute resolution: from the opening minute to the closing minute). Chat names are matched with aliases.json /
  students.json / extras.json (the same files build_workbook.py uses) or an exact ClassPulse/roster name.
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

import openpyxl

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
    # per-day rules: "day_overrides": {"1,2,3": {"present_min": 0.25, "joined_counts_as_late": true}} (1-based days)
    over = {}
    for ks, v in cp.get("day_overrides", {}).items():
        for k in str(ks).split(","):
            over[days[int(k) - 1]] = v
    rule = lambda d, k, default: over.get(d, {}).get(k, cp.get(k, default))
    no_late = {days[i - 1] for i in cp.get("no_late_days", [])}
    nb = cp.get("new_batch") or {}
    nb_day = days[nb["admitted_day"] - 1] if nb.get("admitted_day") else None
    exclude = {norm(x) for x in cp.get("exclude", [])}
    alias = {norm(k): norm(v) for k, v in cp.get("aliases", {}).items()}
    nkey = lambda n: alias.get(norm(n), norm(n))

    # ---- one entry per (day, ClassPulse participant)
    ents, totals, logs, wins = [], {}, {}, {}
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
        # checkpoint windows in local minutes: opening minute .. closing minute (no close: next opening or session end)
        minute = lambda ms: local(ms).replace(second=0, microsecond=0, tzinfo=None)
        opens = [e for e in ev if e["type"] == "cp.open"]
        stop = max((e["t"] for e in ev), default=0)
        wins[d] = []
        for o in cps:
            close = next((e["t"] for e in ev if e["type"] == "cp.close" and e.get("cp") == o["id"] and e["t"] >= o["t"]), None)
            nxt = next((e["t"] for e in opens if e["t"] > o["t"]), stop)
            wins[d].append((o["id"], minute(o["t"]), minute(close if close is not None else nxt)))
        num = {o["id"]: (i, o) for i, o in enumerate(cps, 1)}
        hm = lambda ms: local(ms).strftime("%H:%M:%S")
        # the full event log of the day: [time, who, text, by trainer, event type, device]
        logs[d] = []
        name = lambda pid: (P.get(pid) or {}).get("name", pid).strip()
        for e in ev:
            t, ty = hm(e["t"]), e["type"]
            if ty == "cp.open":
                i = num[e["id"]][0] if e["id"] in num else "(no answers)"
                logs[d].append([t, "Trainer", f"Checkpoint {i} opened ({e.get('adhoc') or e['q'].get('type')}): "
                                f"{e['q'].get('text') or e['q'].get('title') or ''}".rstrip(": "), True, ty, None])
            elif ty == "cp.close":
                i = num[e["cp"]][0] if e.get("cp") in num else "(no answers)"
                logs[d].append([t, "Trainer", f"Checkpoint {i} closed", True, ty, None])
            elif ty == "resp" and e["r"]["cp"] in num:
                i, o = num[e["r"]["cp"]]
                opts, ans = o["q"].get("options") or [], e["r"].get("answer")
                label = opts[ans] if isinstance(ans, int) and 0 <= ans < len(opts) else json.dumps(ans, ensure_ascii=False)
                if norm(name(e["r"]["pid"])) not in exclude:
                    logs[d].append([t, name(e["r"]["pid"]), f"Checkpoint {i}: {label}", False, ty, e["r"].get("device")])
            elif ty == "p.join" and norm(e["p"]["name"]) not in exclude:
                p = e["p"]
                logs[d].append([t, p["name"].strip(), f"joined (roster ID {p.get('rosterId') or '-'}, "
                                f"{'mobile' if p.get('mobile') else 'desktop'})", False, ty, ", ".join(p.get("devices") or []) or None])
            elif ty in ("p.admit", "p.reject", "p.device", "p.deviceRequest") and norm(name(e.get("pid"))) not in exclude:
                txt = {"p.admit": "admitted by the trainer", "p.reject": "rejected by the trainer",
                       "p.deviceRequest": "asked to add a device",
                       "p.device": f"device {'approved' if e.get('approved') else 'refused'} by the trainer"}[ty]
                logs[d].append([t, name(e.get("pid")), txt, False, ty, e.get("device")])
        for p in P.values():
            if norm(p["name"]) in exclude:
                continue
            ents.append({"day": d, "pid": p["id"], "rid": (p.get("rosterId") or "").strip(),
                         "name": re.sub(r"\s+", " ", p["name"]).strip(), "known": bool(p.get("known")),
                         "status": st.get(p["id"], p.get("status")),
                         "cps": {o["id"] for o in cps if p["id"] in R[o["id"]]}})

    # ---- chat credit: a chat message during an open checkpoint counts as answering it (pseudo-entries, merged below)
    chat_log = {"credited": {}, "unmatched": {}}
    if cp.get("chat_checkpoint_credit"):
        roster = load("students.json", [])
        aliases, extras = load("aliases.json", {}), load("extras.json", {})
        instr = set(cfg.get("instructor_chat_names", ["SDAIA Academy"])) | {"Trainer"}
        r_email = {(s.get("email") or "").strip().lower(): s for s in roster if s.get("email")}
        r_name = {norm(s["name"]): s for s in roster if s.get("name")}
        cp_names = {nkey(e["name"]) for e in ents}

        def target(u):
            """(roster ID, name) for a chat name, or None."""
            ref = str(aliases.get(u, ""))
            s = None
            if ref.startswith("#"):
                s = roster[int(ref[1:])] if ref[1:].isdigit() and int(ref[1:]) < len(roster) else None
            elif ref.startswith("+"):
                x = extras.get(ref[1:])
                return (None, x["name"]) if x else None
            elif ref:
                s = r_email.get(ref.strip().lower()) or r_name.get(norm(ref))
            else:
                s = r_name.get(norm(u))
                if not s and nkey(u) in cp_names:
                    return (None, u)
            return (str(s.get("nafath") or "").strip() or None, s["name"]) if s else None

        for d in held:
            f = os.path.join(D, f"chat-{d}.xlsx")
            if not os.path.exists(f):
                continue
            got = {}
            for row in openpyxl.load_workbook(f, read_only=True).worksheets[0].iter_rows(min_row=2, values_only=True):
                if not row or not row[0] or not row[1] or row[1] in instr or norm(row[1]) in exclude:
                    continue
                t = dt.datetime.strptime(str(row[0])[:16], "%Y-%m-%d %H:%M")
                hit = {cid for cid, a, b in wins[d] if a <= t <= b}
                if not hit:
                    continue
                tg = target(row[1])
                if not tg:
                    chat_log["unmatched"].setdefault(row[1], set()).add(d)
                    continue
                got.setdefault(tg, set()).update(hit)
            for (rid, name), hit in got.items():
                ents.append({"day": d, "pid": "chat:" + (rid or norm(name)), "rid": rid or "", "name": name, "known": True,
                             "status": "admitted", "cps": hit, "chat": True})
            chat_log["credited"][d] = len(got)

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
                cps_all = set().union(*(e["cps"] for e in es))
                via_chat = len(cps_all - set().union(set(), *(e["cps"] for e in es if not e.get("chat"))))
                p["days"][d] = {"answered": len(cps_all), "total": totals[d], "admitted": any(e["status"] == "admitted" for e in es),
                                "via_chat": via_chat}
        new_batch = bool(nb_day) and not any(d in p["days"] for d in held if d < nb_day) and nb_day in p["days"]
        for d in held:
            present_min, late_min = rule(d, "present_min", 0.65), rule(d, "late_min", 0.25)
            joined_late = rule(d, "joined_counts_as_late", False)
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
            if x and x.get("via_chat"):
                why += f" ({x['via_chat']} via chat)"
            p["marks"][d], p["why"][d] = m, why
        if cp.get("leave_if_never_present") and held and all(p["marks"][d] != "Present" for d in held):
            for d in held:
                p["why"][d] += f"; {p['marks'][d]} → Leave (never Present)"
                p["marks"][d] = "Leave"
        # leave_if_joined_days_lte: N → people who joined ClassPulse on at most N days get Leave on every held day
        # (0 = only those never seen; the instructor raises it at program end, e.g. 1 = "joined one day only → Leave everywhere")
        lte = cp.get("leave_if_joined_days_lte")
        if lte is not None and held and len(p["days"]) <= int(lte):
            for d in held:
                p["why"][d] += f"; joined {len(p['days'])} day(s) → Leave"
                p["marks"][d] = "Leave"
        people.append(p)

    for p in people:                                   # pseudo chat identities are not display names
        p["names"] = [n for n in p["names"] if n] or p["names"]
    out = {"source": os.path.basename(backup), "days": held, "totals": totals, "people": people, "logs": logs,
           "chat_credit": {"people_per_day": chat_log["credited"],
                           "unmatched": {u: sorted(ds) for u, ds in chat_log["unmatched"].items()}}}
    with open(os.path.join(D, "classpulse_marks.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    cnt = {d: {} for d in held}
    for p in people:
        for d in held:
            cnt[d][p["marks"][d]] = cnt[d].get(p["marks"][d], 0) + 1
    merged = sum(1 for p in people if len(p["names"]) > 1 or len(p["rosterIds"]) > 1)
    print(f"classpulse_marks.json: {len(people)} people ({merged} merged) | checkpoints {totals} | " +
          " | ".join(f"{d} " + " ".join(f"{k} {v}" for k, v in sorted(c.items())) for d, c in cnt.items()))
    if cp.get("chat_checkpoint_credit"):
        gained = {d: sum(1 for p in people if p["days"].get(d, {}).get("via_chat")) for d in held}
        print("chat credit: people with checkpoints gained via chat per day", gained,
              "| unmatched chat names during checkpoints:", {u: sorted(ds) for u, ds in chat_log["unmatched"].items()} or "none")
    missing = [d for d in days if d not in by_day and d <= max(held, default="")]
    if missing:
        print("no ClassPulse session on:", ", ".join(missing))


if __name__ == "__main__":
    sys.exit(main())

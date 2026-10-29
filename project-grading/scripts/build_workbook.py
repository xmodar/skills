#!/usr/bin/env python3
"""Build the course grading workbook (Certificates, Attendance, Projects, one sheet per course date, Notes).

Usage:
    python build_workbook.py COURSE_DIR [--out OUT.xlsx] [--check]

COURSE_DIR must contain:
    course.json   - course settings and rubric (see SKILL.md); program fields may come from program.json
    students.json - roster: [{"name": ..., "email": ...}, ...] (`athkax.py roster` adds "id" and "nafath")
and one attendance source:
    chat-YYYY-MM-DD.xlsx   - one Webex chat export per day (columns: timestamp | user | text), or
    classpulse_marks.json  - ClassPulse marks written by `classpulse.py` (used when present, or when
                             course.json "attendance_source" is "classpulse")
and may contain:
    program.json  - AthkaX program details saved by `athkax.py program <link>` (name, instructor, dates, link)
    aliases.json  - {"chat or ClassPulse name": "roster email" | "#<roster index>" | "+<extra key>"}
    extras.json   - {"<key>": {"name": ..., "email": null}}  people in chat but not on roster
    grades.json   - list of graded projects (see SKILL.md)

--check only reports unmapped names and roll-call windows; it writes nothing.
Exit code 2 = unmapped chat users remain (map them in aliases.json, then rerun). Unmatched ClassPulse
people are listed with candidates and added as unregistered extras (no email, never synced, no certificate).
"""
import argparse, datetime as dt, difflib, json, os, re, sys

import openpyxl
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

# ---- one visual system for every sheet
FONT = "Arial"
HEAD = PatternFill("solid", fgColor="1F4E78")          # all header cells
HEAD_FONT = Font(name=FONT, size=11, bold=True, color="FFFFFF")
BODY_FONT = Font(name=FONT, size=11)
BOLD_FONT = Font(name=FONT, size=11, bold=True)
LINK_FONT = Font(name=FONT, size=11, color="0563C1", underline="single")
ZEBRA = [PatternFill("solid", fgColor="FFFFFF"), PatternFill("solid", fgColor="F2F6FA")]
KEY = PatternFill("solid", fgColor="E2F0D9")           # computed key columns (Attendance %, Project %)
FILL = {"Present": PatternFill("solid", fgColor="C6E0B4"),
        "Late": PatternFill("solid", fgColor="FFE699"),
        "Absent": PatternFill("solid", fgColor="F8CBAD"),
        "Leave": PatternFill("solid", fgColor="D9D9D9")}
# conditional-format fills: Excel paints a dxf solid fill from bgColor (end_color), so set both colours
CF = lambda col: PatternFill(fill_type="solid", start_color=col, end_color=col)
CF_FILL = {k: CF(f.fgColor.rgb[-6:]) for k, f in FILL.items()}
RANK = ["Absent", "Leave", "Late", "Present"]
THIN = Side(style="thin", color="D9D9D9")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center")
TOP = Alignment(vertical="top")
WRAP = Alignment(vertical="top", wrap_text=True)
HEAD_AL = Alignment(horizontal="center", vertical="center", wrap_text=True)
DATE_FMT = "yyyy-mm-dd"


def load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def norm(s):
    s = re.sub(r"[ً-ْـ]", "", str(s or ""))  # strip tashkeel/tatweel
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"\s+", " ", s).strip().lower()


def header(ws, row, labels, col0=1):
    for j, h in enumerate(labels, col0):
        x = ws.cell(row, j, h)
        x.fill, x.font, x.alignment, x.border = HEAD, HEAD_FONT, HEAD_AL, BOX
    ws.row_dimensions[row].height = 30


def body(ws, r, c, value=None, *, align=TOP, fill=None, font=None, fmt=None, zebra=True):
    x = ws.cell(r, c) if value is None else ws.cell(r, c, value)
    x.font = font or BODY_FONT
    x.alignment = align
    x.border = BOX
    if fill is not None:
        x.fill = fill
    elif zebra:
        x.fill = ZEBRA[r % 2]
    if fmt:
        x.number_format = fmt
    return x


def from_classpulse(cp, days, people, roster, aliases, resolve, default_mark):
    """Map classpulse_marks.json people to roster keys: alias → Nafath ID → email → name; the rest become +CPn extras.

    Returns (chats-like day logs, status, seen names, notes, unmatched people, ratios). Two ClassPulse identities that
    resolve to one learner keep the better mark per day; roster learners never seen in ClassPulse get `default_mark`.
    ratios = {key: {day index: (answered, total)}} for every day the learner joined ClassPulse (the best identity)."""
    digits = lambda s: re.sub(r"\D", "", str(s or ""))
    by_naf = {digits(s.get("nafath")): "#%d" % i for i, s in enumerate(roster) if digits(s.get("nafath"))}
    by_email = {(e or "").strip().lower(): k for k, _, e in people if e}
    by_name = {norm(n): k for k, n, _ in people if n}
    status, seen, notes, unmatched, ratios = {}, {}, [], [], {}
    for p in cp["people"]:
        k = next((resolve(aliases[n]) for n in p["names"] if n in aliases), None)
        k = k or next((by_naf[digits(r)] for r in p["rosterIds"] if "@" not in r and digits(r) in by_naf), None)
        k = k or next((by_email[r.strip().lower()] for r in p["rosterIds"] if r.strip().lower() in by_email), None)
        k = k or next((by_name[norm(n)] for n in p["names"] if norm(n) in by_name), None)
        if not k:
            k = "+CP%d" % (len(unmatched) + 1)
            people.append((k, p["name"], None))
            unmatched.append(p)
        elif k in status:
            notes.append(f"{dict((x, n) for x, n, _ in people)[k]}: several ClassPulse identities "
                         f"({', '.join(seen[k] + p['names'])}); the better mark is kept each day.")
        cur = status.setdefault(k, {})
        for d, m in p["marks"].items():
            if d in days:
                di = days.index(d)
                if cur.get(di) is None or RANK.index(m) > RANK.index(cur[di]):
                    cur[di] = m
        seen.setdefault(k, [])
        seen[k] += [n for n in p["names"] if n not in seen[k]]
        for d, x in (p.get("days") or {}).items():
            if d in days and x.get("total"):
                rk = ratios.setdefault(k, {})
                di = days.index(d)
                if di not in rk or x["answered"] / x["total"] > rk[di][0] / rk[di][1]:
                    rk[di] = (x["answered"], x["total"])
    held = set(cp["days"])
    for k, _, _ in people:
        if k not in status:
            status[k] = {days.index(d): default_mark for d in held if d in days}
    chats = [[(f"{ds} {t}", "Trainer" if tr else u, x) for t, u, x, tr in cp["logs"][ds]] if ds in held else None
             for ds in days]
    return chats, status, seen, notes, unmatched, ratios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("course_dir")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    D = a.course_dir
    cfg = load(os.path.join(D, "course.json"), {})
    prog = load(os.path.join(D, "program.json"), {})   # from athkax.py program <link>
    for k in ("program_name", "instructor", "days", "program_url", "delivery", "content_url"):
        if prog.get(k) and not cfg.get(k):
            cfg[k] = prog[k]
    roster = load(os.path.join(D, "students.json"))
    # AthkaX can enrol the same person twice (same Nafath ID/email): one row per person; athkax.py marks both records
    uniq = {}
    for s in roster:
        uniq.setdefault(str(s.get("nafath") or (s.get("email") or "").strip().lower() or id(s)), s)
    dup_enrol, roster = len(roster) - len(uniq), list(uniq.values())
    aliases = load(os.path.join(D, "aliases.json"), {})
    extras = load(os.path.join(D, "extras.json"), {})
    grades = load(os.path.join(D, "grades.json"), [])

    days = cfg["days"]                                   # ["2026-10-12", ...] all course days (ISO)
    ndays = len(days)
    instr = set(cfg.get("instructor_chat_names", ["SDAIA Academy"]))
    kw = cfg.get("rollcall_keyword", "تحضير")
    before = cfg.get("window_before_min", 1)
    after = cfg.get("window_after_min", 3)
    lenient = {int(d) - 1 for d in cfg.get("lenient_days", [])}   # 1-based in config
    extra_windows = cfg.get("extra_windows", {})          # {"1": [["HH:MM","HH:MM"]]} only if instructor confirms

    # ---- people: roster + extras, keyed by "#i" / "+key"
    people = [("#%d" % i, s.get("name") or "", s.get("email")) for i, s in enumerate(roster)]
    people += [("+" + k, v["name"], v.get("email")) for k, v in extras.items()]
    by_email = {(e or "").strip().lower(): k for k, _, e in people if e}
    by_name = {norm(n): k for k, n, _ in people if n}

    def resolve(ref):
        if ref is None:
            return None
        ref = str(ref)
        if ref.startswith("#") or ref.startswith("+"):
            return ref
        return by_email.get(ref.strip().lower()) or by_name.get(norm(ref))

    def who(chat_name):
        if chat_name in aliases:
            return resolve(aliases[chat_name])
        return by_name.get(norm(chat_name))

    P = lambda s: dt.datetime.strptime(str(s)[:16], "%Y-%m-%d %H:%M")

    cp_path = os.path.join(D, "classpulse_marks.json")
    source = cfg.get("attendance_source") or ("classpulse" if os.path.exists(cp_path) else "chat")
    cpc = cfg.get("classpulse", {})

    # ---- chats (attendance source "chat")
    status, seen, chats, unmapped, windows_log = {}, {}, [], {}, []
    ratios = {}                                          # ClassPulse: {key: {day: (answered, total)}} (days joined)
    cp_notes, cp_unmatched = [], []
    chat_days = []                                       # days whose marks came from a chat export
    chat_merged, chat_unmapped = [], {}                  # ClassPulse days whose chat export is shown in the date sheet

    def chat_day(di, ds, status, seen):
        """Mark one day from chat-<ds>.xlsx into status/seen; returns the rows, or None if there is no export."""
        f = os.path.join(D, f"chat-{ds}.xlsx")
        if not os.path.exists(f):
            return None
        chat_days.append(di)
        ws = openpyxl.load_workbook(f).active
        rows = [r[:3] for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]
        calls = [P(r[0]) for r in rows if r[1] in instr and kw in str(r[2])]
        wins = [(t - dt.timedelta(minutes=before), t + dt.timedelta(minutes=after)) for t in calls]
        for s, e in extra_windows.get(str(di + 1), []):
            wins.append((P(f"{ds} {s}"), P(f"{ds} {e}")))
        windows_log.append((ds, [t.strftime("%H:%M") for t in calls], len(rows)))
        for ts, u, txt in rows:
            if u in instr:
                continue
            k = who(u)
            if not k:
                unmapped.setdefault(u, set()).add(ds)
                continue
            seen.setdefault(k, [])
            if u not in seen[k]:
                seen[k].append(u)
            t = P(ts)
            inw = any(s <= t <= e for s, e in wins)
            cur = status.setdefault(k, {}).get(di)
            status[k][di] = "Present" if (inw or cur == "Present" or di in lenient) else "Late"
        return rows

    def lenient_links(status):
        # lenient days: a submitted project link also counts as Present
        for g in grades:
            k = resolve(g.get("student"))
            if k and g.get("link") and g.get("submitted_day"):
                di = int(g["submitted_day"]) - 1
                if di in lenient:
                    status.setdefault(k, {})[di] = "Present"

    for di, ds in enumerate(days if source == "chat" else []):
        chats.append(chat_day(di, ds, status, seen))
    lenient_links(status)

    if source == "classpulse":                           # ---- ClassPulse checkpoints (see classpulse.py)
        cp = load(cp_path)
        if not cp:
            sys.exit("attendance_source is classpulse but classpulse_marks.json is missing — run classpulse.py first")
        # learners never seen in ClassPulse: Leave under leave_if_never_present or leave_if_joined_days_lte (0 joined days), else Absent
        default = "Leave" if cpc.get("leave_if_never_present") or cpc.get("leave_if_joined_days_lte") is not None else "Absent"
        chats, status, seen, cp_notes, cp_unmatched, ratios = from_classpulse(cp, days, people, roster, aliases, resolve, default)
        # days with no ClassPulse session fall back to that day's Webex chat export, if there is one
        for di, ds in enumerate(days):
            if chats[di] is None:
                chats[di] = chat_day(di, ds, status, seen)
        lenient_links(status)
        # ClassPulse days: show the official roster name on checkpoint rows and interleave that day's Webex chat export
        # (if any) by time. Chat on these days never affects marks; unmapped chat names are reported, shown as typed.
        name_of = {k: n for k, n, _ in people}
        cp_key = {norm(n): k for k, ns in seen.items() for n in ns}
        for di, ds in enumerate(days):
            if chats[di] is None or di in chat_days:
                continue
            rows = [(ts, u if u in instr | {"Trainer"} else name_of.get(cp_key.get(norm(u)), u), x) for ts, u, x in chats[di]]
            f = os.path.join(D, f"chat-{ds}.xlsx")
            if os.path.exists(f):
                chat_merged.append(ds)
                ws = openpyxl.load_workbook(f).active
                for ts, u, x in (r[:3] for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]):
                    k = None if u in instr else who(u)
                    if u not in instr and not k:
                        chat_unmapped.setdefault(u, set()).add(ds)
                    elif k:
                        seen.setdefault(k, [])
                        if u not in seen[k]:
                            seen[k].append(u)
                    rows.append((str(ts)[:16], name_of[k] if k else u, x))
            rows.sort(key=lambda r: str(r[0])[:16])
            chats[di] = rows
        if cpc.get("leave_if_never_present"):            # never Present/Late on any day → Leave on chat days too
            for k, _, _ in people:
                st = status.setdefault(k, {})
                if not any(m in ("Present", "Late") for m in st.values()):
                    for di in chat_days:
                        st[di] = "Leave"
        instr = instr | {"Trainer"}
        print(f"classpulse: {cp['source']} | checkpoints {cp['totals']} | {len(cp['people'])} people"
              f" | matched {len(cp['people']) - len(cp_unmatched)} | not on roster {len(cp_unmatched)}"
              + (f" | {dup_enrol} duplicate enrolments merged" if dup_enrol else ""))
        if cp_unmatched:
            print("\nClassPulse people not on the roster (map in aliases.json if they are; else flagged as unregistered):")
            names = [n for k, n, _ in people if k.startswith("#")]
            for p in cp_unmatched:
                cand = difflib.get_close_matches(norm(p["name"]), [norm(n) for n in names], n=3, cutoff=0.4)
                print(f"  {p['name']!r} ids={p['rosterIds']} days={ {d: v['answered'] for d, v in p['days'].items()} } candidates: {cand}")
    # end-of-program rule (course.json "leave_if_attended_days_lte": N, set on the last day): anyone who joined on at most
    # N days — a ClassPulse day joined (even with no answer) or a chat day with a message — is Leave on every held day.
    end_leave = cfg.get("leave_if_attended_days_lte")
    end_leave_names = []
    if end_leave is not None:
        held_days = [d for d in range(ndays) if chats[d] is not None]
        for k, n, _ in people:
            st = status.setdefault(k, {})
            joined = {d for d in ratios.get(k, {})} | {d for d in chat_days if st.get(d) in ("Present", "Late")}
            if len(joined) <= int(end_leave) and any(st.get(d) != "Leave" for d in held_days):
                for d in held_days:
                    st[d] = "Leave"
                if joined:
                    end_leave_names.append(n)
        print(f"end-of-program Leave (joined <= {end_leave} day(s)): {len(end_leave_names)} learners who joined, plus those never seen")
    # instructor overrides: course.json "status_overrides": {"<email>": {"<day number>": "Late", ...}}
    overrides_log = []
    for who, dm in (cfg.get("status_overrides") or {}).items():
        k = resolve(who)
        if not k:
            sys.exit(f"status_overrides: cannot resolve {who!r}")
        for dn, mark in dm.items():
            di = int(dn) - 1
            overrides_log.append(f"{who} on {days[di]}: {status.get(k, {}).get(di, '-')} -> {mark}")
            status.setdefault(k, {})[di] = mark
    if overrides_log:
        print("status overrides:", "; ".join(overrides_log))
    if windows_log:
        print("chats:", "; ".join(f"{ds} {n} msgs, calls {','.join(calls) or 'NONE'}" for ds, calls, n in windows_log))
    missing = [days[d] for d in range(ndays) if chats[d] is None]
    if missing:
        print(f"no {'ClassPulse session' if source == 'classpulse' else 'chat export'} yet:", ", ".join(missing))
    if chat_unmapped:
        print("\nChat names on ClassPulse days not on the roster (shown as typed; add to aliases.json or extras.json):")
        for u, ds in chat_unmapped.items():
            print(f"  {u!r} on {', '.join(sorted(ds))}")
    if unmapped:
        print("\nUNMAPPED chat users (add to aliases.json or extras.json):")
        names = [n for _, n, _ in people if n]
        for u, ds in sorted(unmapped.items()):
            cand = difflib.get_close_matches(norm(u), [norm(n) for n in names], n=3, cutoff=0.4)
            print(f"  {u!r} ({', '.join(sorted(ds))}) candidates: {cand}")
        if not a.check:
            sys.exit(2)
    if a.check:
        return

    # ---- grades by person
    gmap = {}
    for g in grades:
        k = resolve(g.get("student"))
        if not k:
            sys.exit(f"grades.json: cannot resolve student {g.get('student')!r}")
        gmap[k] = g
    rub = cfg.get("rubric") or {"criteria": []}       # rubric may be added later (attendance-only builds)
    crit = rub["criteria"]                              # [["Functional end-to-end", 35], ...]
    bonus = rub.get("bonus")                             # ["Fine-tuning bonus", 15] or None
    cap = rub.get("cap", 100)

    def pscore(k):
        g = gmap.get(k)
        if not g or not g.get("scores"):
            return -1
        return min(cap, sum(g["scores"]) + (g.get("bonus") or 0))

    def ascore(k):
        st = status.get(k, {})
        return sum(2 if st.get(d) == "Present" else 1 if st.get(d) == "Late" else 0 for d in range(ndays))

    order = sorted(range(len(people)), key=lambda j: (-ascore(people[j][0]), -pscore(people[j][0]), j))
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    nc = len(crit)
    nb = 1 if bonus else 0
    proj_col = 5 + nc + nb + 2                           # Projects: A..E, criteria, [bonus], link-check, Project
    att_col = 4 + ndays                                  # Attendance: Name, Email, Chat Name, dates..., Attendance

    # ---- Certificates
    c = wb.create_sheet("Certificates")
    c.sheet_view.rightToLeft = True
    sd = dt.datetime.strptime(days[0], "%Y-%m-%d")
    info = [("اسم المدرب", cfg["instructor"]), ("اسم البرنامج", cfg["program_name"]),
            ("تاريخ البرنامج", sd), ("عدد الأيام", ndays),
            ("حضوري - عن بعد", cfg.get("delivery", "عن بعد")), ("رابط البرنامج", cfg.get("program_url")),
            ("رابط المحتوى", cfg.get("content_url"))]
    for r, (k_, v) in enumerate(info, 1):
        x = c.cell(r, 1, k_)
        x.fill, x.font, x.alignment, x.border = HEAD, HEAD_FONT, Alignment(vertical="center"), BOX
        y = body(c, r, 2, v, font=BOLD_FONT, zebra=False, align=Alignment(horizontal="right", vertical="center"))
        if k_ == "تاريخ البرنامج":
            y.number_format = DATE_FMT
        if k_ in ("رابط البرنامج", "رابط المحتوى") and v:
            y.hyperlink, y.font = v, LINK_FONT
    HR = len(info) + 2                                   # table header row (one blank row after the info block)
    header(c, HR, ["الإسم ثلاثي", "الإيميل", "الحضور", "المشروع", "المجموع", "نوع الشهادة", "رابط المشروع"])
    min_att = cfg.get("certificate_min_attendance_points", 1)  # (2P+L) points needed to be listed
    def total(k):                                        # المجموع as the sheet computes it: 70% project + 30% attendance
        return 0.7 * max(pscore(k), 0) / 100 + 0.3 * ascore(k) / (2 * ndays)

    cert_order = sorted(order, key=lambda j: -total(people[j][0]))   # stable: ties keep attendance/project/roster order
    r = HR + 1
    for j in cert_order:
        k, n, e = people[j]
        if ascore(k) < min_att or (source == "classpulse" and not e):   # ClassPulse: AthkaX learners only
            continue
        body(c, r, 1, n)
        body(c, r, 2, e)
        body(c, r, 3, f"=IFERROR(INDEX(Attendance!${L(att_col)}:${L(att_col)},MATCH(A{r},Attendance!$A:$A,0)),0)", align=CENTER, fmt="0%")
        body(c, r, 4, f"=IFERROR(INDEX(Projects!${L(proj_col)}:${L(proj_col)},MATCH(A{r},Projects!$A:$A,0)),0)", align=CENTER, fmt="0%")
        body(c, r, 5, f"=70%*D{r}+30%*C{r}", align=CENTER, fmt="0%", font=BOLD_FONT)
        body(c, r, 6, f'=IF(AND(E{r}>65%,C{r}>65%),"اجتياز",IF(C{r}>65%,"حضور","بدون"))', align=CENTER, font=BOLD_FONT)
        body(c, r, 7, f'=IFERROR(INDEX(Projects!$C:$C,MATCH(A{r},Projects!$A:$A,0)),"")')
        r += 1
    listed = r - HR - 1
    last_c = max(r - 1, HR + 1)
    for v, col in (("اجتياز", "C6E0B4"), ("حضور", "FFE699"), ("بدون", "F8CBAD")):
        c.conditional_formatting.add(f"F{HR + 1}:F{last_c}", FormulaRule(formula=[f'F{HR + 1}="{v}"'], fill=CF(col)))
    note = c.cell(r + 1, 1, cfg.get("certificates_footnote", "تتضمن القائمة كل من سُجّل حضوره في يوم واحد على الأقل."))
    note.font = Font(name=FONT, size=10, italic=True, color="595959")
    for col, w in zip("ABCDEFG", [30, 32, 9, 9, 9, 12, 60]):
        c.column_dimensions[col].width = w
    c.freeze_panes = f"A{HR + 1}"
    c.auto_filter.ref = f"A{HR}:G{last_c}"

    # ---- Attendance
    at = wb.create_sheet("Attendance")
    header(at, 1, ["Name", "Email", ("ClassPulse / Chat Name" if chat_days or chat_merged else "ClassPulse Name") if source == "classpulse" else "Chat Name"] + list(days) + ["Attendance"])
    lastday = L(3 + ndays)
    # ClassPulse days: a learner who joined gets the checkpoint ratio as a formula ("=4/6") whose number format shows
    # the mark — Present ≥ present_min, Late ≥ late_min, else Absent — when that matches the computed mark (not an
    # override, Leave or a special rule); everything else is text. Totals and the conditional fills read both forms;
    # mark cells carry no static fill, so the colour always follows the cell's current value.
    pmin, lmin = cpc.get("present_min", 0.65), cpc.get("late_min", 0.25)
    ratio_fmt = f'[>={pmin:g}]"Present";[>={lmin:g}]"Late";"Absent"'
    as_mark = lambda a, t: "Present" if a / t >= pmin else "Late" if a / t >= lmin else "Absent"
    n_formula = 0
    for r, j in enumerate(order, 2):
        k, n, e = people[j]
        body(at, r, 1, n)
        body(at, r, 2, e)
        body(at, r, 3, ", ".join(seen.get(k, [])) or None)
        for d in range(ndays):
            v = status.get(k, {}).get(d, "Absent") if chats[d] is not None else None
            q = ratios.get(k, {}).get(d)
            if v and q and d not in chat_days and as_mark(*q) == v:
                body(at, r, 4 + d, f"={q[0]}/{q[1]}", align=CENTER, fmt=ratio_fmt, zebra=False)
                n_formula += 1
            else:
                body(at, r, 4 + d, v, align=CENTER, zebra=v is None)
        rng = f"D{r}:{lastday}{r}"
        body(at, r, att_col, f'=(2*(COUNTIF({rng},"Present")+COUNTIF({rng},">={pmin:g}"))+COUNTIF({rng},"Late")'
                             f'+COUNTIFS({rng},">={lmin:g}",{rng},"<{pmin:g}"))/{2 * ndays}',
             align=CENTER, fmt="0%", fill=KEY, font=BOLD_FONT)
    last = len(order) + 1
    rules = {"Present": f'OR(D2="Present",AND(ISNUMBER(D2),D2>={pmin:g}))',
             "Late": f'OR(D2="Late",AND(ISNUMBER(D2),D2>={lmin:g},D2<{pmin:g}))',
             "Absent": f'OR(D2="Absent",AND(ISNUMBER(D2),D2<{lmin:g}))',
             "Leave": 'D2="Leave"'}
    for v, f in CF_FILL.items():
        at.conditional_formatting.add(f"D2:{lastday}{last}", FormulaRule(formula=[rules[v]], fill=f, stopIfTrue=True))
    for col, w in zip("ABC", [32, 32, 40]):
        at.column_dimensions[col].width = w
    for d in range(ndays):
        at.column_dimensions[L(4 + d)].width = 12
    at.column_dimensions[L(att_col)].width = 12
    at.freeze_panes = "B2"
    at.auto_filter.ref = f"A1:{L(att_col)}{last}"

    # ---- Projects
    p = wb.create_sheet("Projects")
    ph = ["Name", "Email", "Submission Link", "Commit Hash", "Use case"] + [f"{n} ({w})" for n, w in crit]
    if bonus:
        ph.append(f"{bonus[0]} (+{bonus[1]})")
    ph += [rub.get("link_check_label", "Required link in README"), "Project", "Reasoning"]
    header(p, 1, ph)
    p.row_dimensions[1].height = 45
    first_c, last_s = L(6), L(5 + nc + nb)
    graded = sorted(gmap.items(), key=lambda kv: -pscore(kv[0]))
    name_of = {k: n for k, n, _ in people}
    email_of = {k: e for k, _, e in people}
    for r, (k, g) in enumerate(graded, 2):
        sc = g.get("scores")
        body(p, r, 1, name_of[k])
        body(p, r, 2, email_of.get(k))
        lk = body(p, r, 3, g.get("link"))
        if g.get("link"):
            lk.hyperlink, lk.font = g["link"], LINK_FONT
        body(p, r, 4, g.get("commit"), font=Font(name="Consolas", size=10))
        body(p, r, 5, g.get("use_case"))
        for i in range(nc):
            body(p, r, 6 + i, sc[i] if sc else None, align=CENTER)
        if bonus:
            body(p, r, 6 + nc, (g.get("bonus") or 0) if sc else None, align=CENTER)
        body(p, r, 6 + nc + nb, ("Yes" if g.get("link_ok", True) else "No") if sc else None, align=CENTER)
        body(p, r, proj_col, f'=IF(COUNT({first_c}{r}:{L(5 + nc)}{r})=0,"",MIN({cap},SUM({first_c}{r}:{last_s}{r}))/100)',
             align=CENTER, fmt="0%", fill=KEY, font=BOLD_FONT)
        body(p, r, proj_col + 1, g.get("reasoning"), align=WRAP)
    lastp = max(len(graded) + 1, 2)
    p.conditional_formatting.add(f"{L(proj_col)}2:{L(proj_col)}{lastp}", ColorScaleRule(
        start_type="num", start_value=0, start_color="F8696B", mid_type="num", mid_value=rub.get("pass_mark", 70) / 100,
        mid_color="FFEB84", end_type="num", end_value=cap / 100, end_color="63BE7B"))
    p.conditional_formatting.add(f"{L(6 + nc + nb)}2:{L(6 + nc + nb)}{lastp}",
                                 FormulaRule(formula=[f'{L(6 + nc + nb)}2="No"'], fill=CF_FILL["Absent"]))
    widths = [32, 30, 45, 44, 18] + [13] * nc + ([12] if bonus else []) + [12, 10, 100]
    for j, w in enumerate(widths, 1):
        p.column_dimensions[L(j)].width = w
    p.freeze_panes = "B2"
    p.auto_filter.ref = f"A1:{L(proj_col + 1)}{lastp}"

    # ---- one chat sheet per course date (time only)
    for d, rows in enumerate(chats):
        if rows is None:
            continue
        s = wb.create_sheet(days[d])
        header(s, 1, ["time", "user", "text"])
        for r, (ts, u, txt) in enumerate(rows, 2):
            is_instr = u in instr
            f = Font(name=FONT, size=11, bold=True, color="1F4E78") if is_instr else None
            body(s, r, 1, str(ts)[11:16], align=CENTER, font=f)
            body(s, r, 2, u, font=f)
            body(s, r, 3, txt, align=WRAP, font=f)
        for col, w in zip("ABC", [8, 32, 100]):
            s.column_dimensions[col].width = w
        s.freeze_panes = "A2"
        s.auto_filter.ref = f"A1:C{len(rows) + 1}"

    # ---- Notes
    nt = wb.create_sheet("Notes")
    header(nt, 1, ["Notes"])
    if source == "classpulse":
        pm, lm = cpc.get("present_min", 0.65), cpc.get("late_min", 0.25)
        nb = cpc.get("new_batch") or {}
        notes = [f"Source: ClassPulse checkpoint questions ({cp['source']}); only checkpoints that received at least one answer count: "
                 + ", ".join(f"{d} {n}" for d, n in cp["totals"].items()) + ".",
                 f"Present = answered at least {pm:.0%} of that day's checkpoints."
                 + (f" Late = answered at least {lm:.0%}." if lm < pm else ""),
                 ("Late also = joined the ClassPulse link that day (admitted, waiting or rejected) without reaching the Present mark. "
                  if cpc.get("joined_counts_as_late") else "") + "Absent = did not join that day.",
                 "Leave = not Present on any session day, including AthkaX learners never seen in ClassPulse (all session days)."
                 if cpc.get("leave_if_never_present") else
                 f"Leave on every day = joined ClassPulse on {cpc['leave_if_joined_days_lte']} day(s) or fewer over the whole program (AthkaX learners never seen included)."
                 if cpc.get("leave_if_joined_days_lte") is not None else "AthkaX learners never seen in ClassPulse are Absent."]
        for ks, v in cpc.get("day_overrides", {}).items():
            ds_ = ", ".join(days[int(k) - 1] for k in str(ks).split(","))
            notes.append(f"Rules on {ds_}: Present = answered at least {v.get('present_min', pm):.0%}"
                         + ("; any attempt to join counts as Late" if v.get("joined_counts_as_late") else "")
                         + (f"; Late = answered at least {v['late_min']:.0%}" if "late_min" in v else "") + ".")
        if cpc.get("no_late_days"):
            notes.append("No-Late day(s): " + ", ".join(days[i - 1] for i in cpc["no_late_days"]) + " — Late counts as Present.")
        if nb.get("admitted_day"):
            notes.append(f"New batch (first joined on {days[nb['admitted_day'] - 1]}, admitted late): {nb.get('mark_before', 'Absent')} before that day"
                         + (f", {nb['mark_admitted_day']} on it" if nb.get("mark_admitted_day") else "") + ".")
        notes += ["Duplicate ClassPulse identities (several devices, missing or mistyped ID, Arabic/English name) are merged; each checkpoint counts once.",
                  "Matching to AthkaX: aliases.json, then Nafath ID, then email, then exact name. Names and emails shown are the official AthkaX ones.",
                  "The date sheets list the ClassPulse checkpoint log" + (f" interleaved by time with the Webex chat export of {', '.join(chat_merged)}" if chat_merged else "")
                  + " (trainer rows in bold); the user column shows the official roster name (chat and ClassPulse names mapped via aliases.json)."]
        if cpc.get("chat_checkpoint_credit"):
            notes.append("A Webex chat message posted while a checkpoint was open (from its opening minute to its closing minute) "
                         "counts as answering that checkpoint; chat names are matched to learners through aliases.json.")
        if cpc.get("aliases"):
            notes.append("Manual ClassPulse links: " + "; ".join(f"{k} = {v}" for k, v in cpc["aliases"].items()) + ".")
        if cpc.get("exclude"):
            notes.append("Excluded from ClassPulse data: " + ", ".join(cpc["exclude"]) + ".")
        if dup_enrol:
            notes.append(f"{dup_enrol} people are enrolled twice on AthkaX (same Nafath ID/email); listed once, and athkax.py marks both records.")
        notes += cp_notes
        notes += [f"{p['name']} [{', '.join(p['rosterIds']) or 'no ID'}]: in ClassPulse but not on the AthkaX batch; no email, not synced, no certificate — check registration."
                  for p in cp_unmatched]
        notes += [f"Chat name {u!r} ({', '.join(sorted(ds))}) could not be matched to the roster; shown as typed in the date sheet."
                  for u, ds in chat_unmapped.items()]
        if chat_days:
            notes.append("No ClassPulse session on " + ", ".join(days[d] for d in chat_days)
                         + ": attendance taken from the Webex chat export (sheet of that date lists the chat).")
    else:
        notes = [f"Present = the student posted any message from {before} minute(s) before through {after} minutes after any instructor message containing the word {kw}.",
                 "Late = the student posted at least one message during the day but did not post inside any attendance window.",
                 "Absent = the student posted no message during the day."]
    notes += [f"Attendance = (2 × Present + Late) / (2 × Days), so Present counts as a full day and Late as half a day across {ndays} days.",
              "Project = min(100, rubric criteria + bonus) / 100. المجموع = 70% × Project + 30% × Attendance; اجتياز needs المجموع > 65% and Attendance > 65%.",
              "Certificates rows are sorted by المجموع descending; Attendance and Projects rows by Attendance descending, then Project descending; ties retain the official roster order."]
    if source == "classpulse":
        notes.append(f"ClassPulse day cells hold the learner's checkpoint ratio as a formula (e.g. =4/6, answered/total); the cell format "
                     f"shows Present when it is at least {pmin:.0%}, Late when at least {lmin:.0%} and Absent below, and the colours follow. "
                     "Text marks are overrides, Leave, days not joined (Absent) and chat days.")
    if end_leave is not None:
        notes.append(f"End of program: anyone who joined on {end_leave} day(s) or fewer (ClassPulse joins, or a chat message on a chat day) "
                     "is Leave on every day" + (f" ({', '.join(end_leave_names)} joined once; everyone else never joined)." if end_leave_names else "."))
    if overrides_log:
        notes.append("Instructor attendance overrides: " + "; ".join(overrides_log) + ".")
    if source == "chat" or chat_days:
        notes.append("Chat display-name aliases were matched to official roster entries; all non-instructor chat users were mapped before export.")
    if lenient:
        notes.append("Lenient day(s) by instructor decision: " + ", ".join(days[d] for d in sorted(lenient)) +
                     " — any chat message or a submitted project link counts as Present (no Late).")
    if missing:
        notes.append(f"PARTIAL: no {'ClassPulse session' if source == 'classpulse' else 'chat export'} yet for "
                     + ", ".join(missing) + "; those days count as zero until added.")
    notes += cfg.get("notes", [])
    for i, t in enumerate(notes, 2):
        body(nt, i, 1, t, align=WRAP)
    nt.column_dimensions["A"].width = 150

    for ws in wb:                                        # print-friendly defaults
        ws.sheet_view.zoomScale = 100
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth = 1
    out = a.out or os.path.join(D, cfg.get("output_name", f"{cfg['program_name']} {sd:%d-%m-%Y}.xlsx"))
    wb.save(out)
    print(f"saved {os.path.basename(out)} | graded {sum(1 for g in grades if g.get('scores'))} | certificates {listed}")


if __name__ == "__main__":
    main()

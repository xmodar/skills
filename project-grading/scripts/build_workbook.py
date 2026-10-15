#!/usr/bin/env python3
"""Build the course grading workbook (Certificates, Attendance, Projects, one sheet per course date, Notes).

Usage:
    python build_workbook.py COURSE_DIR [--out OUT.xlsx] [--check]

COURSE_DIR must contain:
    course.json   - course settings and rubric (see SKILL.md); program fields may come from program.json
    students.json - roster: [{"name": ..., "email": ...}, ...]
    chat-YYYY-MM-DD.xlsx - one chat export per day (columns: timestamp | user | text)
and may contain:
    program.json  - AthkaX program details saved by `athkax.py program <link>` (name, instructor, dates, link)
    aliases.json  - {"chat display name": "roster email" | "#<roster index>" | "+<extra key>"}
    extras.json   - {"<key>": {"name": ..., "email": null}}  people in chat but not on roster
    grades.json   - list of graded projects (see SKILL.md)

--check only reports unmapped chat names and roll-call windows; it writes nothing.
Exit code 2 = unmapped chat users remain (map them in aliases.json, then rerun).
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
        "Absent": PatternFill("solid", fgColor="F8CBAD")}
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

    # ---- chats
    status, seen, chats, unmapped, windows_log = {}, {}, [], {}, []
    for di, ds in enumerate(days):
        f = os.path.join(D, f"chat-{ds}.xlsx")
        if not os.path.exists(f):
            chats.append(None)
            continue
        ws = openpyxl.load_workbook(f).active
        rows = [r[:3] for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]
        chats.append(rows)
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

    # lenient days: a submitted project link also counts as Present
    for g in grades:
        k = resolve(g.get("student"))
        if k and g.get("link") and g.get("submitted_day"):
            di = int(g["submitted_day"]) - 1
            if di in lenient:
                status.setdefault(k, {})[di] = "Present"

    print("chats:", "; ".join(f"{ds} {n} msgs, calls {','.join(calls) or 'NONE'}" for ds, calls, n in windows_log))
    missing = [days[d] for d in range(ndays) if chats[d] is None]
    if missing:
        print("no chat export yet:", ", ".join(missing))
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
    crit = cfg["rubric"]["criteria"]                     # [["Functional end-to-end", 35], ...]
    bonus = cfg["rubric"].get("bonus")                   # ["Fine-tuning bonus", 15] or None
    cap = cfg["rubric"].get("cap", 100)

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
    r = HR + 1
    for j in order:
        k, n, e = people[j]
        if ascore(k) < min_att:
            continue
        body(c, r, 1, n)
        body(c, r, 2, e)
        body(c, r, 3, f"=IFERROR(INDEX(Attendance!${L(att_col)}:${L(att_col)},MATCH(A{r},Attendance!$A:$A,0)),0)", align=CENTER, fmt="0%")
        body(c, r, 4, f"=IFERROR(INDEX(Projects!${L(proj_col)}:${L(proj_col)},MATCH(A{r},Projects!$A:$A,0)),0)", align=CENTER, fmt="0%")
        body(c, r, 5, f"=70%*D{r}+30%*C{r}", align=CENTER, fmt="0%", font=BOLD_FONT)
        body(c, r, 6, f'=IF(AND(E{r}>65%,C{r}>65%),"إجتياز",IF(C{r}>65%,"حضور","بدون"))', align=CENTER, font=BOLD_FONT)
        body(c, r, 7, f'=IFERROR(INDEX(Projects!$C:$C,MATCH(A{r},Projects!$A:$A,0)),"")')
        r += 1
    listed = r - HR - 1
    last_c = max(r - 1, HR + 1)
    for v, col in (("إجتياز", "C6E0B4"), ("حضور", "FFE699"), ("بدون", "F8CBAD")):
        c.conditional_formatting.add(f"F{HR + 1}:F{last_c}", FormulaRule(formula=[f'F{HR + 1}="{v}"'], fill=PatternFill("solid", fgColor=col)))
    note = c.cell(r + 1, 1, cfg.get("certificates_footnote", "تتضمن القائمة كل من سُجّل حضوره في يوم واحد على الأقل."))
    note.font = Font(name=FONT, size=10, italic=True, color="595959")
    for col, w in zip("ABCDEFG", [30, 32, 9, 9, 9, 12, 60]):
        c.column_dimensions[col].width = w
    c.freeze_panes = f"A{HR + 1}"
    c.auto_filter.ref = f"A{HR}:G{last_c}"

    # ---- Attendance
    at = wb.create_sheet("Attendance")
    header(at, 1, ["Name", "Email", "Chat Name"] + list(days) + ["Attendance"])
    lastday = L(3 + ndays)
    for r, j in enumerate(order, 2):
        k, n, e = people[j]
        body(at, r, 1, n)
        body(at, r, 2, e)
        body(at, r, 3, ", ".join(seen.get(k, [])) or None)
        for d in range(ndays):
            v = status.get(k, {}).get(d, "Absent") if chats[d] is not None else None
            body(at, r, 4 + d, v, align=CENTER, fill=FILL.get(v), zebra=v is None)
        body(at, r, att_col, f'=(2*COUNTIF(D{r}:{lastday}{r},"Present")+COUNTIF(D{r}:{lastday}{r},"Late"))/{2 * ndays}',
             align=CENTER, fmt="0%", fill=KEY, font=BOLD_FONT)
    last = len(order) + 1
    for v, f in FILL.items():
        at.conditional_formatting.add(f"D2:{lastday}{last}", FormulaRule(formula=[f'D2="{v}"'], fill=f))
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
    ph += [cfg["rubric"].get("link_check_label", "Required link in README"), "Project", "Reasoning"]
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
        start_type="num", start_value=0, start_color="F8696B", mid_type="num", mid_value=cfg["rubric"].get("pass_mark", 70) / 100,
        mid_color="FFEB84", end_type="num", end_value=cap / 100, end_color="63BE7B"))
    p.conditional_formatting.add(f"{L(6 + nc + nb)}2:{L(6 + nc + nb)}{lastp}",
                                 FormulaRule(formula=[f'{L(6 + nc + nb)}2="No"'], fill=FILL["Absent"]))
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
    notes = [f"Present = the student posted any message from {before} minute(s) before through {after} minutes after any instructor message containing the word {kw}.",
             "Late = the student posted at least one message during the day but did not post inside any attendance window.",
             "Absent = the student posted no message during the day.",
             f"Attendance = (2 × Present + Late) / (2 × Days), so Present counts as a full day and Late as half a day across {ndays} days.",
             "Project = min(100, rubric criteria + bonus) / 100. المجموع = 70% × Project + 30% × Attendance; إجتياز needs المجموع > 65% and Attendance > 65%.",
             "Rows are sorted by Attendance descending, then Project descending; ties retain the official roster order.",
             "Chat display-name aliases were matched to official roster entries; all non-instructor chat users were mapped before export."]
    if lenient:
        notes.append("Lenient day(s) by instructor decision: " + ", ".join(days[d] for d in sorted(lenient)) +
                     " — any chat message or a submitted project link counts as Present (no Late).")
    if missing:
        notes.append("PARTIAL: no chat export yet for " + ", ".join(missing) + "; those days count as zero until added.")
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

#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx>=0.28",
#   "keyring>=25",
#   "openpyxl>=3.1",
# ]
# ///
"""AthkaX (athkax.sdaia.gov.sa) helper for the project-grading workflow. Generic for any course.

    uv run athkax.py program <program link or slug> [--out DIR]
        Fetch the program's details (name, instructor, dates, number of days, delivery) and save
        DIR/program.json (+ program_raw.json). The workbook builder reads program.json.

    uv run athkax.py attendance WORKBOOK.xlsx [--dry-run] [--program SLUG] [--batch ID] [--yes]
        Sync the workbook's Attendance sheet to the platform, matched by email: reads the current marks and
        sends only the differences (safe to re-run). Dates come from the Attendance date headers; the program
        from the Certificates "رابط البرنامج" link (or --program). Writes athkax_roster.json, athkax_mismatches.json and attendance_plan.csv.

    uv run athkax.py roster <program link or slug> [--out DIR]
        Save the batch's learners (batch-learner id, name, email, Nafath ID) to DIR/students.json.

    uv run athkax.py programs            list your ongoing programs (slug, title, batches)

Auth: no token is stored in this file. The session token is read from the OS keyring (saved after a
successful Nafath login) or the ATHKAX_TOKEN environment variable; otherwise you are asked for your
National/Iqama ID and approve the request in the Nafath app.
"""
import argparse
import asyncio
import base64
import datetime as dt
import json
import os
import re
from collections.abc import Callable
from typing import Any, Literal

import httpx
import keyring
import openpyxl

EventStatus = Literal["ongoing", "upcoming", "completed", "cancelled"]
Attendance = Literal["present", "late", "absent", "leave", "unmarked"]
Language = Literal["ar", "en"]
SHEET_TO_PLATFORM = {"present": "present", "late": "late", "absent": "absent", "leave": "leave"}
SLUG_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
BASE = "https://athkax.sdaia.gov.sa"


class AthkaXClient(httpx.AsyncClient):
    def __init__(self, connections: int = 8) -> None:
        connections = max(connections, 1)
        super().__init__(
            base_url=BASE,
            timeout=30,
            follow_redirects=True,
            headers={"accept": "application/json, text/plain, */*", "accept-language": "ar", "referer": f"{BASE}/"},
            limits=httpx.Limits(max_connections=connections, max_keepalive_connections=connections),
        )

    @property
    def token(self) -> str:
        if token := keyring.get_password(str(self.base_url), "nafath"):
            self.headers["authorization"] = token
        return self.headers.get("authorization", "")

    @token.setter
    def token(self, token: str | None) -> None:
        if token:
            token = token if token.lower().startswith("bearer ") else f"Bearer {token}"
            self.headers["authorization"] = token
            keyring.set_password(str(self.base_url), "nafath", token)
        else:
            self.headers.pop("authorization", None)
            if keyring.get_password(str(self.base_url), "nafath"):
                keyring.delete_password(str(self.base_url), "nafath")

    @property
    def session_ttl(self) -> int:
        try:
            payload = self.token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
            return max(int(exp - dt.datetime.now(dt.timezone.utc).timestamp()), 0)
        except Exception:  # noqa: BLE001
            return 0

    async def login(self, nafath_id: str, force: bool = False,
                    on_nafath: Callable[[str], Any] | None = print) -> bool:
        if not re.fullmatch(r"[1-3]\d{9}", nafath_id):
            raise ValueError("`nafath_id` is not a valid National/Iqama ID")
        if not force and self.session_ttl >= 60:
            return True
        payload = {"id": nafath_id}
        deadline = asyncio.get_running_loop().time() + 60
        while asyncio.get_running_loop().time() < deadline:
            response = await self.post(
                "/api/v1/users/nafath_auth", json=payload, params={"locale": "ar"},
                headers={"accept": "application/json", "origin": str(self.base_url),
                         "referer": f"{self.base_url}/signin"},
            )
            if token := response.raise_for_status().headers.get("authorization"):
                self.token = token
                return True
            payload.update(response.json())
            if on_nafath:
                on_nafath(f"Approve in Nafath — number: {payload.get('random')}")
                on_nafath = None
            await asyncio.sleep(2)
        return False

    async def _token_works(self) -> bool:
        r = await self.get("/api/v1/instructor/events/ongoing", params={"page": 1, "perPageItems": 12})
        return r.status_code not in (401, 403)

    async def ensure_login(self, nafath_id: str | None) -> None:
        if os.environ.get("ATHKAX_TOKEN"):
            self.token = os.environ["ATHKAX_TOKEN"]
        if self.session_ttl >= 60 and not await self._token_works():
            print("Saved AthkaX session was refused (401/403) — signing in again with Nafath.")
            self.token = None
        if self.session_ttl < 60:
            nid = nafath_id or input("Nafath (National/Iqama) ID: ").strip()
            if not await self.login(nid):
                raise SystemExit("Login failed or Nafath request not approved in 60 s")

    async def json(self, url: str, **params: Any) -> Any:
        return (await self.get(url, params=params)).raise_for_status().json()

    async def put_json(self, url: str, body: Any, **params: Any) -> Any:
        return (await self.put(url, params=params, json=body)).raise_for_status().json()

    async def get_program(self, slug: str, lang: Language = "ar") -> Any:
        return await self.json(f"/api/v1/public/events/{slug}", locale=lang)

    async def get_instructor_program(self, slug: str, lang: Language = "ar") -> Any:
        return await self.json(f"/api/v1/instructor/events/{slug}", locale=lang)

    async def get_topics(self, slug: str, lang: Language = "ar") -> Any:
        return await self.json(f"/api/v1/public/events/{slug}/training_weeks", locale=lang, page=False)

    async def get_programs(self, status: EventStatus = "ongoing") -> Any:
        return await self.json(f"/api/v1/instructor/events/{status}", page=1, perPageItems=50)

    async def get_roster(self, slug: int | str, batch: int | str, date: dt.date | None = None) -> Any:
        url = f"/api/v1/instructor/events/{slug}/batches/{batch}/batch_learners/attendances"
        learners, page = [], 1
        while page:
            r = await self.json(url, page=page, date=str(date or dt.date.today()))
            learners += r.get("batchLearners") or []
            page = (r.get("pagination") or {}).get("next")
        return {"batchLearners": learners}

    async def get_learner(self, slug: int | str, event_learner: int | str) -> Any:
        return await self.json(f"/api/v1/instructor/events/{slug}/event_learners/{event_learner}", locale="ar")

    async def mark_attendance(self, slug: int | str, batch_learner: int | str,
                              mark: Attendance = "unmarked", date: dt.date | None = None) -> Any:
        url = f"/api/v1/instructor/events/{slug}/attendances/mark"
        body = {"attendance": {"batch_learner_id": batch_learner, "availability": mark}}
        return await self.put_json(url, body, date=str(date or dt.date.today()))

    async def bulk_attendance(self, slug: int | str, batch: int | str,
                              mark: Attendance = "unmarked", date: dt.date | None = None) -> Any:
        url = f"/api/v1/instructor/events/{slug}/attendances/bulk_mark"
        body = {"attendance": {"batch_id": str(batch), "availability": mark}}
        return await self.put_json(url, body, date=str(date or dt.date.today()))


# ---------------------------------------------------------------- program details
def slug_of(link: str) -> str:
    m = SLUG_RE.search(link or "")
    if not m:
        raise SystemExit(f"No program slug found in {link!r}")
    return m.group(0).lower()


WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
MODES = {"online": "عن بعد", "remote": "عن بعد", "virtual": "عن بعد",
         "onsite": "حضوري", "offline": "حضوري", "in_person": "حضوري", "physical": "حضوري", "hybrid": "مدمج"}


def _date(v) -> dt.date | None:
    if isinstance(v, str) and (m := re.match(r"(\d{4}-\d{2}-\d{2})", v)):
        return dt.date.fromisoformat(m.group(1))
    return None


def summarize(slug: str, raw: dict) -> dict:
    """Map the AthkaX event JSON to the fields the workbook needs.

    Uses: title, startDate/endDate (NOT registrationStartDate/lastDateToApply), eventInstructors[].name,
    mode, duration+unit, and the batch weekdays (batches[].days or batchCourses[].frequencies[].day)
    to list the session dates between start and end.
    """
    ev = raw.get("instructor_event") or {}
    pub = raw.get("public_event") or {}
    get = lambda k: ev.get(k) if ev.get(k) not in (None, "") else pub.get(k)
    courses = ev.get("eventCourses") or pub.get("eventCourses") or []
    start = _date(get("startDate")) or min((_date(c.get("startDate")) for c in courses if _date(c.get("startDate"))), default=None)
    end = _date(get("endDate")) or max((_date(c.get("endDate")) for c in courses if _date(c.get("endDate"))), default=None)

    weekdays: set[int] = set()
    for b in (ev.get("batches") or []) + (pub.get("batches") or []):
        for d in b.get("days") or []:
            weekdays.add(WEEKDAYS.get(str(d)[:3].lower(), -1))
        for bc in b.get("batchCourses") or []:
            for fr in bc.get("frequencies") or []:
                weekdays.add(WEEKDAYS.get(str(fr.get("day"))[:3].lower(), -1))
    for c in courses:
        for b in (c.get("courseInfo") or {}).get("batches") or []:
            for d in b.get("days") or []:
                weekdays.add(WEEKDAYS.get(str(d)[:3].lower(), -1))
    weekdays.discard(-1)
    if not weekdays:
        weekdays = {6, 0, 1, 2, 3}  # Sun–Thu
    days = []
    if start and end:
        days = [start + dt.timedelta(n) for n in range((end - start).days + 1)
                if (start + dt.timedelta(n)).weekday() in weekdays]

    instructors = [i["name"].strip() for i in ev.get("eventInstructors") or [] if i.get("name") and i.get("status", "active") == "active"]
    batches = ev.get("batches") or pub.get("batches") or []
    duration, unit = get("duration"), get("unit")
    info = {
        "slug": slug,
        "program_url": f"{BASE}/programs/{slug}",
        "program_name": get("title"),
        "instructor": "، ".join(instructors) or None,
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "days": [d.isoformat() for d in days],
        "num_days": len(days),
        "delivery": MODES.get(str(get("mode") or "").lower()),
        "session_time": batches[0].get("time") if batches else None,
        "batch_id": batches[0].get("id") if len(batches) == 1 else None,
        "attendance_criteria": get("attendanceCriteria"),
        "teaching_assistants": [t["name"] for t in ev.get("eventTeachingAssistants") or [] if t.get("name")],
    }
    if unit == "days" and duration and duration != len(days):
        print(f"WARNING: platform duration is {duration} days but {len(days)} session dates were found — check 'days'")
    return info


async def cmd_program(args) -> None:
    slug = slug_of(args.link)
    async with AthkaXClient() as client:
        raw: dict = {}
        try:
            await client.ensure_login(args.nafath_id)
            raw["instructor_event"] = await client.get_instructor_program(slug)
        except httpx.HTTPStatusError as e:
            print("instructor endpoint failed:", e.response.status_code)
        try:
            raw["public_event"] = await client.get_program(slug)
        except httpx.HTTPStatusError as e:
            print("public endpoint failed:", e.response.status_code)
        try:
            raw["training_weeks"] = await client.get_topics(slug)
        except httpx.HTTPStatusError:
            pass
    if not raw:
        raise SystemExit("Could not read the program from AthkaX")
    info = summarize(slug, raw)
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "program_raw.json"), "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "program.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    print(f"program.json: {info['program_name']} | {info['instructor']} | {info['start_date']}..{info['end_date']}"
          f" | {info['num_days']} days | {info['delivery']} | batch {info['batch_id']}")
    missing = [k for k in ("program_name", "instructor", "start_date", "end_date", "days", "delivery") if not info[k]]
    if missing:
        print("MISSING:", missing, "— see program_raw.json")


async def cmd_programs(args) -> None:
    async with AthkaXClient() as client:
        await client.ensure_login(args.nafath_id)
        for e in (await client.get_programs())["events"]:
            prog = await client.get_program(e["slug"])
            batches = ", ".join(str(b["id"]) for b in prog.get("batches", []))
            print(f"- {e.get('title') or e.get('name') or ''} | {BASE}/programs/{e['slug']} | batches: {batches}")


async def cmd_roster(args) -> None:
    """Save the batch's learners (batch-learner id, name, email, Nafath ID) to students.json for the workbook."""
    async with AthkaXClient() as client:
        await client.ensure_login(args.nafath_id)
        step = lambda name, e: SystemExit(f"{name}: HTTP {e.response.status_code} ({e.request.url.path})")
        slug = slug_of(args.link)
        try:
            await client.get_instructor_program(slug)
        except httpx.HTTPStatusError as e:
            raise step("program details", e)
        batch = await pick_batch(client, slug, args.batch)
        learners = (await client.get_roster(slug, batch))["batchLearners"]
        try:
            details = await asyncio.gather(*(client.get_learner(slug, s["eventLearnerId"]) for s in learners))
        except httpx.HTTPStatusError as e:
            raise step("learner details (Nafath ID)", e)
    rows = [{"id": s["id"], "name": ((s.get("learnerDetails") or {}).get("name") or "").strip(),
             "email": ((s.get("learnerDetails") or {}).get("email") or "").strip().lower() or None,
             "nafath": str(n.get("learnerNafathId") or "").strip() or None} for s, n in zip(learners, details)]
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "students.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print(f"students.json: {len(rows)} learners | batch {batch} | {sum(1 for r in rows if r['email'])} with email"
          f" | {sum(1 for r in rows if r['nafath'])} with Nafath ID")


# ---------------------------------------------------------------- attendance push
def read_sheet(path: str) -> tuple[list[dt.date], dict[str, list[str]], str | None]:
    """Return (course dates, {email: [mark per day]}, program slug or None) from the workbook."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    cert = wb["Certificates"]
    slug = None
    for row in cert.iter_rows(min_row=1, max_row=10, max_col=2, values_only=True):
        if row[1] and isinstance(row[1], str) and SLUG_RE.search(row[1]):
            slug = slug_of(row[1])
    rows = list(wb["Attendance"].iter_rows(values_only=True))
    header = rows[0]
    day_cols, dates = [], []
    for i, h in enumerate(header):
        if isinstance(h, dt.datetime):
            d = h.date()
        elif isinstance(h, dt.date):
            d = h
        elif isinstance(h, str) and re.fullmatch(r"\s*\d{4}-\d{2}-\d{2}\s*", h):
            d = dt.date.fromisoformat(h.strip())
        else:
            continue
        day_cols.append(i)
        dates.append(d)
    if not dates:
        raise SystemExit("No date columns (YYYY-MM-DD) found in the Attendance sheet header")
    sheet = {}
    for row in rows[1:]:
        email = (row[1] or "").strip().lower()
        if email:
            sheet[email] = [str(row[i] or "").strip().lower() for i in day_cols]
    return dates, sheet, slug


async def pick_batch(client: AthkaXClient, slug: str, batch: str | None) -> str:
    """The batch as the roster endpoint accepts it: tries the batch slug, then the numeric id."""
    if batch:
        return batch
    batches = (await client.get_program(slug)).get("batches", [])
    if len(batches) != 1:
        raise SystemExit(f"Program has {len(batches)} batches — rerun with --batch ID: {[b['id'] for b in batches]}")
    tried = []
    for cand in dict.fromkeys(str(x) for x in (batches[0].get("id"), batches[0].get("slug")) if x):
        try:
            await client.json(f"/api/v1/instructor/events/{slug}/batches/{cand}/batch_learners/attendances", page=1, date=str(dt.date.today()))
            return cand
        except httpx.HTTPStatusError as e:
            tried.append(f"{cand} -> {e.response.status_code}")
    raise SystemExit(f"Roster endpoint refused every batch form: {'; '.join(tried)}")


async def cmd_attendance(args) -> None:
    """Sync the sheet to the platform: fetch the current mark of every learner on every course date and
    send only the marks that differ (idempotent; safe to re-run). Learners not on the sheet, or absent on
    every day, are set to --default (leave)."""
    all_dates, sheet, wb_slug = read_sheet(args.workbook)
    dates = all_dates
    if args.date:                                # only fetch and mark these dates (all-days rules still use every column)
        want_dates = {dt.date.fromisoformat(d) for d in args.date}
        if unknown := want_dates - set(all_dates):
            raise SystemExit(f"--date not in the Attendance sheet: {', '.join(map(str, sorted(unknown)))}")
        dates = [d for d in all_dates if d in want_dates]
    slug = slug_of(args.program) if args.program else wb_slug
    if not slug:
        raise SystemExit("No program link in the workbook — pass --program <link or slug>")
    out_dir = os.path.dirname(os.path.abspath(args.workbook))
    async with AthkaXClient() as client:
        await client.ensure_login(args.nafath_id)
        batch = await pick_batch(client, slug, args.batch)
        rosters = await asyncio.gather(*(client.get_roster(slug, batch, d) for d in dates))
        with open(os.path.join(out_dir, "athkax_roster.json"), "w", encoding="utf-8") as f:
            json.dump({d.isoformat(): r for d, r in zip(dates, rosters)}, f, ensure_ascii=False, indent=1)
        current: dict[tuple[int, dt.date], str] = {}
        learners: dict[str, list[int]] = {}   # email -> batch-learner ids (AthkaX may enrol a person twice)
        no_email = 0
        for d, r in zip(dates, rosters):
            for s in r["batchLearners"]:
                email = ((s.get("learnerDetails") or {}).get("email") or "").strip().lower()
                if not email:
                    no_email += d == dates[0]
                    continue
                if s["id"] not in learners.setdefault(email, []):
                    learners[email].append(s["id"])
                current[(s["id"], d)] = (s.get("availabilityByDate") or {}).get("availability") or "unmarked"
        only_sheet = sorted(sheet.keys() - learners.keys())
        only_platform = sorted(learners.keys() - sheet.keys())
        print(f"program {slug} batch {batch} | {dates[0]}..{dates[-1]} ({len(dates)} days)"
              f" | sheet {len(sheet)} | platform {len(learners)} people / {sum(map(len, learners.values()))} records"
              f" (+{no_email} without email, untouched)")
        with open(os.path.join(out_dir, "athkax_mismatches.json"), "w", encoding="utf-8") as f:
            json.dump({"only_on_sheet": only_sheet, "only_on_platform": only_platform}, f, ensure_ascii=False, indent=1)
        short = lambda xs: ", ".join(xs[:5]) + (f" … (+{len(xs) - 5})" if len(xs) > 5 else "")
        if only_sheet:
            print(f"only on sheet ({len(only_sheet)}, skipped): {short(only_sheet)}")
        if only_platform:
            print(f"only on platform ({len(only_platform)}, set to {args.default}): {short(only_platform)}")
        plan = []
        for email, lids in learners.items():
            marks = sheet.get(email)
            never = marks is None or (args.skip_all_absent and all(m in ("absent", "") for m in marks))
            for lid in lids:
                for d in dates:
                    want = args.default if never else SHEET_TO_PLATFORM.get(marks[all_dates.index(d)])
                    if want and current.get((lid, d)) != want:
                        plan.append((email, lid, d, current.get((lid, d)), want))
        with open(os.path.join(out_dir, "attendance_plan.csv"), "w", encoding="utf-8") as f:
            f.write("email,date,current,new\n" + "".join(f"{e},{d},{c},{w}\n" for e, _, d, c, w in plan))
        summary: dict[str, int] = {}
        for *_, c, w in plan:
            summary[f"{c}->{w}"] = summary.get(f"{c}->{w}", 0) + 1
        print(f"changes: {len(plan)} {summary} (details: attendance_plan.csv)")
        if not plan or args.dry_run:
            return
        if not args.yes and input("Proceed? [y/N] ").strip().lower() != "y":
            print("Cancelled.")
            return
        await asyncio.gather(*(client.mark_attendance(slug, lid, w, d) for _, lid, d, _, w in plan))
        print(f"Done: {len(plan)} marks updated.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--nafath-id", help="National/Iqama ID for Nafath login (otherwise prompted when needed)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("program", help="fetch a program's details into program.json")
    p.add_argument("link", help="program link (https://athkax.sdaia.gov.sa/programs/<slug>) or slug")
    p.add_argument("--out", default=".", help="folder for program.json / program_raw.json (default: current)")
    sub.add_parser("programs", help="list your ongoing programs")
    ro = sub.add_parser("roster", help="save the batch's learners (id, name, email, Nafath ID) to students.json")
    ro.add_argument("link", help="program link or slug")
    ro.add_argument("--batch", help="batch slug or id (default: the program's only batch)")
    ro.add_argument("--out", default=".", help="folder for students.json (default: current)")
    t = sub.add_parser("attendance", help="push the workbook's Attendance sheet to AthkaX")
    t.add_argument("workbook")
    t.add_argument("--program", help="program link or slug (default: the link in the Certificates sheet)")
    t.add_argument("--batch", help="batch id (default: the program's only batch)")
    t.add_argument("--default", default="leave", choices=["leave", "absent", "unmarked"],
                   help="mark for learners not on the sheet or absent every day (default: leave)")
    t.add_argument("--no-skip-all-absent", dest="skip_all_absent", action="store_false",
                   help="also mark students who were absent every day (default: they keep the default mark)")
    t.add_argument("--date", action="append", metavar="YYYY-MM-DD",
                   help="only sync this date (repeatable; default: every date column in the sheet)")
    t.add_argument("--dry-run", action="store_true", help="show the plan without changing anything")
    t.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = ap.parse_args()
    asyncio.run({"program": cmd_program, "programs": cmd_programs, "attendance": cmd_attendance, "roster": cmd_roster}[args.cmd](args))


if __name__ == "__main__":
    main()

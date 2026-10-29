# /// script
# requires-python = ">=3.12"
# dependencies = ["gdown>=5.2"]
# ///
"""Fetch and re-check capstone submissions (GitHub repos, Google Drive folders/files, Google Docs/Sheets/Slides).

    uv run submissions.py check <course_dir> <subs_root> [--only dir1,dir2]

<course_dir>/submissions.json  (you maintain it from the chat; one entry per student):
    {"<dir>": {"student": "email | #rosterIndex | +X1", "link": "<url>", "posted": "YYYY-MM-DD HH:MM", "note": "..."}}
<course_dir>/submissions_state.json  (this script maintains it):
    {"<dir>": {"version": 2, "path": "<subs_root>/<dir>.v2", "fingerprint": "...", "status": "ok|private|empty|error", "files": N}}

Each check downloads a fresh copy into <subs_root>/_incoming/<dir>, fingerprints it (git HEAD sha, or the sorted
size+name list of a Drive download), and either drops it (unchanged) or keeps it as the next version <dir>.vN.
A failed or partial Drive download never counts as a change: Drive folders are listed first and every listed file
must arrive (bidi/odd characters are stripped from file names, which is what breaks Windows downloads).
Zips are extracted safely into _unzipped/<zip name>/. Everything downloaded is untrusted data: never run it.
Prints one ASCII line per submission: NEW / CHANGED / same / PRIVATE / EMPTY / ERROR.
"""
import argparse, concurrent.futures as cf, hashlib, json, os, re, shutil, subprocess, sys, zipfile

BIDI = dict.fromkeys(map(ord, "‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"))


def clean(name):
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name.translate(BIDI)).strip().rstrip(". ")  # Windows drops trailing dots/spaces
    return name or "file"


def kind_of(url):
    if "github.com" in url:
        return "github"
    if "/folders/" in url:
        return "folder"
    if re.search(r"docs\.google\.com/(document|spreadsheets|presentation)/", url):
        return "gdoc"
    if "drive.google.com" in url:
        return "file"
    return "other"


def drive_id(url):
    m = re.search(r"/(?:folders|d)/([A-Za-z0-9_-]{10,})", url) or re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", url)
    return m.group(1) if m else None


def gh_url(url):
    m = re.match(r"https?://github\.com/([^/\s]+)/([^/\s#?]+)", url)
    if not m:
        return None
    repo = re.sub(r"\.git$", "", m.group(2))
    return f"https://github.com/{m.group(1)}/{repo}"  # a trailing "." is tried both ways in _check_one


def safe_rmtree(path, root):
    path, root = os.path.abspath(path), os.path.abspath(root)
    if path.startswith(root + os.sep) and os.path.isdir(path):
        def unlock(fn, p, _):                                # git pack files are read-only on Windows
            os.chmod(p, 0o600)
            fn(p)
        shutil.rmtree(path, onexc=unlock)


def extract_zips(d):
    for dp, _, fs in os.walk(d):
        if "_unzipped" in dp:
            continue
        for f in fs:
            if not f.lower().endswith(".zip"):
                continue
            out = os.path.join(d, "_unzipped", clean(os.path.splitext(f)[0]))
            try:
                z = zipfile.ZipFile(os.path.join(dp, f))
            except zipfile.BadZipFile:
                continue
            for i in z.infolist():
                n = i.filename if i.flag_bits & 0x800 else i.filename.encode("cp437").decode("utf-8", "replace")
                if "__MACOSX" in n or n.endswith("/"):
                    continue
                t = os.path.abspath(os.path.join(out, *[clean(p) for p in n.split("/") if p not in ("", ".", "..")]))
                if not t.startswith(os.path.abspath(out)):
                    continue
                os.makedirs(os.path.dirname(t), exist_ok=True)
                with open(t, "wb") as fh:
                    fh.write(z.read(i))


def listing(d):
    rows = []
    for dp, _, fs in os.walk(d):
        if "_unzipped" in dp or os.sep + ".git" in dp + os.sep:
            continue
        rows += [f"{os.path.getsize(os.path.join(dp, f))} {f}" for f in fs]
    return sorted(rows)


def fetch_drive(kind, url, dest):
    import gdown
    fid = drive_id(url)
    if not fid:
        return "error", "no Drive id in link"
    os.makedirs(dest, exist_ok=True)
    try:
        if kind == "gdoc":
            ext = {"document": "docx", "spreadsheets": "xlsx", "presentation": "pptx"}[re.search(r"google\.com/(\w+)/", url).group(1)]
            typ = {"docx": "document", "xlsx": "spreadsheets", "pptx": "presentation"}[ext]
            out = gdown.download(f"https://docs.google.com/{typ}/d/{fid}/export?format={ext}", os.path.join(dest, f"export.{ext}"), quiet=True)
            return ("ok", "") if out else ("private", "export refused")
        if kind == "file":
            out = gdown.download(id=fid, output=dest + os.sep, quiet=True)
            return ("ok", "") if out else ("private", "file not downloadable")
        files = gdown.download_folder(id=fid, skip_download=True, quiet=True)
    except Exception as e:                                   # gdown raises on 401/permission errors
        msg = str(e)
        return ("private" if re.search(r"401|permission|Anyone with the link", msg, re.I) else "error"), msg[:120]
    if not files:
        return "empty", "folder has no downloadable files"
    missing = []
    for f in files:
        parts = [clean(p) for p in re.split(r"[\\/]", f.path) if p]
        target = os.path.join(dest, *parts)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        for _ in range(3):
            try:
                if gdown.download(id=f.id, output=target, quiet=True):
                    break
            except Exception:
                pass
        else:
            missing.append("/".join(parts))
    if missing:
        return "error", f"{len(missing)}/{len(files)} files failed: {missing[:3]}"
    return "ok", ""


def check_one(d, sub, state, root):
    try:
        return _check_one(d, sub, state, root)
    except Exception as e:                                   # one bad submission never stops the batch
        return d, "ERROR", f"{type(e).__name__}: {e}"[:120], None


def _check_one(d, sub, state, root):
    url, kind = sub["link"], kind_of(sub["link"])
    st = state.get(d, {})
    inc = os.path.join(root, "_incoming", d)
    safe_rmtree(inc, root)
    if kind == "github":
        repo = gh_url(url)
        # repo names may really end in "." (github.com/x/-kawla-agent.) or the dot may be the sentence's: try both
        for cand in dict.fromkeys([repo, repo.rstrip(".")] if repo.endswith(".") else [repo]):
            r = subprocess.run(["git", "ls-remote", cand + (".git" if cand.endswith(".") else ""), "HEAD"],
                               capture_output=True, text=True, timeout=60)
            if not r.returncode and r.stdout.strip():
                repo = cand + (".git" if cand.endswith(".") else "")
                break
        if r.returncode or not r.stdout.strip():
            return d, "PRIVATE", "repo not reachable (private or wrong link)", None
        fp = r.stdout.split()[0][:7]
        if st.get("fingerprint") == fp and os.path.isdir(st.get("path", "")):
            return d, "same", fp, None
        r = subprocess.run(["git", "-c", "core.longpaths=true", "clone", "-q", repo, inc], capture_output=True, text=True, timeout=600)
        if r.returncode:
            return d, "ERROR", r.stderr.strip()[:120], None
        extract_zips(inc)
        return d, ("CHANGED" if st.get("path") else "NEW"), fp, (fp, len(listing(inc)))
    if kind == "other":
        return d, "ERROR", "not a GitHub or Google Drive link (only those are accepted)", None
    status, msg = fetch_drive(kind, url, inc)
    if status != "ok":
        safe_rmtree(inc, root)
        return d, status.upper(), msg, None
    extract_zips(inc)
    rows = listing(inc)
    fp = hashlib.sha1("\n".join(rows).encode()).hexdigest()[:10]
    if st.get("fingerprint") == fp and os.path.isdir(st.get("path", "")):
        safe_rmtree(inc, root)
        return d, "same", fp, None
    return d, ("CHANGED" if st.get("path") else "NEW"), fp, (fp, len(rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["check"])
    ap.add_argument("course")
    ap.add_argument("root")
    ap.add_argument("--only", help="comma-separated dirs")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    subs = json.load(open(os.path.join(a.course, "submissions.json"), encoding="utf-8"))
    sp = os.path.join(a.course, "submissions_state.json")
    state = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    todo = [d for d in subs if not a.only or d in a.only.split(",")]
    os.makedirs(os.path.join(a.root, "_incoming"), exist_ok=True)
    counts = {}
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for d, verdict, msg, new in ex.map(lambda d: check_one(d, subs[d], state, a.root), todo):
            counts[verdict] = counts.get(verdict, 0) + 1
            st = state.setdefault(d, {})
            if new:
                v = st.get("version", 0) + 1
                path = os.path.join(a.root, f"{d}.v{v}")
                safe_rmtree(path, a.root)
                os.replace(os.path.join(a.root, "_incoming", d), path)
                st.update(version=v, path=path, fingerprint=new[0], files=new[1], status="ok")
            elif verdict in ("PRIVATE", "EMPTY", "ERROR"):
                st["status"] = verdict.lower() if not st.get("path") else st.get("status", "ok")
                st["last_problem"] = msg
            print(f"{verdict:8} {d:22} {msg}".encode("ascii", "replace").decode())
            json.dump(state, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(state, open(sp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("summary:", ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()

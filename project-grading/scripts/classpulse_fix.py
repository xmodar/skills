#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["cryptography>=42", "openpyxl>=3.1"]
# ///
"""Investigate and repair identities in a ClassPulse backup. The instructor runs it in his terminal (password prompt).

    uv run classpulse_fix.py inspect     <course_dir> <out.txt> <key> [<key> ...]
    uv run classpulse_fix.py move-device <course_dir> <deviceId> <fromRosterId> <toRosterId>   [--backup FILE]

inspect: writes (UTF-8) every roster entry, join, admit/reject, device request/approval and response that mentions a
  key (name fragment, roster ID, email, device id), with local times and the device of each answer. Read-only.
  Typical case — "ClassPulse shows me someone else's name": a second browser/phone that asked to join under another
  learner's roster ID and was approved by the trainer (p.deviceRequest + p.device approved) sits on the wrong person.
  Evidence: the device joins in step with the claimant's own device and answers under the other identity.
move-device: moves that device and its events (joins, device request/approval, presence, responses) from one learner to
  the other in every session where the target learner joined, and moves it in the course roster; re-encrypts with the
  same password (fresh salt/iv), verifies, keeps the original as backup/<name>.pre-fix-<time>.cpbackup, then reruns
  classpulse.py. Afterwards: diff classpulse_marks.json against the previous copy, rebuild, and re-import the fixed
  backup into ClassPulse before the next session.
"""
import argparse, base64, copy, datetime as dt, getpass, glob, json, os, shutil, subprocess, sys, time, zlib
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from classpulse import decrypt  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("cmd", choices=["inspect", "move-device"])
ap.add_argument("course")
ap.add_argument("args", nargs="+")
ap.add_argument("--backup")
a = ap.parse_args()
path = a.backup or max(glob.glob(os.path.join(a.course, "classpulse-*.cpbackup")), key=os.path.getmtime)
pw = os.environ.get("CLASSPULSE_PASSWORD") or getpass.getpass("ClassPulse backup password: ")
data = decrypt(path, pw)
loc = lambda ms: (dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc) + dt.timedelta(hours=3)).strftime("%Y-%m-%d %H:%M") if isinstance(ms, (int, float)) else ms
sess = {s["id"]: loc(s.get("startedAt")) for s in data.get("sessions", [])}

if a.cmd == "inspect":
    out, keys = a.args[0], [k.lower() for k in a.args[1:]]
    hit = lambda o: any(k in json.dumps(o, ensure_ascii=False).lower() for k in keys)
    pids = {e["p"]["id"] for e in data["events"] if e["type"] == "p.join" and hit(e)}
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"backup {os.path.basename(path)}\n")
        for c in data.get("courses", []):
            for r in c.get("roster", []):
                if hit(r):
                    f.write(f"[roster] {json.dumps(r, ensure_ascii=False)[:600]}\n")
        for e in sorted(data["events"], key=lambda e: e["t"]):
            t = e["type"]
            if t == "p.join" and e["p"]["id"] in pids:
                p = e["p"]
                f.write(f"[join] session {sess.get(e.get('sessionId'))} at {loc(e['t'])} pid={p['id']} rid={p.get('rosterId')} "
                        f"name={p.get('name')} devices={p.get('devices')} mobile={p.get('mobile')} status={p.get('status')}\n")
            elif t in ("p.admit", "p.reject", "p.device", "p.deviceRequest") and (e.get("pid") in pids or hit(e)):
                f.write(f"[{t}] {loc(e['t'])} {json.dumps({k: v for k, v in e.items() if k not in ('t', 'n')}, ensure_ascii=False)}\n")
            elif t == "resp" and (e["r"].get("pid") in pids or hit(e["r"])):
                f.write(f"[resp] {loc(e['t'])} pid={e['r'].get('pid')} device={e['r'].get('device')} cp={e['r'].get('cp')}\n")
    print("wrote", out)
    sys.exit()

DEV, SRC, DST = a.args[:3]
src_p, dst_p = {}, {}
for e in data["events"]:
    if e["type"] == "p.join":
        rid, sid = (e["p"].get("rosterId") or "").strip(), e.get("sessionId")
        if rid == SRC:
            src_p.setdefault(sid, set()).add(e["p"]["id"])
        elif rid == DST and DEV not in e["p"].get("devices", []):
            dst_p[sid] = e["p"]
changes = {}
for e in data["events"]:
    sid = e.get("sessionId")
    if sid not in dst_p:
        continue
    d = dst_p[sid]
    if e["type"] == "p.join" and DEV in e["p"].get("devices", []) and e["p"]["id"] in src_p.get(sid, ()):
        p = copy.deepcopy(d)
        p.update(devices=[DEV], joinedAt=e["p"].get("joinedAt", d.get("joinedAt")), mobile=e["p"].get("mobile", d.get("mobile")))
        e["p"] = p
    elif e["type"] == "resp" and e["r"].get("device") == DEV and e["r"].get("pid") in src_p.get(sid, ()):
        e["r"]["pid"] = d["id"]
    elif e.get("device") == DEV and e.get("pid") in src_p.get(sid, ()):
        e["pid"] = d["id"]
    else:
        continue
    changes[e["type"]] = changes.get(e["type"], 0) + 1
for c in data.get("courses", []):
    for r in c.get("roster", []):
        rid = (r.get("rosterId") or "").strip()
        if rid == SRC and DEV in r.get("devices", []):
            r["devices"].remove(DEV); changes["roster-remove"] = 1
        elif rid == DST and DEV not in r.get("devices", []):
            r.setdefault("devices", []).append(DEV); changes["roster-add"] = 1
print("changes:", changes, "| sessions where the source has joins but the target none (left as is):",
      sum(1 for s in src_p if s not in dst_p))
if not changes:
    sys.exit("nothing to change")
env = json.load(open(path, encoding="utf-8"))
salt, iv = os.urandom(16), os.urandom(12)
key = PBKDF2HMAC(hashes.SHA256(), 32, salt, env.get("iter", 310_000)).derive(pw.encode())
co = zlib.compressobj(9, zlib.DEFLATED, -15)
plain = co.compress(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()) + co.flush()
enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
env.update(salt=enc(salt), data=enc(iv + AESGCM(key).encrypt(iv, plain, None)))
tmp = path + ".tmp"
json.dump(env, open(tmp, "w", encoding="utf-8"))
assert len(decrypt(tmp, pw)["events"]) == len(data["events"]), "verification failed"
os.makedirs(os.path.join(a.course, "backup"), exist_ok=True)
keep = os.path.join(a.course, "backup", os.path.basename(path).replace(".cpbackup", f".pre-fix-{time.strftime('%H%M')}.cpbackup"))
shutil.copy2(path, keep)
marks = os.path.join(a.course, "classpulse_marks.json")
if os.path.exists(marks):
    shutil.copy2(marks, os.path.join(a.course, "backup", f"classpulse_marks.pre-fix-{time.strftime('%H%M')}.json"))
os.replace(tmp, path)
print("fixed backup written; original kept as", keep)
os.environ["CLASSPULSE_PASSWORD"] = pw
sys.exit(subprocess.run(["uv", "run", "-q", os.path.join(HERE, "classpulse.py"), a.course, "--backup", path]).returncode)

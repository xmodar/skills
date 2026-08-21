#!/usr/bin/env node
// Claude Desktop keeps the conversation-history LIST and the conversations themselves
// in two different places:
//
//   index       <appdata>/Claude/claude-code-sessions/<accountId>/<orgId>/local_<uuid>.json
//   transcript  ~/.claude/projects/<encoded-cwd>/<cliSessionId>.jsonl
//
// The index is what the history list renders; the transcript is the actual conversation.
// They drift apart in both directions, and this script fixes either drift:
//
//   restore   transcript on disk, no index entry  ->  rebuild the entry (default)
//   prune     transcript on disk, no index entry  ->  delete the transcript
//
// Both are dry runs until you pass --apply.
//
//   node restore-sessions.mjs                  # what is missing from the list
//   node restore-sessions.mjs --apply
//   node restore-sessions.mjs prune            # what is on disk but invisible
//   node restore-sessions.mjs prune --apply
//
// Shared flags:
//   --apply                 actually write (default is a dry run)
//   --project <substr>      only sessions whose cwd contains <substr>
//   --since <YYYY-MM-DD>    only sessions active on/after this date
//   --json                  machine-readable output
//   --index-dir <path>      override the index directory
//   --transcript-root <p>   override ~/.claude/projects
//
// restore only:
//   --min-messages <n>      skip transcripts with fewer user messages (default 1)
//   --include-archived      re-list sessions you had archived on purpose
//   --include-deleted       also re-list sessions you deleted in the app on purpose
//
// prune only:
//   --min-age-hours <n>     protect transcripts touched recently (default 24)
//   --hard                  unlink instead of moving to ~/.claude/deleted-transcripts

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import readline from 'node:readline';

// ---------------------------------------------------------------- args

const argv = process.argv.slice(2);
const COMMAND = ['restore', 'prune'].includes(argv[0]) ? argv[0] : 'restore';
const has = (f) => argv.includes(f);
const val = (f, d = null) => {
  const i = argv.indexOf(f);
  return i !== -1 && argv[i + 1] ? argv[i + 1] : d;
};

const APPLY = has('--apply');
const AS_JSON = has('--json');
const PROJECT = val('--project');
const SINCE = val('--since') ? Date.parse(val('--since')) : null;
const MIN_MSGS = Number(val('--min-messages', '1'));
const INCLUDE_ARCHIVED = has('--include-archived');
const INCLUDE_DELETED = has('--include-deleted');
const MIN_AGE_HOURS = Number(val('--min-age-hours', '24'));
const HARD = has('--hard');

function fail(msg) {
  console.error(`error: ${msg}`);
  process.exit(1);
}

if (SINCE !== null && Number.isNaN(SINCE)) fail('--since must be YYYY-MM-DD');
if (Number.isNaN(MIN_AGE_HOURS) || MIN_AGE_HOURS < 0) fail('--min-age-hours must be a non-negative number');

const out = (...a) => { if (!AS_JSON) console.log(...a); };

// ---------------------------------------------------------------- locations

const HOME = os.homedir();
const TRANSCRIPT_ROOT = val('--transcript-root') || path.join(HOME, '.claude', 'projects');

function appDataDir() {
  if (process.platform === 'win32') {
    return path.join(process.env.APPDATA || path.join(HOME, 'AppData', 'Roaming'), 'Claude');
  }
  if (process.platform === 'darwin') {
    return path.join(HOME, 'Library', 'Application Support', 'Claude');
  }
  return path.join(process.env.XDG_CONFIG_HOME || path.join(HOME, '.config'), 'Claude');
}

// The index nests one directory per account, then one per org. Those ids are the
// app's, not ours - never invent them. If the app has never written the tree there
// is nothing safe to guess at, so say so and stop.
function findIndexDir() {
  const override = val('--index-dir');
  if (override) {
    fs.mkdirSync(override, { recursive: true });
    return override;
  }

  const root = path.join(appDataDir(), 'claude-code-sessions');
  if (!fs.existsSync(root)) {
    fail(
      `no session index at ${root}\n` +
      `  The app creates it on launch. Open Claude Desktop, start one session in any\n` +
      `  project so the account/org folders exist, then run this again.`,
    );
  }

  const leaves = [];
  for (const acct of fs.readdirSync(root, { withFileTypes: true })) {
    if (!acct.isDirectory()) continue;
    const acctPath = path.join(root, acct.name);
    for (const org of fs.readdirSync(acctPath, { withFileTypes: true })) {
      if (!org.isDirectory()) continue;
      const p = path.join(acctPath, org.name);
      const n = fs.readdirSync(p).filter((f) => f.startsWith('local_') && f.endsWith('.json')).length;
      leaves.push({ path: p, entries: n, mtime: fs.statSync(p).mtimeMs });
    }
  }

  if (leaves.length === 0) fail(`no account/org folder under ${root} - launch Claude Desktop once, then re-run.`);
  leaves.sort((a, b) => b.mtime - a.mtime);
  if (leaves.length > 1) {
    out(`note: ${leaves.length} account/org folders found, using the most recent:`);
    for (const l of leaves) out(`      ${l.path}  (${l.entries} entries)`);
    out('      pass --index-dir to pick another.\n');
  }
  return leaves[0].path;
}

// Sessions with a live CLI process. Never restore over one, never prune one.
function liveSessionIds() {
  const dir = path.join(HOME, '.claude', 'sessions');
  const live = new Set();
  if (!fs.existsSync(dir)) return live;
  for (const f of fs.readdirSync(dir)) {
    if (!f.endsWith('.json')) continue;
    try {
      const o = JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
      if (o.sessionId) live.add(o.sessionId);
    } catch { /* a stale pid file is not worth failing over */ }
  }
  return live;
}

// ---------------------------------------------------------------- transcripts

// A uuid-v4-shaped id derived from the transcript id, so re-running this script
// rewrites the same entry instead of piling up duplicates of one conversation.
function derivedUuid(seed) {
  const h = crypto.createHash('sha256').update(`ccd-restore:${seed}`).digest();
  const b = Buffer.from(h.subarray(0, 16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const s = b.toString('hex');
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}-${s.slice(16, 20)}-${s.slice(20)}`;
}

function textOf(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) {
    const t = content.find((p) => p?.type === 'text');
    if (t) return t.text;
  }
  return null;
}

// Real prompts only: no tool results, no hook or reminder envelopes, no slash-command
// plumbing. Those are wrapped in XML-ish tags, so strip tags and see what is left.
function humanPrompt(raw) {
  if (!raw || typeof raw !== 'string') return null;
  if (raw.includes('tool_result') || raw.includes('<local-command')) return null;
  const stripped = raw
    .replace(/<command-[a-z-]+>[\s\S]*?<\/command-[a-z-]+>/g, ' ')
    .replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return stripped.length >= 2 ? stripped : null;
}

async function readTranscript(file) {
  const st = fs.statSync(file);
  const rec = {
    cliSessionId: path.basename(file, '.jsonl'),
    file,
    bytes: st.size,
    mtime: st.mtimeMs,
    cwd: null,
    model: null,
    firstTs: null,
    lastTs: null,
    firstUser: null,
    summary: null,
    userMsgs: 0,
  };

  const rl = readline.createInterface({
    input: fs.createReadStream(file, { encoding: 'utf8' }),
    crlfDelay: Infinity,
  });

  for await (const line of rl) {
    if (!line.trim()) continue;
    let o;
    try { o = JSON.parse(line); } catch { continue; }

    if (o.cwd && !rec.cwd) rec.cwd = o.cwd;
    if (o.message?.model) rec.model = o.message.model;
    if (o.type === 'summary' && typeof o.summary === 'string' && !rec.summary) rec.summary = o.summary;

    if (o.timestamp) {
      const t = Date.parse(o.timestamp);
      if (!Number.isNaN(t)) {
        if (rec.firstTs === null || t < rec.firstTs) rec.firstTs = t;
        if (rec.lastTs === null || t > rec.lastTs) rec.lastTs = t;
      }
    }

    if (o.type === 'user' && !o.isMeta && !o.isSidechain) {
      const prompt = humanPrompt(textOf(o.message?.content));
      if (prompt) {
        rec.userMsgs++;
        if (!rec.firstUser) rec.firstUser = prompt.slice(0, 300);
      }
    }
  }

  return rec;
}

function titleFor(rec) {
  const raw = (rec.summary || rec.firstUser || '').replace(/\s+/g, ' ').trim();
  if (!raw) return 'Untitled session';
  let t = raw.replace(/^@\S+\s*/, '').replace(/^(let'?s|please)\s+/i, '');
  t = t.slice(0, 60).trim();
  if (raw.length > 60) t = `${t.replace(/[,;:.\s]+\S*$/, '')}…`;
  return t.charAt(0).toUpperCase() + t.slice(1);
}

const mb = (n) => `${(n / 1048576).toFixed(1)}MB`;
const when = (ts) => (ts ? new Date(ts).toISOString().replace('T', ' ').slice(0, 16) : '?'.padEnd(16));

// ---------------------------------------------------------------- read both sides

if (!fs.existsSync(TRANSCRIPT_ROOT)) fail(`no transcripts at ${TRANSCRIPT_ROOT}`);

const INDEX_DIR = findIndexDir();
const LIVE = liveSessionIds();

const indexed = new Map();
// Deleting a conversation in the app leaves a file named deleted_<cliSessionId> holding
// a timestamp. That is a record of intent, not damage: the transcript stays on disk but
// the user asked for it gone. Restoring over one un-deletes something deliberately
// deleted, so it takes --include-deleted to do it.
const tombstones = new Set();

for (const f of fs.readdirSync(INDEX_DIR)) {
  if (f.startsWith('deleted_')) { tombstones.add(f.slice('deleted_'.length)); continue; }
  if (!f.startsWith('local_') || !f.endsWith('.json')) continue;
  try {
    const o = JSON.parse(fs.readFileSync(path.join(INDEX_DIR, f), 'utf8'));
    if (o.cliSessionId) indexed.set(o.cliSessionId, o);
  } catch { /* a corrupt entry is not a reason to abort */ }
}

const transcripts = [];
for (const dir of fs.readdirSync(TRANSCRIPT_ROOT, { withFileTypes: true })) {
  if (!dir.isDirectory()) continue;
  const projDir = path.join(TRANSCRIPT_ROOT, dir.name);
  for (const f of fs.readdirSync(projDir)) {
    if (f.endsWith('.jsonl')) transcripts.push(path.join(projDir, f));
  }
}

const records = [];
for (const file of transcripts) records.push(await readTranscript(file));
records.sort((a, b) => (b.lastTs ?? 0) - (a.lastTs ?? 0));

const passesFilters = (rec) => {
  if (PROJECT && !(rec.cwd || '').toLowerCase().includes(PROJECT.toLowerCase())) return false;
  if (SINCE !== null && (rec.lastTs ?? 0) < SINCE) return false;
  return true;
};

// ---------------------------------------------------------------- backup helper

function backupIndex() {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const dest = path.join(HOME, '.claude', 'session-index-backups', stamp);
  fs.mkdirSync(dest, { recursive: true });
  for (const f of fs.readdirSync(INDEX_DIR)) {
    const src = path.join(INDEX_DIR, f);
    if (fs.statSync(src).isFile()) fs.copyFileSync(src, path.join(dest, f));
  }
  return dest;
}

// ---------------------------------------------------------------- restore

if (COMMAND === 'restore') {
  const planned = [];
  const skipped = { indexed: 0, empty: 0, filtered: 0, archived: 0, deleted: 0 };

  for (const rec of records) {
    const existing = indexed.get(rec.cliSessionId);
    if (existing) {
      if (existing.isArchived && INCLUDE_ARCHIVED) planned.push({ rec, unarchive: existing });
      else skipped[existing.isArchived ? 'archived' : 'indexed']++;
      continue;
    }
    if (tombstones.has(rec.cliSessionId) && !INCLUDE_DELETED) { skipped.deleted++; continue; }
    if (!rec.cwd || !rec.lastTs || rec.userMsgs < MIN_MSGS) { skipped.empty++; continue; }
    if (!passesFilters(rec)) { skipped.filtered++; continue; }
    planned.push({ rec });
  }

  const entryFor = ({ rec, unarchive }) => (unarchive ? { ...unarchive, isArchived: false } : {
    sessionId: `local_${derivedUuid(rec.cliSessionId)}`,
    cliSessionId: rec.cliSessionId,
    cwd: rec.cwd,
    originCwd: rec.cwd,
    lastFocusedAt: rec.lastTs,
    createdAt: rec.firstTs ?? rec.lastTs,
    lastActivityAt: rec.lastTs,
    model: rec.model || 'claude-opus-5',
    effort: 'high',
    isArchived: false,
    title: titleFor(rec),
    titleSource: 'auto',
    permissionMode: 'auto',
    remoteMcpServersConfig: [],
    alwaysAllowedReasons: [],
    sessionPermissionUpdates: [],
    classifierSummaryEnabled: true,
    reportFindingsCard: true,
    spawnSeed: {},
  });

  const writes = planned.map((p) => ({ entry: entryFor(p), rec: p.rec }));
  // Only ever cleared for sessions we were explicitly asked to un-delete.
  const toClear = INCLUDE_DELETED ? writes.filter((w) => tombstones.has(w.rec.cliSessionId)) : [];

  if (AS_JSON) {
    console.log(JSON.stringify({
      command: 'restore', indexDir: INDEX_DIR, applied: APPLY, skipped,
      tombstonesCleared: toClear.map((w) => w.rec.cliSessionId),
      entries: writes.map((w) => w.entry),
    }, null, 2));
  } else {
    for (const w of writes) {
      const mark = tombstones.has(w.rec.cliSessionId) ? '  [you deleted this in the app]' : '';
      out(`${when(w.entry.lastActivityAt)}  ${w.rec.cliSessionId}  ${w.entry.title}${mark}`);
    }
    out(
      `\n${writes.length} to restore  (${skipped.indexed} already listed, ` +
      `${skipped.empty} empty, ${skipped.filtered} filtered, ${skipped.archived} archived, ` +
      `${skipped.deleted} deleted on purpose)`,
    );
    if (skipped.deleted) out(`pass --include-deleted to bring back the ${skipped.deleted} you deleted`);
    if (toClear.length) out(`${toClear.length} deletion marker(s) to clear`);
    out(`index:       ${INDEX_DIR}`);
    out(`transcripts: ${TRANSCRIPT_ROOT}  (${transcripts.length} files)`);
  }

  if (!APPLY) { out('\nDRY RUN - nothing written. Re-run with --apply.'); process.exit(0); }
  if (writes.length === 0) process.exit(0);

  const backup = backupIndex();
  for (const w of toClear) fs.rmSync(path.join(INDEX_DIR, `deleted_${w.rec.cliSessionId}`), { force: true });
  for (const w of writes) {
    fs.writeFileSync(path.join(INDEX_DIR, `${w.entry.sessionId}.json`), JSON.stringify(w.entry), 'utf8');
  }

  out(`\nbacked up previous index -> ${backup}`);
  if (toClear.length) out(`cleared ${toClear.length} deletion marker(s)`);
  out(`restored ${writes.length} sessions.`);
  out('Fully quit and reopen Claude Desktop - the index is read at startup.');
  out('Then OPEN each conversation you care about, so the app adopts its entry.');
  process.exit(0);
}

// ---------------------------------------------------------------- prune

// Deletes transcripts the app cannot show you: no index entry, so no way to open them
// from the history list. Conservative by default - recent files and live sessions are
// never touched, and what goes is moved to a trash folder rather than unlinked.
{
  const cutoff = Date.now() - MIN_AGE_HOURS * 3600_000;
  const doomed = [];
  const kept = { indexed: 0, live: 0, recent: 0, filtered: 0 };

  for (const rec of records) {
    if (indexed.has(rec.cliSessionId)) { kept.indexed++; continue; }
    if (LIVE.has(rec.cliSessionId)) { kept.live++; continue; }
    if (rec.mtime > cutoff) { kept.recent++; continue; }
    if (!passesFilters(rec)) { kept.filtered++; continue; }
    doomed.push(rec);
  }

  // Each transcript may have a sidecar folder of tool results next to it.
  for (const rec of doomed) {
    const side = path.join(path.dirname(rec.file), rec.cliSessionId);
    rec.sidecar = fs.existsSync(side) && fs.statSync(side).isDirectory() ? side : null;
  }

  const total = doomed.reduce((n, r) => n + r.bytes, 0);

  if (AS_JSON) {
    console.log(JSON.stringify({
      command: 'prune', applied: APPLY, hard: HARD, minAgeHours: MIN_AGE_HOURS, kept,
      bytes: total,
      deleting: doomed.map((r) => ({ cliSessionId: r.cliSessionId, file: r.file, cwd: r.cwd, bytes: r.bytes, lastTs: r.lastTs, title: titleFor(r) })),
    }, null, 2));
  } else {
    for (const r of doomed) {
      out(`${when(r.lastTs)}  ${r.cliSessionId}  ${mb(r.bytes).padStart(7)}  ${titleFor(r)}`);
    }
    out(
      `\n${doomed.length} transcript(s) not visible in the app, ${mb(total)}  ` +
      `(kept: ${kept.indexed} listed, ${kept.live} live, ${kept.recent} newer than ` +
      `${MIN_AGE_HOURS}h, ${kept.filtered} filtered)`,
    );
    out(`transcripts: ${TRANSCRIPT_ROOT}  (${transcripts.length} files)`);
    out(HARD ? 'mode: --hard, files are unlinked' : 'mode: moved to ~/.claude/deleted-transcripts');
  }

  if (!APPLY) { out('\nDRY RUN - nothing deleted. Re-run with --apply.'); process.exit(0); }
  if (doomed.length === 0) process.exit(0);

  let trash = null;
  if (!HARD) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    trash = path.join(HOME, '.claude', 'deleted-transcripts', stamp);
    fs.mkdirSync(trash, { recursive: true });
  }

  for (const r of doomed) {
    const targets = [r.file, ...(r.sidecar ? [r.sidecar] : [])];
    for (const t of targets) {
      if (HARD) {
        fs.rmSync(t, { recursive: true, force: true });
      } else {
        // Keep the project folder name so a restore knows which cwd it came from.
        const dest = path.join(trash, path.basename(path.dirname(r.file)), path.basename(t));
        fs.mkdirSync(path.dirname(dest), { recursive: true });
        fs.renameSync(t, dest);
      }
    }
  }

  out(`\ndeleted ${doomed.length} transcript(s), ${mb(total)}`);
  if (trash) out(`moved to ${trash} - delete that folder to reclaim the space for good.`);
}

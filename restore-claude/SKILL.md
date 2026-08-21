---
name: restore-claude
description: Repair Claude Desktop's conversation-history list when sessions vanish from it — after an app update, a profile reset, or a sync that dropped entries — by rebuilding the index from the transcripts on disk. Also prunes local transcripts the app can no longer show. Use when the user says their conversations/history/sessions disappeared, the sidebar is empty after updating, they want an old session back, or they want to clean up orphaned local conversation files.
---

# Restore Claude Desktop sessions

## The one thing to tell the user first

**Conversations are almost never lost.** The history list and the conversations are two
separate stores, and it is the list that breaks:

| | where | what it is |
|---|---|---|
| index | `%APPDATA%\Claude\claude-code-sessions\<accountId>\<orgId>\local_<uuid>.json` | one small JSON per session — the sidebar |
| transcript | `~/.claude/projects/<encoded-cwd>/<cliSessionId>.jsonl` | the actual conversation |

An empty sidebar means the index was reset. Check `~/.claude/projects/` before saying
anything is gone — the `.jsonl` files are the real data and survive app updates, which
recreate `%APPDATA%\Claude` from scratch.

Each index entry maps `sessionId` (`local_…`) → `cliSessionId`, which is the transcript's
filename, plus `cwd`, `createdAt`, `lastActivityAt`, `model`, `title`, `isArchived`.
That is the whole schema, so the index is regenerable and the transcripts are not.

## Restore

```bash
node ~/.claude/skills/restore-claude/restore-sessions.mjs
```

Dry run: lists every transcript with no index entry, with a title derived from its
opening message. Add `--apply` to write. The previous index is copied to
`~/.claude/session-index-backups/<timestamp>/` first, so any run is reversible by
copying that folder back.

Narrow it with `--project samai2`, `--since 2026-08-01`, `--min-messages 3`.
`--include-archived` also re-lists sessions that were archived on purpose.

Then: **fully quit and reopen the app** — the index is read at startup — and **open each
conversation that matters**.

## Deletion markers

Deleting a conversation in the app writes a **deletion marker** beside the entries: a file
named `deleted_<cliSessionId>` containing a timestamp. The transcript stays on disk, so the
session still looks restorable — but the marker records that the user asked for it gone.

`restore` therefore **skips any session carrying one**, and reports the count.
`--include-deleted` overrides that and clears the marker, genuinely un-deleting the
conversation. Do not pass it on a hunch: a marker is a decision the user already made, and
a bulk restore that ignores them refills the sidebar with conversations they cleared out.
If a session they want back is being skipped, name it and confirm before overriding.

A restored entry stays provisional until the app adopts it — opening the conversation
rewrites its file with the full field set. After a bulk restore, tell the user to open the
ones that matter.

## Prune

The mirror image: transcripts on disk with no index entry, which the app has no way to
open. Reclaims space after a history wipe the user does *not* want undone.

```bash
node ~/.claude/skills/restore-claude/restore-sessions.mjs prune
```

Dry run listing what would go, with sizes. `--apply` moves them — plus each transcript's
sidecar folder of tool results — to `~/.claude/deleted-transcripts/<timestamp>/`, grouped
by project. Deleting that folder is what actually reclaims the disk; `--hard` unlinks
directly and skips the trash.

Protected without asking: anything with an index entry, any session with a live CLI
process, and anything modified in the last 24h (`--min-age-hours`). Same `--project`
and `--since` filters.

**Confirm the list with the user before `--apply`.** `prune` is the destructive half of
this skill and the dry run is the whole point — read it out, then delete.

## When there is no index directory at all

The script stops rather than guessing: the account and org ids are the app's, and
inventing them produces entries the app will never read. Have the user launch Claude
Desktop and start one session in any project so the folders exist, then re-run.

`--index-dir` and `--transcript-root` override both paths for testing; `--json` gives
machine-readable output.

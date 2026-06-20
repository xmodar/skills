#!/usr/bin/env python3
"""Timestamp-isolated subtitle extraction and reconstruction.

The commands intentionally never print subtitle text or timestamp values. The
model-facing intermediate files contain cue IDs and subtitle text only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

try:
    import pysubs2
except ImportError:  # Keep the failure message free of source data.
    print(
        json.dumps(
            {
                "ok": False,
                "error": "dependency_missing",
                "action": "Install the skill requirements and retry.",
            }
        ),
        file=sys.stderr,
    )
    raise SystemExit(2)

try:
    from charset_normalizer import from_path as detect_charset_from_path
except ImportError:
    detect_charset_from_path = None

SCHEMA_VERSION = 1
DEFAULT_CHUNK_CUES = 100
DEFAULT_CHUNK_CHARS = 12_000
MARKUP_RE = re.compile(r"\{[^{}]*\}|</?[A-Za-z][^>]*>")
PLACEHOLDER_RE = re.compile(r"\[\[F(\d+)\]\]")
ARABIC_RE = re.compile(r"[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]")
LATIN_RE = re.compile(r"[A-Za-z]")
WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
SAFE_STATE_VALUES = {"extracted", "awaiting_approval", "translating", "complete"}


class PipelineError(RuntimeError):
    def __init__(self, code: str, message: str, *, ids: Sequence[int] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.ids = list(ids or [])


@dataclass(frozen=True)
class CueRecord:
    cue_id: int
    text: str


def emit(payload: dict[str, Any], *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=stream)


def fail(code: str, message: str, *, ids: Sequence[int] | None = None) -> None:
    raise PipelineError(code, message, ids=ids)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return slug[:72] or "subtitles"


def atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        fail("invalid_metadata", "A pipeline metadata file is missing or invalid.")


def encoding_candidates(path: Path, requested: str) -> list[str]:
    if requested.lower() != "auto":
        return [requested]

    candidates: list[str] = []
    try:
        prefix = path.read_bytes()[:4]
    except OSError:
        fail("source_unreadable", "The source file cannot be read.")

    if prefix.startswith(b"\xef\xbb\xbf"):
        candidates.append("utf-8-sig")
    elif prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates.append("utf-16")

    if detect_charset_from_path is not None:
        try:
            result = detect_charset_from_path(str(path)).best()
            if result and result.encoding:
                candidates.append(result.encoding)
        except Exception:
            pass

    candidates.extend(
        [
            "utf-8-sig",
            "utf-8",
            "utf-16",
            "cp1252",
            "cp1256",
            "cp1251",
            "gb18030",
            "shift_jis",
            "euc-kr",
        ]
    )

    unique: list[str] = []
    for item in candidates:
        normalized = item.lower().replace("_", "-")
        if normalized not in {entry.lower().replace("_", "-") for entry in unique}:
            unique.append(item)
    return unique


def load_subtitles(
    path: Path,
    *,
    encoding: str = "auto",
    fps: float | None = None,
    input_format: str | None = None,
) -> tuple[pysubs2.SSAFile, str]:
    if not path.is_file():
        fail("source_missing", "The source subtitle file does not exist.")

    for candidate in encoding_candidates(path, encoding):
        kwargs: dict[str, Any] = {"encoding": candidate}
        if fps is not None:
            kwargs["fps"] = fps
        if input_format:
            kwargs["format_"] = input_format
        try:
            subs = pysubs2.load(str(path), **kwargs)
            return subs, candidate
        except (UnicodeError, LookupError):
            continue
        except Exception:
            # Some format errors are encoding-dependent, so try all candidates.
            continue

    fail(
        "parse_failed",
        "The subtitle parser could not read this text-based subtitle file. "
        "The format may be unsupported, bitmap-based, encrypted, or require an FPS value.",
    )


def mask_markup(text: str) -> tuple[str, list[str]]:
    tags: list[str] = []

    def replace(match: re.Match[str]) -> str:
        tags.append(match.group(0))
        return f"[[F{len(tags)}]]"

    masked = MARKUP_RE.sub(replace, text)
    masked = masked.replace(r"\N", "\n").replace(r"\n", "\n").replace(r"\h", " ")
    return masked, tags


def visible_text(masked: str) -> str:
    return PLACEHOLDER_RE.sub("", masked).strip()


def translatable_events(subs: pysubs2.SSAFile) -> list[tuple[int, Any, str]]:
    result: list[tuple[int, Any, str]] = []
    cue_id = 1
    for event_index, event in enumerate(subs.events):
        try:
            is_text = bool(event.is_text)
        except Exception:
            is_text = not bool(getattr(event, "is_comment", False))
        if not is_text:
            continue
        masked, _ = mask_markup(event.text)
        if not visible_text(masked):
            continue
        result.append((cue_id, event, masked))
        cue_id += 1
    return result


def compact_record(record: CueRecord) -> str:
    return json.dumps(
        {"i": record.cue_id, "t": record.text},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def compact_text_record(record: CueRecord) -> str:
    return f"{record.cue_id}: {json.dumps(record.text, ensure_ascii=False)}"


def write_compact_text(path: Path, records: Iterable[CueRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as handle:
        for record in records:
            handle.write(compact_text_record(record))
            handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def parse_compact_text(path: Path) -> list[CueRecord]:
    records: list[CueRecord] = []
    seen: set[int] = set()
    line_re = re.compile(r"^\s*(\d+)\s*:\s*(.+?)\s*$")
    try:
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                match = line_re.match(line)
                if not match:
                    fail("invalid_compact_text", "A compact translation line must use ID: JSON-string format.")
                cue_id = int(match.group(1))
                if cue_id in seen:
                    fail("invalid_compact_text", "A compact translation file contains a duplicate cue ID.")
                try:
                    text = json.loads(match.group(2))
                except json.JSONDecodeError:
                    fail("invalid_compact_text", "A compact translation line has an invalid JSON string.")
                if not isinstance(text, str):
                    fail("invalid_compact_text", "A compact translation value must be a string.")
                records.append(CueRecord(cue_id, text))
                seen.add(cue_id)
    except OSError:
        fail("missing_intermediate", "A required compact translation file is missing.")
    return records


def write_records(path: Path, records: Iterable[CueRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline="\n"
    ) as handle:
        for record in records:
            handle.write(compact_record(record))
            handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, path)


def read_records(path: Path) -> list[CueRecord]:
    records: list[CueRecord] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                line = raw_line.rstrip("\n")
                if not line:
                    fail("invalid_intermediate", "An intermediate file contains a blank record.")
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    fail("invalid_intermediate", "An intermediate file is not valid JSONL.")
                if (
                    not isinstance(item, dict)
                    or set(item) != {"i", "t"}
                    or not isinstance(item["i"], int)
                    or not isinstance(item["t"], str)
                ):
                    fail("invalid_intermediate", "An intermediate record has the wrong schema.")
                records.append(CueRecord(item["i"], item["t"]))
    except OSError:
        fail("missing_intermediate", "A required intermediate file is missing.")
    return records


def split_chunks(records: list[CueRecord], max_cues: int, max_chars: int) -> list[list[CueRecord]]:
    chunks: list[list[CueRecord]] = []
    current: list[CueRecord] = []
    current_chars = 0
    for record in records:
        size = len(record.text)
        if current and (len(current) >= max_cues or current_chars + size > max_chars):
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(record)
        current_chars += size
    if current:
        chunks.append(current)
    return chunks


def all_source_records(workdir: Path, manifest: dict[str, Any]) -> list[CueRecord]:
    records: list[CueRecord] = []
    for item in manifest["chunks"]:
        records.extend(read_records(workdir / "chunks" / "source" / item["name"]))
    return records


def parse_ranges(value: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for raw_part in re.split(r"[,\n]+", value):
        part = raw_part.strip()
        if not part or part.startswith("#"):
            continue
        match = re.match(r"^(\d+)\s*-\s*(\d+)(?:\s+.*)?$", part)
        if not match:
            fail("invalid_ranges", "Cue ranges must use START-END entries.")
        start = int(match.group(1))
        end = int(match.group(2))
        if end < start:
            fail("invalid_ranges", "A cue range ends before it starts.")
        ranges.append((start, end))
    if not ranges:
        fail("invalid_ranges", "No cue ranges were provided.")
    return ranges


def semantic_chunks_from_ranges(records: list[CueRecord], ranges: list[tuple[int, int]]) -> list[list[CueRecord]]:
    by_id = {record.cue_id: record for record in records}
    expected_next = records[0].cue_id if records else 1
    chunks: list[list[CueRecord]] = []
    for start, end in ranges:
        if start != expected_next:
            fail("invalid_ranges", "Cue ranges must be complete, ordered, and non-overlapping.")
        chunk: list[CueRecord] = []
        for cue_id in range(start, end + 1):
            record = by_id.get(cue_id)
            if record is None:
                fail("invalid_ranges", "A cue range references a missing cue ID.")
            chunk.append(record)
        chunks.append(chunk)
        expected_next = end + 1
    if records and expected_next != records[-1].cue_id + 1:
        fail("invalid_ranges", "Cue ranges do not cover every cue ID.")
    return chunks


def replace_manifest_chunks(workdir: Path, manifest: dict[str, Any], chunks: list[list[CueRecord]]) -> None:
    source_dir = workdir / "chunks" / "source"
    translated_dir = workdir / "chunks" / "translated"
    shutil.rmtree(source_dir, ignore_errors=True)
    shutil.rmtree(translated_dir, ignore_errors=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    translated_dir.mkdir(parents=True, exist_ok=True)

    chunk_metadata: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, 1):
        name = f"{index:04d}.jsonl"
        write_records(source_dir / name, chunk)
        chunk_metadata.append(
            {
                "name": name,
                "first_id": chunk[0].cue_id,
                "last_id": chunk[-1].cue_id,
                "cue_count": len(chunk),
            }
        )
    manifest["chunks"] = chunk_metadata
    manifest["chunk_count"] = len(chunks)
    manifest["chunking"] = "semantic_ranges"
    atomic_json_write(manifest_path(workdir), manifest)


def manifest_path(workdir: Path) -> Path:
    return workdir / "manifest.json"


def load_manifest(workdir: Path) -> dict[str, Any]:
    manifest = read_json(manifest_path(workdir))
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA_VERSION:
        fail("invalid_metadata", "The workspace manifest has an unsupported schema.")
    return manifest


def update_active_pointer(workdir: Path, session: dict[str, Any]) -> None:
    pointer = {
        "schema": SCHEMA_VERSION,
        "workdir": str(workdir.resolve()),
        "status": session.get("status", "extracted"),
        "guide": session.get("guide"),
        "output": session.get("output"),
        "output_format": session.get("output_format", "srt"),
    }
    atomic_json_write(workdir.parent / "active.json", pointer)


def write_session(workdir: Path, session: dict[str, Any]) -> None:
    atomic_json_write(workdir / "session.json", session)
    update_active_pointer(workdir, session)


def load_session(workdir: Path) -> dict[str, Any]:
    path = workdir / "session.json"
    if path.exists():
        session = read_json(path)
        if isinstance(session, dict):
            return session
    return {"schema": SCHEMA_VERSION, "status": "extracted", "output_format": "srt"}


def ensure_source_unchanged(manifest: dict[str, Any]) -> Path:
    source = Path(manifest["source"])
    if not source.is_file() or sha256_file(source) != manifest.get("source_sha256"):
        fail("source_changed", "The source file changed after extraction; re-extract before continuing.")
    return source


def expected_placeholders(text: str) -> list[str]:
    return [f"[[F{number}]]" for number in PLACEHOLDER_RE.findall(text)]


def normalize_for_comparison(text: str) -> str:
    text = PLACEHOLDER_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def likely_acronym_or_symbol(text: str) -> bool:
    clean = PLACEHOLDER_RE.sub("", text).strip()
    letters = "".join(ch for ch in clean if ch.isalpha())
    if not letters:
        return True
    return len(letters) <= 8 and letters.upper() == letters


def validate_pair(source: CueRecord, translated: CueRecord) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if source.cue_id != translated.cue_id:
        errors.append("id_mismatch")
    if not translated.text.strip():
        errors.append("empty_translation")

    source_tokens = expected_placeholders(source.text)
    translated_tokens = expected_placeholders(translated.text)
    if sorted(source_tokens) != sorted(translated_tokens):
        errors.append("markup_mismatch")
    for token in source_tokens:
        if translated.text.count(token) != source.text.count(token):
            errors.append("markup_count_mismatch")
            break

    source_normalized = normalize_for_comparison(source.text)
    translated_normalized = normalize_for_comparison(translated.text)
    source_words = WORD_RE.findall(source_normalized)
    if (
        source_normalized
        and source_normalized == translated_normalized
        and sum(len(word) for word in source_words) >= 4
        and not likely_acronym_or_symbol(source.text)
    ):
        warnings.append("unchanged")

    if (
        LATIN_RE.search(translated.text)
        and not ARABIC_RE.search(translated.text)
        and not likely_acronym_or_symbol(translated.text)
    ):
        warnings.append("no_arabic_script")
    return errors, warnings


def validate_chunk(source_path: Path, translated_path: Path) -> dict[str, Any]:
    source_records = read_records(source_path)
    translated_records = read_records(translated_path)
    if len(source_records) != len(translated_records):
        fail("cue_count_mismatch", "A translated chunk has the wrong number of cues.")

    bad_ids: list[int] = []
    warning_ids: list[int] = []
    warning_kinds: dict[str, list[int]] = {}
    for source, translated in zip(source_records, translated_records, strict=True):
        errors, warnings = validate_pair(source, translated)
        if errors:
            bad_ids.append(source.cue_id)
        for warning in warnings:
            warning_ids.append(source.cue_id)
            warning_kinds.setdefault(warning, []).append(source.cue_id)
    if bad_ids:
        fail(
            "translated_chunk_invalid",
            "A translated chunk failed ID, emptiness, or formatting validation.",
            ids=bad_ids,
        )
    return {
        "cues": len(source_records),
        "warning_ids": sorted(set(warning_ids)),
        "warnings": warning_kinds,
    }


def cmd_extract(args: argparse.Namespace) -> None:
    source = Path(args.source).expanduser().resolve()
    source_hash = sha256_file(source) if source.is_file() else ""
    if not source_hash:
        fail("source_missing", "The source subtitle file does not exist.")

    subs, encoding_used = load_subtitles(
        source,
        encoding=args.encoding,
        fps=args.fps,
        input_format=args.input_format,
    )
    events = translatable_events(subs)
    if not events:
        fail("no_text_cues", "No translatable text cues were found in the source file.")

    records = [CueRecord(cue_id, masked) for cue_id, _event, masked in events]
    chunks = split_chunks(records, args.chunk_cues, args.chunk_chars)

    if args.workdir:
        workdir = Path(args.workdir).expanduser().resolve()
    else:
        root = Path(args.work_root).expanduser().resolve()
        workdir = root / f"{slugify(source.stem)}-{source_hash[:8]}"

    if workdir.exists() and args.force:
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    source_dir = workdir / "chunks" / "source"
    translated_dir = workdir / "chunks" / "translated"
    source_dir.mkdir(parents=True, exist_ok=True)
    translated_dir.mkdir(parents=True, exist_ok=True)

    chunk_metadata: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, 1):
        name = f"{index:04d}.jsonl"
        write_records(source_dir / name, chunk)
        chunk_metadata.append(
            {
                "name": name,
                "first_id": chunk[0].cue_id,
                "last_id": chunk[-1].cue_id,
                "cue_count": len(chunk),
            }
        )

    manifest = {
        "schema": SCHEMA_VERSION,
        "source": str(source),
        "source_sha256": source_hash,
        "source_format": getattr(subs, "format", None) or args.input_format or source.suffix.lstrip("."),
        "source_encoding": encoding_used,
        "fps": args.fps,
        "cue_count": len(records),
        "chunk_count": len(chunks),
        "chunks": chunk_metadata,
        "intermediate_schema": {"i": "sequential cue ID", "t": "subtitle text without timestamps"},
    }
    atomic_json_write(manifest_path(workdir), manifest)
    session = {
        "schema": SCHEMA_VERSION,
        "status": "extracted",
        "guide": None,
        "output": None,
        "output_format": "srt",
    }
    write_session(workdir, session)

    emit(
        {
            "ok": True,
            "action": "extract",
            "workdir": str(workdir),
            "manifest": str(manifest_path(workdir)),
            "format": manifest["source_format"],
            "cues": len(records),
            "chunks": len(chunks),
            "timestamps_exposed": False,
        }
    )


def selected_chunks(manifest: dict[str, Any], requested: str | None) -> list[str]:
    names = [item["name"] for item in manifest["chunks"]]
    if requested is None:
        return names
    normalized = requested if requested.endswith(".jsonl") else f"{requested}.jsonl"
    if normalized not in names:
        fail("unknown_chunk", "The requested chunk does not exist.")
    return [normalized]


def cmd_check(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).expanduser().resolve()
    manifest = load_manifest(workdir)
    ensure_source_unchanged(manifest)
    names = selected_chunks(manifest, args.chunk)
    total_cues = 0
    warning_ids: list[int] = []
    warnings: dict[str, list[int]] = {}
    for name in names:
        result = validate_chunk(
            workdir / "chunks" / "source" / name,
            workdir / "chunks" / "translated" / name,
        )
        total_cues += result["cues"]
        warning_ids.extend(result["warning_ids"])
        for kind, ids in result["warnings"].items():
            warnings.setdefault(kind, []).extend(ids)

    emit(
        {
            "ok": True,
            "action": "check",
            "chunks": len(names),
            "cues": total_cues,
            "warning_ids": sorted(set(warning_ids)),
            "warnings": {key: sorted(set(value)) for key, value in warnings.items()},
            "timestamps_exposed": False,
        }
    )


def cmd_rechunk(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).expanduser().resolve()
    manifest = load_manifest(workdir)
    ensure_source_unchanged(manifest)
    translated_dir = workdir / "chunks" / "translated"
    if any(translated_dir.glob("*.jsonl")) and not args.force:
        fail("translated_chunks_exist", "Refusing to rechunk after translation started; pass --force to discard translated chunks.")
    range_text = args.ranges
    if args.ranges_file:
        try:
            range_text = Path(args.ranges_file).expanduser().read_text(encoding="utf-8")
        except OSError:
            fail("missing_ranges", "The requested cue ranges file cannot be read.")
    if not range_text:
        fail("invalid_ranges", "Cue ranges must be provided.")
    records = all_source_records(workdir, manifest)
    chunks = semantic_chunks_from_ranges(records, parse_ranges(range_text))
    replace_manifest_chunks(workdir, manifest, chunks)
    emit(
        {
            "ok": True,
            "action": "rechunk",
            "workdir": str(workdir),
            "chunks": len(chunks),
            "cues": len(records),
            "timestamps_exposed": False,
        }
    )


def cmd_export_compact(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).expanduser().resolve()
    manifest = load_manifest(workdir)
    ensure_source_unchanged(manifest)
    name = selected_chunks(manifest, args.chunk)[0]
    chunk_item = next(item for item in manifest["chunks"] if item["name"] == name)
    source_records = all_source_records(workdir, manifest)
    by_id = {record.cue_id: record for record in source_records}
    context = max(0, int(args.context_cues))
    before_start = max(1, int(chunk_item["first_id"]) - context)
    after_end = min(int(manifest["cue_count"]), int(chunk_item["last_id"]) + context)

    sections: list[tuple[str, list[CueRecord]]] = []
    if context:
        before = [by_id[cue_id] for cue_id in range(before_start, int(chunk_item["first_id"]))]
        if before:
            sections.append(("context_before", before))
    target = [by_id[cue_id] for cue_id in range(int(chunk_item["first_id"]), int(chunk_item["last_id"]) + 1)]
    sections.append(("translate", target))
    if context:
        after = [by_id[cue_id] for cue_id in range(int(chunk_item["last_id"]) + 1, after_end + 1)]
        if after:
            sections.append(("context_after", after))

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output.parent, delete=False, newline="\n"
    ) as handle:
        for section_name, records in sections:
            handle.write(f"# {section_name}\n")
            for record in records:
                handle.write(compact_text_record(record))
                handle.write("\n")
        temp_name = handle.name
    os.replace(temp_name, output)
    emit(
        {
            "ok": True,
            "action": "export-compact",
            "chunk": name,
            "output": str(output),
            "target_cues": int(chunk_item["cue_count"]),
            "context_cues": context,
            "timestamps_exposed": False,
        }
    )


def cmd_import_compact(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).expanduser().resolve()
    manifest = load_manifest(workdir)
    ensure_source_unchanged(manifest)
    name = selected_chunks(manifest, args.chunk)[0]
    source_path = workdir / "chunks" / "source" / name
    translated_path = workdir / "chunks" / "translated" / name
    source_records = read_records(source_path)
    translated_records = parse_compact_text(Path(args.input).expanduser().resolve())
    expected_ids = [record.cue_id for record in source_records]
    found_ids = [record.cue_id for record in translated_records]
    if found_ids != expected_ids:
        fail("id_sequence_mismatch", "The compact translation IDs do not exactly match the target chunk.")
    write_records(translated_path, translated_records)
    result = validate_chunk(source_path, translated_path)
    emit(
        {
            "ok": True,
            "action": "import-compact",
            "chunk": name,
            "cues": result["cues"],
            "warning_ids": result["warning_ids"],
            "warnings": result["warnings"],
            "timestamps_exposed": False,
        }
    )


def cmd_state(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).expanduser().resolve()
    load_manifest(workdir)
    if args.status not in SAFE_STATE_VALUES:
        fail("invalid_state", "The requested session state is invalid.")
    session = load_session(workdir)
    session.update(
        {
            "schema": SCHEMA_VERSION,
            "status": args.status,
            "guide": str(Path(args.guide).expanduser().resolve()) if args.guide else session.get("guide"),
            "output": str(Path(args.output).expanduser().resolve()) if args.output else session.get("output"),
            "output_format": args.output_format or session.get("output_format", "srt"),
        }
    )
    write_session(workdir, session)
    emit(
        {
            "ok": True,
            "action": "state",
            "workdir": str(workdir),
            "status": session["status"],
            "guide": session.get("guide"),
            "output": session.get("output"),
            "output_format": session.get("output_format"),
            "timestamps_exposed": False,
        }
    )


def cmd_active(args: argparse.Namespace) -> None:
    root = Path(args.work_root).expanduser().resolve()
    pointer = read_json(root / "active.json")
    if not isinstance(pointer, dict) or pointer.get("schema") != SCHEMA_VERSION:
        fail("no_active_session", "No active subtitle translation session was found.")
    emit({"ok": True, "action": "active", **pointer, "timestamps_exposed": False})


def unmask_translation(original_text: str, translated_text: str) -> str:
    _masked, tags = mask_markup(original_text)
    expected = [f"[[F{index}]]" for index in range(1, len(tags) + 1)]
    found = expected_placeholders(translated_text)
    if sorted(expected) != sorted(found):
        fail("markup_mismatch", "Formatting placeholders do not match the source cue.")
    rebuilt = translated_text
    for index, tag in enumerate(tags, 1):
        token = f"[[F{index}]]"
        if rebuilt.count(token) != 1:
            fail("markup_mismatch", "A formatting placeholder is missing or duplicated.")
        rebuilt = rebuilt.replace(token, tag)
    rebuilt = rebuilt.replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\N")
    return rebuilt


def all_translations(workdir: Path, manifest: dict[str, Any]) -> list[CueRecord]:
    combined: list[CueRecord] = []
    for item in manifest["chunks"]:
        name = item["name"]
        validate_chunk(
            workdir / "chunks" / "source" / name,
            workdir / "chunks" / "translated" / name,
        )
        combined.extend(read_records(workdir / "chunks" / "translated" / name))
    expected_ids = list(range(1, manifest["cue_count"] + 1))
    actual_ids = [record.cue_id for record in combined]
    if actual_ids != expected_ids:
        fail("id_sequence_mismatch", "The translated cue IDs are incomplete or out of order.")
    return combined


def output_format_value(requested: str, manifest: dict[str, Any]) -> str:
    if requested.lower() in {"source", "original", "same"}:
        return str(manifest["source_format"])
    return requested.lower()


def validate_built_output(
    output: Path,
    *,
    format_name: str,
    source_timing: list[tuple[int, int]],
    encoding: str,
    fps: float | None,
) -> None:
    kwargs: dict[str, Any] = {"encoding": encoding, "format_": format_name}
    if fps is not None:
        kwargs["fps"] = fps
    try:
        rebuilt = pysubs2.load(str(output), **kwargs)
    except Exception:
        fail("output_parse_failed", "The generated subtitle file could not be parsed.")
    visible = translatable_events(rebuilt)
    output_timing = [(int(event.start), int(event.end)) for _id, event, _text in visible]
    if len(output_timing) != len(source_timing):
        fail("output_cue_count_mismatch", "The generated file has the wrong number of visible cues.")
    if output_timing != source_timing:
        fail("output_timing_mismatch", "The generated file does not preserve source cue timing.")


def cmd_build(args: argparse.Namespace) -> None:
    workdir = Path(args.workdir).expanduser().resolve()
    manifest = load_manifest(workdir)
    source = ensure_source_unchanged(manifest)
    translations = all_translations(workdir, manifest)
    subs, _encoding = load_subtitles(
        source,
        encoding=manifest["source_encoding"],
        fps=manifest.get("fps"),
        input_format=manifest.get("source_format"),
    )
    events = translatable_events(subs)
    if len(events) != len(translations):
        fail("source_mapping_changed", "The source cue mapping no longer matches the extraction workspace.")

    source_timing: list[tuple[int, int]] = []
    for (cue_id, event, _masked), translated in zip(events, translations, strict=True):
        if cue_id != translated.cue_id:
            fail("id_sequence_mismatch", "The translated cue IDs are incomplete or out of order.")
        source_timing.append((int(event.start), int(event.end)))
        event.text = unmask_translation(event.text, translated.text)

    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    format_name = output_format_value(args.output_format, manifest)

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=output.parent, delete=False, suffix=f".{format_name}"
    ) as handle:
        temp_output = Path(handle.name)
    try:
        save_kwargs: dict[str, Any] = {"format_": format_name, "encoding": "utf-8"}
        if manifest.get("fps") is not None:
            save_kwargs["fps"] = manifest["fps"]
        subs.save(str(temp_output), **save_kwargs)
        validate_built_output(
            temp_output,
            format_name=format_name,
            source_timing=source_timing,
            encoding="utf-8",
            fps=manifest.get("fps"),
        )
        os.replace(temp_output, output)
    except PipelineError:
        temp_output.unlink(missing_ok=True)
        raise
    except Exception:
        temp_output.unlink(missing_ok=True)
        fail("output_write_failed", "The translated subtitle file could not be written.")

    # Collect warnings without exposing text or timestamps.
    warning_ids: list[int] = []
    warning_kinds: dict[str, list[int]] = {}
    for item in manifest["chunks"]:
        result = validate_chunk(
            workdir / "chunks" / "source" / item["name"],
            workdir / "chunks" / "translated" / item["name"],
        )
        warning_ids.extend(result["warning_ids"])
        for kind, ids in result["warnings"].items():
            warning_kinds.setdefault(kind, []).extend(ids)

    session = load_session(workdir)
    session.update(
        {
            "schema": SCHEMA_VERSION,
            "status": "complete",
            "output": str(output),
            "output_format": args.output_format,
        }
    )
    write_session(workdir, session)
    emit(
        {
            "ok": True,
            "action": "build",
            "output": str(output),
            "format": format_name,
            "cues": len(translations),
            "structure_valid": True,
            "timing_match": True,
            "warning_ids": sorted(set(warning_ids)),
            "warnings": {key: sorted(set(value)) for key, value in warning_kinds.items()},
            "timestamps_exposed": False,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract subtitle text without timestamps, validate translation chunks, and rebuild subtitles."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="Create timestamp-free translation chunks.")
    extract.add_argument("source")
    extract.add_argument("--work-root", default=".subtitle-work")
    extract.add_argument("--workdir")
    extract.add_argument("--encoding", default="auto")
    extract.add_argument("--input-format")
    extract.add_argument("--fps", type=float)
    extract.add_argument("--chunk-cues", type=int, default=DEFAULT_CHUNK_CUES)
    extract.add_argument("--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS)
    extract.add_argument("--force", action="store_true")
    extract.set_defaults(func=cmd_extract)

    check = subparsers.add_parser("check", help="Validate one or all translated chunks.")
    check.add_argument("workdir")
    check.add_argument("--chunk")
    check.set_defaults(func=cmd_check)

    rechunk = subparsers.add_parser("rechunk", help="Replace fixed chunks with model-chosen semantic cue ranges.")
    rechunk.add_argument("workdir")
    rechunk.add_argument("--ranges")
    rechunk.add_argument("--ranges-file")
    rechunk.add_argument("--force", action="store_true")
    rechunk.set_defaults(func=cmd_rechunk)

    export_compact = subparsers.add_parser(
        "export-compact", help="Write a timestamp-free compact text view for one chunk."
    )
    export_compact.add_argument("workdir")
    export_compact.add_argument("--chunk", required=True)
    export_compact.add_argument("--context-cues", type=int, default=0)
    export_compact.add_argument("--output", required=True)
    export_compact.set_defaults(func=cmd_export_compact)

    import_compact = subparsers.add_parser(
        "import-compact", help="Convert a compact translated chunk into validated JSONL."
    )
    import_compact.add_argument("workdir")
    import_compact.add_argument("--chunk", required=True)
    import_compact.add_argument("--input", required=True)
    import_compact.set_defaults(func=cmd_import_compact)

    state = subparsers.add_parser("state", help="Persist resumable workflow state.")
    state.add_argument("workdir")
    state.add_argument("--status", required=True, choices=sorted(SAFE_STATE_VALUES))
    state.add_argument("--guide")
    state.add_argument("--output")
    state.add_argument("--output-format")
    state.set_defaults(func=cmd_state)

    active = subparsers.add_parser("active", help="Return the active resumable session.")
    active.add_argument("--work-root", default=".subtitle-work")
    active.set_defaults(func=cmd_active)

    build = subparsers.add_parser("build", help="Reinsert translations and validate the output.")
    build.add_argument("workdir")
    build.add_argument("--output", required=True)
    build.add_argument("--output-format", default="srt")
    build.set_defaults(func=cmd_build)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
        return 0
    except PipelineError as exc:
        payload: dict[str, Any] = {
            "ok": False,
            "error": exc.code,
            "message": exc.message,
            "timestamps_exposed": False,
        }
        if exc.ids:
            payload["ids"] = exc.ids
        emit(payload, error=True)
        return 1
    except Exception:
        emit(
            {
                "ok": False,
                "error": "unexpected_failure",
                "message": "The subtitle pipeline failed without exposing source content.",
                "timestamps_exposed": False,
            },
            error=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

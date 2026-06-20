---
name: arabic-subtitle-translator
description: Translate text-based subtitle files such as SRT, WebVTT, ASS/SSA, TTML, and MicroDVD into natural Arabic, usually as SRT. Uses Python to keep all timestamps outside model context, creates translation guides, and resumes after guide approval.
---

# Objective

Translate complete subtitle files into natural, screen-ready contemporary Modern Standard Arabic. Treat each movie as a standalone work unless the user explicitly provides franchise guidance.

Use the bundled Python pipeline for every subtitle task. The model must work only with timestamp-free intermediate files; Python alone may parse or write timed subtitle formats.

# Interpret the user's intent

Choose one mode from the prompt:

1. **Full translation** — The user asks to translate a file. Generate the guide, immediately use it to translate the entire file, rebuild the requested format, and validate it. Do not stop for approval.
2. **Guide only** — The user asks to generate, prepare, or review the translation guide. Generate the guide and stop before translating. Save resumable state.
3. **Approval continuation** — A later message such as `Lgtm`, `LGTM`, `looks good`, `approved`, or an equivalent approval means: load the active saved session and complete the translation immediately. Do not regenerate the guide and do not ask for confirmation again.
4. **Guide feedback** — Apply the feedback consistently to the guide and keep the session in `awaiting_approval` state. Translate only after approval unless the feedback message also explicitly says to continue.

For guide-only workflows, approval continuation is expected to occur in the same Codex thread and project directory.

# Timestamp isolation: mandatory

Never place source or output timestamps in model context.

- Never open, preview, read, search, print, or edit the original subtitle file directly.
- Never open or preview the rebuilt timed subtitle file.
- Do not use `cat`, `head`, `tail`, `sed`, `awk`, `grep`, `rg`, an editor, or a model-facing file reader on either timed file.
- Do not ask another agent or tool to summarize a timed subtitle file directly.
- Do not redirect raw subtitle content to terminal output or chat.
- Only the bundled Python script may read the original file and final timed output.
- Read and edit only the generated JSONL chunks. Each record contains a sequential cue ID `i` and timestamp-free subtitle text `t`.
- The script's stdout is deliberately limited to paths, counts, IDs, statuses, and validation results. It must remain free of subtitle text and timestamp values.
- Validation and timing comparison must be performed by the script, never by visually inspecting the timed output.

Dialogue that itself mentions a clock time is ordinary translatable text; the restriction concerns structural subtitle timestamps.

# Set up the pipeline

Resolve `SKILL_DIR` as the directory containing this `SKILL.md`, then set:

```bash
PIPELINE="$SKILL_DIR/scripts/subtitle_pipeline.py"
```

Before first use, ensure dependencies are available:

```bash
python -c "import pysubs2, charset_normalizer" 2>/dev/null || \
  python -m pip install -r "$SKILL_DIR/requirements.txt"
```

Do not read the source while locating it. Use the path supplied by the user or the attached file's path. If several subtitle files are present, prefer the one explicitly referenced or attached to the current message.

Target format rules:

- Explicit `to SRT` or `as SRT`: use `srt`.
- Explicit request to retain the format: use `source`.
- Another explicitly named supported text subtitle format: use that format identifier.
- No target specified: default to `srt`.

Default output names:

- Guide: `<source-stem>.ar-guide.md`
- Translation: `<source-stem>.ar.<target-extension>`

Never overwrite the source.

# Extract timestamp-free chunks

For a new task, run:

```bash
python "$PIPELINE" extract "$SOURCE" \
  --work-root .subtitle-work \
  --chunk-cues 100 \
  --chunk-chars 12000 \
  --force
```

Capture the returned `workdir`. Do not open the source file. Safe files inside the workspace are:

- `manifest.json` — format, file hash, cue counts, and chunk list; no timestamps
- `chunks/source/*.jsonl` — model-readable source text with cue separation and no timestamps
- `chunks/translated/*.jsonl` — Arabic translation chunks
- `session.json` — resumable workflow state

Each JSONL line has exactly this schema:

```json
{"i":1,"t":"Subtitle text only"}
```

`[[F1]]`, `[[F2]]`, and similar tokens represent protected formatting. Preserve every such token exactly once. They may be moved with the phrase they format, but must not be translated, altered, added, or deleted.

If extraction reports that a format is unsupported, bitmap-based, or requires FPS, do not inspect the raw file. Report the blocking format requirement concisely. Bitmap subtitle formats and OCR are outside this skill.

# Generate the translation guide

Read the timestamp-free source chunks in order. For long files, process them sequentially and maintain compact rolling notes rather than loading or restating the whole transcript at once.

Write a concise guide containing:

- Plot and dramatic progression
- Setting, period, genre, and tone
- Main characters, relationships, and speaking styles
- Names, titles, places, recurring terminology, and proposed Arabic forms
- Formality, humor, sarcasm, profanity, songs, and sound-description policy
- Running jokes, catchphrases, and context-sensitive wording
- Important ambiguities and chosen resolutions

Infer only from timestamp-free subtitle text, the filename, and user-provided local references. Do not browse for the movie or franchise unless the user explicitly requests research. Do not invent details that the subtitles do not establish.

Keep the guide compact and operational. Prefer a glossary and explicit decisions over long commentary.

## Full-translation mode

After creating the guide, continue directly. Record state before translating:

```bash
python "$PIPELINE" state "$WORKDIR" \
  --status translating \
  --guide "$GUIDE" \
  --output "$OUTPUT" \
  --output-format "$TARGET_FORMAT"
```

Do not return to the user between guide creation and translation.

## Guide-only mode

Do not create translated chunks. Record resumable state:

```bash
python "$PIPELINE" state "$WORKDIR" \
  --status awaiting_approval \
  --guide "$GUIDE" \
  --output "$OUTPUT" \
  --output-format "$TARGET_FORMAT"
```

Report the guide path and a concise summary of the key decisions. End by asking only for `Lgtm` or corrections.

## Resume after `Lgtm`

Locate the session without re-extracting:

```bash
python "$PIPELINE" active --work-root .subtitle-work
```

Use the returned workspace, guide, output path, and output format. Confirm internally that the state is `awaiting_approval`, change it to `translating`, and complete the workflow. Do not ask another question.

# Arabic translation policy

- Use natural contemporary Modern Standard Arabic suitable for professional movie subtitles.
- Translate meaning, intent, tone, humor, emotion, and subtext rather than source-language syntax.
- Do not omit, summarize, censor, or deliberately shorten meaning. Natural Arabic grammatical compression is acceptable when it preserves the complete intent.
- Preserve character voice, social status, politeness, hostility, hesitation, irony, and emotional force.
- Match the source's profanity level unless the approved guide says otherwise.
- Use dialect only when explicitly justified by the guide.
- Keep names, genders, pronouns, relationships, titles, and recurring terminology consistent.
- Prefer established Arabic forms of familiar names and places; otherwise choose one clear transliteration and use it consistently.
- Translate meaningful captions, signs, sound descriptions, and lyrics unless the guide specifies a reason not to.
- Use Arabic punctuation such as `؟` and `،` where natural.
- Avoid unnecessary diacritics and overly classical phrasing.
- Do not add explanations, translator notes, or information absent from the source.

# Translate the chunks

Process chunks in manifest order. For each source chunk:

1. Read only `chunks/source/<name>.jsonl` and the approved guide.
2. Write `chunks/translated/<name>.jsonl` with the same number of records, the same IDs, and exactly the keys `i` and `t`.
3. Change only `t` to Arabic. Preserve protected formatting tokens exactly.
4. Preserve speaker separation and meaningful line breaks; adjust wrapping only for readable Arabic.
5. Run validation immediately:

```bash
python "$PIPELINE" check "$WORKDIR" --chunk "<chunk-number>"
```

6. Fix every validation error before continuing.
7. Inspect warning IDs using only the timestamp-free source and translated chunks. Fix genuinely untranslated cues. Acronyms, proper names, symbols, and intentional foreign words may remain when justified by the guide.

At chunk boundaries, consult only a few neighboring timestamp-free cues when continuity requires it. Do not reread completed chunks wholesale. Update the compact glossary or guide only when a new recurring decision appears.

Never paste chunk contents into chat, and never provide progress messages containing dialogue.

After all chunks, run the full check:

```bash
python "$PIPELINE" check "$WORKDIR"
```

Resolve all structural errors and review remaining warnings before rebuilding.

# Rebuild and validate

Create the final timed subtitle entirely through Python:

```bash
python "$PIPELINE" build "$WORKDIR" \
  --output "$OUTPUT" \
  --output-format "$TARGET_FORMAT"
```

The build command reloads the untouched source internally, reinserts Arabic by sequential cue ID, restores protected formatting, writes the requested format, reparses it, and verifies cue count, cue order, and source timing. It exposes no timestamp values or subtitle text.

Do not open the output after building. If validation fails, correct the timestamp-free translated chunks and rerun the script.

The task is complete only when:

- Every source text cue has one nonempty Arabic counterpart
- Chunk IDs are complete, unique, and ordered
- Formatting placeholders validate
- The final file parses successfully
- Cue count and timing match the parsed source
- The requested output exists and the source remains unchanged

# Completion responses

For a guide-only request, report only:

- Guide path
- Brief summary of major choices
- `Reply Lgtm to continue, or send corrections.`

For a completed translation, report only:

- Output path
- Guide path
- Number of translated cues
- Output format
- Structural and timing validation result
- Any intentionally retained warning IDs, with a brief reason and no subtitle text

Never include the complete translation, raw subtitle content, or timestamps in the response.

---
name: arabic-subtitle-translator
description: Analyze, translate, revise, and validate SRT subtitle files into natural contemporary Arabic while preserving cue numbers and timestamps. Use for complete Arabic subtitle translation, terminology planning, or subtitle revision.
---

# Objective

Translate complete `.srt` subtitle files into natural, screen-ready Modern Standard Arabic.

Translate meaning, intent, tone, humor, and subtext rather than source-language syntax. Translate every nonempty cue; never omit, summarize, or skip dialogue.

Treat each movie as a standalone work. Do not research prequels, sequels, or franchise terminology unless the user explicitly requests it.

# Inputs and outputs

Inputs:

- One source `.srt` file
- Optional user notes or corrections
- Optional approved translation guide

Default outputs:

- Analysis guide: `<source-stem>.ar-guide.md`
- Arabic subtitles: `<source-stem>.ar.srt`

Never overwrite the source file.

# Modes

## Analyze mode

Use this mode before translation unless the user explicitly says that the guidance is already approved.

1. Read the complete subtitle file in sequence.
2. Infer context from the subtitles, filename, and other relevant local files.
3. Do not invent plot details that the available material does not establish.
4. Create `<source-stem>.ar-guide.md` containing:
   - A concise plot summary
   - Setting, period, genre, and overall tone
   - Main characters, relationships, and speaking styles
   - Recurring names, titles, places, technical terms, jokes, and catchphrases
   - Proposed Arabic equivalents and transliterations
   - Guidance for formality, humor, profanity, songs, and sound descriptions
   - Important ambiguities or decisions that may need user feedback
5. Keep the guide concise. Prefer a short glossary over lengthy explanations.
6. Show the user a compact summary of the proposed guidance.
7. Do not translate subtitle cues in this mode.
8. Stop and wait for approval or corrections.

## Translate mode

Begin only when the prompt explicitly requests translation or says the guide is approved.

1. Read the approved guide and the latest user feedback.
2. Translate the entire file from the first cue through the last cue.
3. Do not ask routine questions once translation has started.
4. Resolve nonblocking ambiguities using context and record important choices in the guide.
5. Continue until the complete output file has been created and validated.

## Revise mode

Apply the user's corrections consistently across the whole translated file, not only to the cited examples. Re-run all validation afterward.

# Arabic translation style

- Use natural contemporary Modern Standard Arabic suitable for movie subtitles.
- Avoid literal, awkward, overly formal, or classical phrasing.
- Natural Arabic may be shorter than the source, but no meaning may be omitted or compressed away.
- Preserve character voice, emotional intensity, social status, sarcasm, jokes, threats, hesitation, and subtext.
- Match the source's level of profanity; do not automatically sanitize it.
- Use dialect only when the approved guide explicitly calls for it.
- Keep names, titles, pronouns, genders, relationships, and recurring terminology consistent.
- Prefer established Arabic forms of well-known names and places. Otherwise, use one clear transliteration consistently.
- Translate meaningful sound descriptions, signs, captions, and song lyrics unless the guide says otherwise.
- Use Arabic punctuation where appropriate, including `؟` and `،`.
- Avoid unnecessary diacritics.
- Do not add explanations, translator notes, or information absent from the source.

# SRT requirements

Preserve exactly:

- Cue numbers and their order
- Start and end timestamps
- Cue boundaries
- Formatting tags such as `<i>`, `<b>`, and `<u>`
- Music symbols, positioning codes, and other valid subtitle markup

Line breaks may be adjusted for readable Arabic.

Where practical:

- Use no more than two displayed lines per cue.
- Keep connected phrases together.
- Preserve separate-speaker formatting.
- Avoid leaving a preposition, conjunction, or article alone at the end of a line.

# Token-efficient workflow

1. Never paste the complete source or translated SRT into the conversation.
2. Write the translation directly to the output file.
3. Treat the source SRT as an immutable structural template.
4. Process cues in contiguous chunks.
5. For translation work, use a compact representation containing only cue identifiers and subtitle text. Do not repeatedly include timestamps.
6. Inspect surrounding cues only when context is needed; do not repeatedly reread the whole file.
7. Maintain one compact working state containing:
   - Character names and voices
   - Approved glossary
   - Recurring terminology
   - Last completed cue
   - Unresolved ambiguities
8. Update that state in place instead of appending a long progress log.
9. Do not repeat the plot summary, glossary, completed chunks, or earlier decisions in progress messages.
10. Give only brief checkpoint reports during long translations.
11. Remove temporary chunk files after successful validation.
12. Do not place the final subtitles in an `srt` code block unless the user explicitly asks to receive the contents in chat.

Use a small deterministic script for parsing, merging, and validation when useful. Scripts must not perform translation; they should only handle SRT structure.

# Validation

Before declaring completion, programmatically verify that:

- The output is valid UTF-8.
- The output parses as SRT.
- Source and output contain the same number of cues.
- Every cue number matches the corresponding source cue.
- Every timestamp line matches the source exactly.
- Every nonempty source cue has a nonempty translated cue.
- No cue is duplicated, omitted, or reordered.
- Formatting tags remain balanced.
- No large block of source-language dialogue was accidentally left untranslated.

Manually inspect the first cues, last cues, chunk boundaries, multiline dialogue, recurring terminology, and any automatically flagged untranslated text.

Fix all validation failures before finishing.

# Completion response

After analysis, report:

- Guide file path
- Concise translation approach
- Decisions requiring feedback

After translation, report only:

- Output file path
- Number of translated cues
- Validation result
- Any notable nonblocking interpretation choices

Do not include the complete subtitle text in the response.

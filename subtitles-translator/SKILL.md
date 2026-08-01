---
name: subtitles-translator
description: Translate SubRip subtitle (.srt) files from any source language to a requested target language while preserving cue numbers, timestamps, line structure, markup, and encoding compatibility. Use when Codex needs to translate subtitles, localize an SRT, create a translated subtitle copy, overwrite an SRT in place, or validate subtitle structure before or after translation.
---

# Subtitles Translator

Translate SRT dialogue with the bundled `scripts/translate_srt.js` and preserve subtitle structure deterministically.

## Workflow

1. Resolve the exact input path and confirm that it is an `.srt` file.
2. Determine the target language. Use source language `auto` unless the user specifies it.
3. Decide output behavior:
   - Default to a sibling `<name>.<target-code>.srt` file.
   - Use `--in-place` only when the user explicitly requests replacement.
   - In in-place mode, keep the default backup unless the user explicitly declines it; then pass `--no-backup`.
4. Explain that the bundled provider uploads dialogue text to Google Translate. Obtain explicit consent before passing `--allow-third-party-upload`. Do not infer upload consent merely from a request to translate.
5. Run the translator. Request network or out-of-workspace filesystem approval when required.
6. Verify the reported cue, ID, timestamp, and markup checks before reporting completion.
7. State that the result is machine-translated when translation quality matters; offer focused human review for names, idioms, songs, and fantasy or technical terms.

## Commands

Use Node.js 18 or newer. Quote paths containing spaces.

Create a translated copy:

```powershell
node scripts/translate_srt.js --input "C:\path\episode.srt" --target Arabic --allow-third-party-upload
```

Choose a source and output path:

```powershell
node scripts/translate_srt.js --input "C:\path\episode.srt" --source French --target Japanese --output "C:\path\episode.ja.srt" --allow-third-party-upload
```

Replace the source while retaining a backup:

```powershell
node scripts/translate_srt.js --input "C:\path\episode.srt" --target Spanish --in-place --allow-third-party-upload
```

Replace the source without a backup only after explicit user instruction:

```powershell
node scripts/translate_srt.js --input "C:\path\episode.srt" --target Spanish --in-place --no-backup --allow-third-party-upload
```

Validate structure without translating or using the network:

```powershell
node scripts/translate_srt.js --input "C:\path\episode.srt" --validate-only
```

Use `--overwrite` to replace an existing separate output file. Use `--concurrency N` to tune request concurrency; the default is 6.

## Guardrails

- Preserve cue identifiers and timing lines byte-for-byte in logical content.
- Preserve HTML-like tags and ASS override tags exactly; never send them to the provider.
- Preserve dialogue dashes and subtitle line boundaries.
- Decode UTF-8, UTF-16 LE/BE, and Windows-1252 input; emit UTF-8 with BOM for broad player compatibility.
- Never overwrite an unrelated path. Resolve and compare source and destination paths first.
- Stop on malformed SRT blocks, translation failures, or structural validation failures.
- Treat the Google endpoint as a network dependency that may rate-limit or change. Retry transient failures, but report persistent failures rather than producing partial output.


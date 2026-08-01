#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const LANGUAGE_CODES = {
  afrikaans: 'af', arabic: 'ar', bengali: 'bn', bulgarian: 'bg', catalan: 'ca',
  chinese: 'zh-CN', 'chinese simplified': 'zh-CN', 'simplified chinese': 'zh-CN',
  'chinese traditional': 'zh-TW', 'traditional chinese': 'zh-TW', croatian: 'hr',
  czech: 'cs', danish: 'da', dutch: 'nl', english: 'en', estonian: 'et', finnish: 'fi',
  french: 'fr', german: 'de', greek: 'el', gujarati: 'gu', hebrew: 'he', hindi: 'hi',
  hungarian: 'hu', icelandic: 'is', indonesian: 'id', irish: 'ga', italian: 'it',
  japanese: 'ja', kannada: 'kn', korean: 'ko', latvian: 'lv', lithuanian: 'lt',
  malay: 'ms', malayalam: 'ml', marathi: 'mr', norwegian: 'no', persian: 'fa',
  farsi: 'fa', polish: 'pl', portuguese: 'pt', punjabi: 'pa', romanian: 'ro',
  russian: 'ru', serbian: 'sr', slovak: 'sk', slovenian: 'sl', spanish: 'es',
  swahili: 'sw', swedish: 'sv', tamil: 'ta', telugu: 'te', thai: 'th', turkish: 'tr',
  ukrainian: 'uk', urdu: 'ur', vietnamese: 'vi', welsh: 'cy', auto: 'auto'
};

function usage() {
  console.log(`Usage:
  node translate_srt.js --input <file.srt> --target <language> [options]
  node translate_srt.js --input <file.srt> --validate-only

Options:
  --source <language>              Source language name/code (default: auto)
  --target <language>              Target language name/code
  --output <file.srt>              Output path (default: sibling name.<code>.srt)
  --in-place                       Replace the input file
  --backup                         Back up in-place input (default)
  --no-backup                      Do not back up in-place input
  --overwrite                      Replace an existing separate output
  --allow-third-party-upload       Confirm dialogue upload to Google Translate
  --concurrency <1-16>             Parallel requests (default: 6)
  --validate-only                  Parse and validate without translation
  --help                           Show this help`);
}

function parseArgs(argv) {
  const args = { source: 'auto', concurrency: 6, backup: true };
  const valueOptions = new Set(['--input', '--source', '--target', '--output', '--concurrency']);
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (valueOptions.has(arg)) {
      if (i + 1 >= argv.length) throw new Error(`${arg} requires a value`);
      args[arg.slice(2).replaceAll('-', '_')] = argv[++i];
    } else if (arg === '--in-place') args.in_place = true;
    else if (arg === '--backup') args.backup = true;
    else if (arg === '--no-backup') args.backup = false;
    else if (arg === '--overwrite') args.overwrite = true;
    else if (arg === '--allow-third-party-upload') args.allow_upload = true;
    else if (arg === '--validate-only') args.validate_only = true;
    else if (arg === '--help' || arg === '-h') args.help = true;
    else throw new Error(`Unknown option: ${arg}`);
  }
  args.concurrency = Number(args.concurrency);
  if (!Number.isInteger(args.concurrency) || args.concurrency < 1 || args.concurrency > 16) {
    throw new Error('--concurrency must be an integer from 1 to 16');
  }
  return args;
}

function normalizeLanguage(value, optionName) {
  if (!value) throw new Error(`${optionName} is required`);
  const normalized = value.trim().toLowerCase().replaceAll('_', '-');
  if (LANGUAGE_CODES[normalized]) return LANGUAGE_CODES[normalized];
  if (/^[a-z]{2,3}(?:-[a-z]{2,4})?$/i.test(normalized)) return normalized;
  throw new Error(`Unknown language '${value}'. Use a common English language name or ISO/BCP-47 code.`);
}

function decodeSubtitle(buffer) {
  if (buffer.length >= 3 && buffer[0] === 0xef && buffer[1] === 0xbb && buffer[2] === 0xbf) {
    return new TextDecoder('utf-8').decode(buffer.subarray(3));
  }
  if (buffer.length >= 2 && buffer[0] === 0xff && buffer[1] === 0xfe) {
    return new TextDecoder('utf-16le').decode(buffer.subarray(2));
  }
  if (buffer.length >= 2 && buffer[0] === 0xfe && buffer[1] === 0xff) {
    const swapped = Buffer.alloc(buffer.length - 2);
    for (let i = 2; i + 1 < buffer.length; i += 2) {
      swapped[i - 2] = buffer[i + 1];
      swapped[i - 1] = buffer[i];
    }
    return new TextDecoder('utf-16le').decode(swapped);
  }
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  } catch {
    return new TextDecoder('windows-1252').decode(buffer);
  }
}

function parseSrt(text) {
  const normalized = text.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const blocks = normalized.trimEnd().split(/\n{2,}/);
  if (blocks.length === 1 && blocks[0].trim() === '') throw new Error('The SRT file is empty');
  return blocks.map((block, index) => {
    const lines = block.split('\n');
    if (lines.length < 3) throw new Error(`Malformed SRT block ${index + 1}: expected ID, timing, and text`);
    if (!/^\d+$/.test(lines[0].trim())) throw new Error(`Malformed cue ID in block ${index + 1}`);
    if (!/^\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}(?:\s+.*)?$/.test(lines[1])) {
      throw new Error(`Malformed timing line in block ${index + 1}: ${lines[1]}`);
    }
    return { id: lines[0], timing: lines[1], lines: lines.slice(2) };
  });
}

const TAG_PATTERN = /(<[^>\r\n]+>|\{\\[^}\r\n]+\})/g;

function markupSequence(lines) {
  return lines.flatMap(line => line.match(TAG_PATTERN) || []);
}

function sameArray(a, b) {
  return a.length === b.length && a.every((value, i) => value === b[i]);
}

function validateTranslation(source, output) {
  if (source.length !== output.length) throw new Error(`Cue count changed: ${source.length} -> ${output.length}`);
  for (let i = 0; i < source.length; i++) {
    if (source[i].id !== output[i].id) throw new Error(`Cue ID changed in block ${i + 1}`);
    if (source[i].timing !== output[i].timing) throw new Error(`Timestamp changed in cue ${source[i].id}`);
    if (source[i].lines.length !== output[i].lines.length) throw new Error(`Line count changed in cue ${source[i].id}`);
    if (!sameArray(markupSequence(source[i].lines), markupSequence(output[i].lines))) {
      throw new Error(`Markup changed in cue ${source[i].id}`);
    }
  }
}

function serializeSrt(cues, newline) {
  return cues.map(cue => [cue.id, cue.timing, ...cue.lines].join(newline)).join(newline + newline) + newline;
}

function splitProtected(line) {
  const parts = [];
  let last = 0;
  for (const match of line.matchAll(TAG_PATTERN)) {
    if (match.index > last) parts.push({ protected: false, value: line.slice(last, match.index) });
    parts.push({ protected: true, value: match[0] });
    last = match.index + match[0].length;
  }
  if (last < line.length) parts.push({ protected: false, value: line.slice(last) });
  return parts;
}

function prepareText(text) {
  const match = text.match(/^(\s*)([-–—]\s*)?([\s\S]*?)(\s*)$/);
  return { prefix: match[1] + (match[2] || ''), body: match[3], suffix: match[4] };
}

function shouldTranslate(text) {
  return /[\p{L}\p{N}]/u.test(text);
}

async function googleTranslate(text, source, target, attempt = 1) {
  const url = new URL('https://translate.googleapis.com/translate_a/single');
  url.searchParams.set('client', 'gtx');
  url.searchParams.set('sl', source);
  url.searchParams.set('tl', target);
  url.searchParams.set('dt', 't');
  url.searchParams.set('q', text);
  try {
    const response = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' } });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data?.[0])) throw new Error('Unexpected translation response');
    return data[0].map(part => part[0] || '').join('');
  } catch (error) {
    if (attempt >= 5) throw new Error(`Translation failed after ${attempt} attempts: ${error.message}`);
    await new Promise(resolve => setTimeout(resolve, 400 * (2 ** attempt)));
    return googleTranslate(text, source, target, attempt + 1);
  }
}

async function translateLine(line, source, target, cache) {
  const parts = splitProtected(line);
  for (const part of parts) {
    if (part.protected) continue;
    const prepared = prepareText(part.value);
    if (!shouldTranslate(prepared.body)) continue;
    const key = `${source}\u0000${target}\u0000${prepared.body}`;
    if (!cache.has(key)) cache.set(key, googleTranslate(prepared.body, source, target));
    part.value = prepared.prefix + await cache.get(key) + prepared.suffix;
  }
  return parts.map(part => part.value).join('');
}

async function translateCues(cues, source, target, concurrency) {
  const output = new Array(cues.length);
  const cache = new Map();
  let cursor = 0;
  let completed = 0;
  async function worker() {
    while (true) {
      const i = cursor++;
      if (i >= cues.length) return;
      const translatedLines = [];
      for (const line of cues[i].lines) translatedLines.push(await translateLine(line, source, target, cache));
      output[i] = { id: cues[i].id, timing: cues[i].timing, lines: translatedLines };
      completed++;
      if (completed % 50 === 0 || completed === cues.length) console.log(`Translated ${completed}/${cues.length} cues`);
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, cues.length) }, worker));
  return output;
}

function nextBackupPath(inputPath) {
  const basic = inputPath + '.bak';
  if (!fs.existsSync(basic)) return basic;
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  return `${basic}.${stamp}`;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) return usage();
  if (!args.input) throw new Error('--input is required');
  const inputPath = path.resolve(args.input);
  if (path.extname(inputPath).toLowerCase() !== '.srt') throw new Error('Input must have an .srt extension');
  if (!fs.existsSync(inputPath)) throw new Error(`Input not found: ${inputPath}`);

  const raw = fs.readFileSync(inputPath);
  const decoded = decodeSubtitle(raw);
  const newline = decoded.includes('\r\n') ? '\r\n' : '\n';
  const cues = parseSrt(decoded);
  console.log(`Validated ${cues.length} SRT cues`);
  if (args.validate_only) return;

  const source = normalizeLanguage(args.source, '--source');
  const target = normalizeLanguage(args.target, '--target');
  if (target === 'auto') throw new Error('--target cannot be auto');
  if (!args.allow_upload) {
    throw new Error('Translation uploads dialogue to Google Translate. Obtain explicit user consent, then pass --allow-third-party-upload.');
  }
  if (args.in_place && args.output) throw new Error('Use either --in-place or --output, not both');

  let outputPath;
  if (args.in_place) outputPath = inputPath;
  else if (args.output) outputPath = path.resolve(args.output);
  else {
    const parsedPath = path.parse(inputPath);
    outputPath = path.join(parsedPath.dir, `${parsedPath.name}.${target}.srt`);
  }
  if (path.extname(outputPath).toLowerCase() !== '.srt') throw new Error('Output must have an .srt extension');
  if (!args.in_place && path.resolve(outputPath).toLowerCase() === inputPath.toLowerCase()) {
    throw new Error('Output resolves to the input; use --in-place explicitly');
  }
  if (!args.in_place && fs.existsSync(outputPath) && !args.overwrite) {
    throw new Error(`Output exists: ${outputPath}. Pass --overwrite to replace it.`);
  }

  const translated = await translateCues(cues, source, target, args.concurrency);
  validateTranslation(cues, translated);
  const reparsed = parseSrt(serializeSrt(translated, newline));
  validateTranslation(cues, reparsed);

  let backupPath = null;
  if (args.in_place && args.backup) {
    backupPath = nextBackupPath(inputPath);
    fs.copyFileSync(inputPath, backupPath, fs.constants.COPYFILE_EXCL);
  }
  fs.writeFileSync(outputPath, '\uFEFF' + serializeSrt(translated, newline), 'utf8');
  console.log(`Wrote: ${outputPath}`);
  if (backupPath) console.log(`Backup: ${backupPath}`);
  console.log(`Verified: ${cues.length} cues; IDs, timestamps, line counts, and markup preserved`);
}

main().catch(error => {
  console.error(`Error: ${error.message}`);
  process.exitCode = 1;
});


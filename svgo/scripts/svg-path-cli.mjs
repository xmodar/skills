#!/usr/bin/env node
import { readFile, writeFile } from 'node:fs/promises';
import { SvgPath, optimizePath, reversePath, changePathOrigin } from 'svg-path-editor-lib';
import { optimize as optimizeSvg, loadConfig, builtinPlugins } from 'svgo';

const usage = `Usage:
  svg-path-cli --path "<svg path d>" [--op <operation> ...] [--decimals N] [--minify]
  svg-path-cli --input input.svg [--output output.svg] [--select all|N|N,N] [--op <operation> ...]
  svg-path-cli --input input.svg --svgo [SVGO options]

Path operations are applied in order:
  translate:dx,dy
  scale:kx,ky
  rotate:ox,oy,degrees
  relative
  absolute
  reverse or reverse:itemIndex
  origin:itemIndex or origin:itemIndex:subpath
  optimize:safe | optimize:size | optimize:closed | optimize:all
  optimize:remove-useless,use-shorthands,use-hv,use-relative-absolute,use-reverse,use-close-path,remove-orphan-dots

Path formatting:
  --decimals N   Number of decimal places for path output, default 4
  --minify       Remove optional path spaces and leading zeroes

SVGO:
  --svgo                         Run SVGO with preset-default
  --svgo-order before|after      Run SVGO before or after path operations, default after
  --svgo-config FILE             Load svgo.config.js, .mjs, or .cjs
  --svgo-preset default|none     Use preset-default or no preset with explicit plugins
  --svgo-plugin NAME[:JSON]      Add a built-in plugin, optionally with JSON params
  --svgo-disable NAME            Disable a preset-default plugin via overrides
  --svgo-precision N             Set global SVGO floatPrecision
  --svgo-multipass               Run repeated SVGO passes while output shrinks
  --svgo-pretty                  Pretty-print SVG output
  --svgo-indent N                Indent width when pretty-printing
  --svgo-eol lf|crlf             Output line ending
  --svgo-final-newline           End SVG output with a newline
  --svgo-datauri base64|enc|unenc
  --svgo-list-plugins            Print available SVGO plugins
`;

const optionAliases = new Map([
  ['remove-useless', 'removeUselessCommands'],
  ['remove-useless-commands', 'removeUselessCommands'],
  ['removeUselessCommands', 'removeUselessCommands'],
  ['use-shorthands', 'useShorthands'],
  ['useShorthands', 'useShorthands'],
  ['use-hv', 'useHorizontalAndVerticalLines'],
  ['use-horizontal-vertical', 'useHorizontalAndVerticalLines'],
  ['use-horizontal-and-vertical-lines', 'useHorizontalAndVerticalLines'],
  ['useHorizontalAndVerticalLines', 'useHorizontalAndVerticalLines'],
  ['use-relative-absolute', 'useRelativeAbsolute'],
  ['useRelativeAbsolute', 'useRelativeAbsolute'],
  ['use-reverse', 'useReverse'],
  ['useReverse', 'useReverse'],
  ['use-close-path', 'useClosePath'],
  ['useClosePath', 'useClosePath'],
  ['remove-orphan-dots', 'removeOrphanDots'],
  ['removeOrphanDots', 'removeOrphanDots']
]);

function parseArgs(argv) {
  const args = {
    ops: [],
    decimals: 4,
    minify: false,
    select: 'all',
    svgo: false,
    svgoOrder: 'after',
    svgoPlugins: [],
    svgoDisabled: []
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--help' || arg === '-h') {
      args.help = true;
    } else if (arg === '--path') {
      args.path = readValue(argv, ++i, arg);
    } else if (arg === '--input' || arg === '-i') {
      args.input = readValue(argv, ++i, arg);
    } else if (arg === '--output' || arg === '-o') {
      args.output = readValue(argv, ++i, arg);
    } else if (arg === '--op') {
      args.ops.push(readValue(argv, ++i, arg));
    } else if (arg === '--decimals') {
      args.decimals = parseInteger(readValue(argv, ++i, arg), 'decimals');
    } else if (arg === '--minify') {
      args.minify = true;
    } else if (arg === '--select') {
      args.select = readValue(argv, ++i, arg);
    } else if (arg === '--svgo') {
      args.svgo = true;
    } else if (arg === '--svgo-order') {
      args.svgo = true;
      args.svgoOrder = readValue(argv, ++i, arg);
      if (args.svgoOrder !== 'before' && args.svgoOrder !== 'after') {
        fail('--svgo-order must be before or after');
      }
    } else if (arg === '--svgo-config') {
      args.svgo = true;
      args.svgoConfig = readValue(argv, ++i, arg);
    } else if (arg === '--svgo-preset') {
      args.svgo = true;
      args.svgoPreset = readValue(argv, ++i, arg);
      if (args.svgoPreset !== 'default' && args.svgoPreset !== 'none') {
        fail('--svgo-preset must be default or none');
      }
    } else if (arg === '--svgo-plugin') {
      args.svgo = true;
      args.svgoPlugins.push(readValue(argv, ++i, arg));
    } else if (arg === '--svgo-disable') {
      args.svgo = true;
      args.svgoDisabled.push(readValue(argv, ++i, arg));
    } else if (arg === '--svgo-precision') {
      args.svgo = true;
      args.svgoPrecision = parseInteger(readValue(argv, ++i, arg), 'svgo precision');
    } else if (arg === '--svgo-multipass') {
      args.svgo = true;
      args.svgoMultipass = true;
    } else if (arg === '--svgo-pretty') {
      args.svgo = true;
      args.svgoPretty = true;
    } else if (arg === '--svgo-indent') {
      args.svgo = true;
      args.svgoIndent = parseInteger(readValue(argv, ++i, arg), 'svgo indent');
    } else if (arg === '--svgo-eol') {
      args.svgo = true;
      args.svgoEol = readValue(argv, ++i, arg);
      if (args.svgoEol !== 'lf' && args.svgoEol !== 'crlf') {
        fail('--svgo-eol must be lf or crlf');
      }
    } else if (arg === '--svgo-final-newline') {
      args.svgo = true;
      args.svgoFinalNewline = true;
    } else if (arg === '--svgo-datauri') {
      args.svgo = true;
      args.svgoDatauri = readValue(argv, ++i, arg);
      if (!['base64', 'enc', 'unenc'].includes(args.svgoDatauri)) {
        fail('--svgo-datauri must be base64, enc, or unenc');
      }
    } else if (arg === '--svgo-list-plugins') {
      args.svgoListPlugins = true;
    } else {
      fail(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

function readValue(argv, index, flag) {
  const value = argv[index];
  if (value === undefined || value.startsWith('--')) {
    fail(`${flag} requires a value`);
  }
  return value;
}

function parseNumber(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    fail(`${label} must be a number: ${value}`);
  }
  return number;
}

function parseInteger(value, label) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < 0) {
    fail(`${label} must be a non-negative integer: ${value}`);
  }
  return number;
}

function parseNumberList(value, expected, label) {
  const parts = value.split(',').map((part) => part.trim()).filter(Boolean);
  if (parts.length !== expected) {
    fail(`${label} requires ${expected} comma-separated numbers`);
  }
  return parts.map((part, index) => parseNumber(part, `${label}[${index}]`));
}

function optimizeOptions(profile) {
  if (!profile || profile === 'safe') {
    return {
      removeUselessCommands: true,
      useShorthands: true,
      useHorizontalAndVerticalLines: true,
      useRelativeAbsolute: true
    };
  }
  if (profile === 'size') {
    return {
      ...optimizeOptions('safe'),
      useReverse: true
    };
  }
  if (profile === 'closed') {
    return {
      ...optimizeOptions('safe'),
      useClosePath: true
    };
  }
  if (profile === 'all') {
    return {
      removeUselessCommands: true,
      removeOrphanDots: true,
      useShorthands: true,
      useHorizontalAndVerticalLines: true,
      useRelativeAbsolute: true,
      useReverse: true,
      useClosePath: true
    };
  }

  const options = {};
  for (const rawName of profile.split(',')) {
    const name = rawName.trim();
    if (!name) {
      continue;
    }
    const key = optionAliases.get(name);
    if (!key) {
      fail(`Unknown optimize option: ${name}`);
    }
    options[key] = true;
  }
  return options;
}

function applyOperation(svg, op) {
  const [name, rest = ''] = op.split(/:(.*)/s);
  switch (name) {
    case 'translate': {
      const [dx, dy] = parseNumberList(rest, 2, op);
      svg.translate(dx, dy);
      break;
    }
    case 'scale': {
      const [kx, ky] = parseNumberList(rest, 2, op);
      svg.scale(kx, ky);
      break;
    }
    case 'rotate': {
      const [ox, oy, degrees] = parseNumberList(rest, 3, op);
      svg.rotate(ox, oy, degrees);
      break;
    }
    case 'relative':
      svg.setRelative(true);
      break;
    case 'absolute':
      svg.setRelative(false);
      break;
    case 'reverse':
      reversePath(svg, rest ? parseInteger(rest, 'reverse itemIndex') : undefined);
      break;
    case 'origin': {
      const [indexText, mode] = rest.split(':');
      const index = parseInteger(indexText, 'origin itemIndex');
      changePathOrigin(svg, index, mode === 'subpath');
      break;
    }
    case 'optimize':
      optimizePath(svg, optimizeOptions(rest || 'safe'));
      break;
    default:
      fail(`Unknown operation: ${name}`);
  }
}

function applyPathOperations(pathData, args) {
  const svg = new SvgPath(pathData);
  for (const op of args.ops) {
    applyOperation(svg, op);
  }
  return svg.asString(args.decimals, args.minify);
}

async function editPathData(pathData, args) {
  let result = pathData;
  if (shouldRunSvgo(args) && args.svgoOrder === 'before') {
    result = await optimizePathDataWithSvgo(result, args);
  }
  result = applyPathOperations(result, args);
  if (shouldRunSvgo(args) && args.svgoOrder === 'after') {
    result = await optimizePathDataWithSvgo(result, args);
  }
  return result;
}

function selectedIndexes(select, count) {
  if (select === 'all') {
    return new Set(Array.from({ length: count }, (_, index) => index));
  }
  const indexes = new Set();
  for (const part of select.split(',')) {
    const index = parseInteger(part.trim(), 'select index');
    if (index >= count) {
      fail(`select index ${index} is out of range; file has ${count} path d attributes`);
    }
    indexes.add(index);
  }
  return indexes;
}

async function editSvgPathAttributes(text, args) {
  const matches = Array.from(text.matchAll(/\bd\s*=\s*(["'])([\s\S]*?)\1/g));
  if (matches.length === 0 && args.ops.length > 0) {
    fail('No path d attributes found in SVG input');
  }
  const selected = selectedIndexes(args.select, matches.length);
  let index = 0;
  let output = '';
  let cursor = 0;
  for (const match of matches) {
    const [full, quote, pathData] = match;
    const start = match.index;
    const end = start + full.length;
    output += text.slice(cursor, start);
    const current = index++;
    if (!selected.has(current) || args.ops.length === 0) {
      output += full;
    } else {
      output += `d=${quote}${await editPathData(pathData, { ...args, svgo: false })}${quote}`;
    }
    cursor = end;
  }
  return output + text.slice(cursor);
}

async function editSvgText(text, args, sourcePath) {
  let result = text;
  if (shouldRunSvgo(args) && args.svgoOrder === 'before') {
    result = await optimizeSvgText(result, args, sourcePath);
  }
  result = await editSvgPathAttributes(result, args);
  if (shouldRunSvgo(args) && args.svgoOrder === 'after') {
    result = await optimizeSvgText(result, args, sourcePath);
  }
  return result;
}

function shouldRunSvgo(args) {
  return args.svgo === true;
}

function parseSvgoPlugin(spec) {
  const separator = spec.indexOf(':');
  if (separator === -1) {
    return spec;
  }
  const name = spec.slice(0, separator);
  const json = spec.slice(separator + 1);
  try {
    return {
      name,
      params: JSON.parse(json)
    };
  } catch (error) {
    fail(`Invalid JSON params for SVGO plugin ${name}: ${error.message}`);
  }
}

async function buildSvgoConfig(args, sourcePath) {
  const config = args.svgoConfig ? { ...(await loadConfig(args.svgoConfig)) } : {};

  if (args.svgoPrecision != null) {
    config.floatPrecision = Math.min(args.svgoPrecision, 20);
  }
  if (args.svgoMultipass) {
    config.multipass = true;
  }
  if (args.svgoDatauri) {
    config.datauri = args.svgoDatauri;
  }
  if (sourcePath) {
    config.path = sourcePath;
  }
  if (args.svgoPretty || args.svgoIndent != null || args.svgoEol || args.svgoFinalNewline) {
    config.js2svg = { ...config.js2svg };
    if (args.svgoPretty) {
      config.js2svg.pretty = true;
    }
    if (args.svgoIndent != null) {
      config.js2svg.indent = args.svgoIndent;
    }
    if (args.svgoEol) {
      config.js2svg.eol = args.svgoEol;
    }
    if (args.svgoFinalNewline) {
      config.js2svg.finalNewline = true;
    }
  }

  const plugins = [];
  const usePreset = args.svgoPreset === 'default' || args.svgoDisabled.length > 0;
  if (usePreset) {
    const overrides = Object.fromEntries(args.svgoDisabled.map((name) => [name, false]));
    plugins.push(args.svgoDisabled.length > 0 ? {
      name: 'preset-default',
      params: { overrides }
    } : 'preset-default');
  } else if (args.svgoPreset === 'none') {
    config.plugins = [];
  }
  if (args.svgoPlugins.length > 0) {
    plugins.push(...args.svgoPlugins.map(parseSvgoPlugin));
  }
  if (plugins.length > 0 || args.svgoPreset === 'none') {
    config.plugins = plugins;
  }
  return config;
}

async function optimizeSvgText(text, args, sourcePath) {
  const config = await buildSvgoConfig(args, sourcePath);
  return optimizeSvg(text, config).data;
}

async function optimizePathDataWithSvgo(pathData, args) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg"><path d="${escapeAttribute(pathData)}"/></svg>`;
  const optimized = await optimizeSvgText(svg, args);
  const match = optimized.match(/\bd\s*=\s*(["'])([\s\S]*?)\1/);
  if (!match) {
    fail('SVGO removed or could not return a path d attribute from raw path input');
  }
  return match[2];
}

function escapeAttribute(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function printSvgoPlugins() {
  for (const plugin of builtinPlugins) {
    const kind = plugin.isPreset ? 'preset' : 'plugin';
    console.log(`${plugin.name}\t${kind}\t${plugin.description || ''}`);
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(usage);
    return;
  }
  if (args.svgoListPlugins) {
    printSvgoPlugins();
    return;
  }
  if (args.path && args.input) {
    fail('Use either --path or --input, not both');
  }
  if (!args.path && !args.input) {
    fail('Provide --path or --input');
  }
  if (args.svgoDatauri && args.svgoOrder === 'before' && args.ops.length > 0) {
    fail('--svgo-datauri cannot run before path operations');
  }

  let output;
  if (args.path) {
    output = await editPathData(args.path, args);
  } else {
    const text = await readFile(args.input, 'utf8');
    if (/<path\b|<svg\b/i.test(text)) {
      output = await editSvgText(text, args, args.input);
    } else {
      output = await editPathData(text.trim(), args);
    }
  }

  if (args.output) {
    await writeFile(args.output, output, 'utf8');
  } else {
    process.stdout.write(`${output}\n`);
  }
}

function fail(message) {
  console.error(`svg-path-cli: ${message}`);
  console.error(usage);
  process.exit(1);
}

main().catch((error) => {
  console.error(`svg-path-cli: ${error.message}`);
  process.exit(1);
});

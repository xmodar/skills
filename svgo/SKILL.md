---
name: svgo
description: Edit, transform, optimize, reverse, and serialize SVG path data using Yqnn/svg-path-editor's svg-path-editor-lib and optimize whole SVG documents with SVGO. Use when Codex needs to modify SVG path d attributes, raw SVG path strings, icon paths, path coordinates, raw SVG matrix transforms, command relative/absolute form, subpath order, path origin, SVG cleanup, SVGO plugin presets, SVG minification, or SVG file optimization from a local CLI workflow.
---

# SVGO

Use this skill for deterministic edits to SVG path `d` data and whole-file SVG optimization. Prefer the bundled CLI before hand-editing path strings or manually minifying SVG markup.

## Quick Start

1. Run the CLI directly first. Do not install dependencies as a preflight on every skill use.

2. If the script fails with a missing module/dependency error because `scripts/node_modules` is absent, create it once, then retry the same command:

```bash
npm install --prefix <skill-dir>/scripts
```

3. Run the CLI with raw path data or an SVG file:

```bash
node <skill-dir>/scripts/svg-path-cli.mjs --path "M 0 0 L 10 0 L 10 10 L 0 10 Z" --op "optimize:safe" --minify
node <skill-dir>/scripts/svg-path-cli.mjs --input icon.svg --output icon.optimized.svg --op "translate:2,-1" --op "optimize:size" --minify
node <skill-dir>/scripts/svg-path-cli.mjs --path "M10 10h5v5z" --op "matrix(-1,0,0,1,30,0)" --minify
node <skill-dir>/scripts/svg-path-cli.mjs --input icon.svg --output icon.svgo.svg --svgo --svgo-multipass --svgo-precision 3
```

Use `--help` for all CLI options and operation formats.

## Workflow

1. Identify whether the user gave a raw path string or an SVG file.
2. Run the script before installing dependencies. If the run fails because `scripts/node_modules` is missing, run `npm install --prefix <skill-dir>/scripts` once and retry. Do not run `npm install` on every skill use.
3. Preserve the original file unless the user explicitly asks for in-place replacement. Write edited SVGs to a new output path.
4. Use path operations for coordinate edits, path reversal, origin changes, or selected path `d` attributes.
5. Use SVGO for whole-document cleanup: metadata/comments, style minification, transforms, shape-to-path conversion, path-data conversion, ID cleanup, attribute sorting, and file minification.
6. Apply path operations in the user-specified order with repeated `--op` flags.
7. Run SVGO after path-index-specific edits unless the user asks for `--svgo-order before`; SVGO plugins such as `mergePaths` and `convertPathData` can change path command structure and indexes.
8. Use `--decimals` and `--minify` for path serialization; use `--svgo-precision`, `--svgo-pretty`, and related flags for SVGO serialization.
9. Render or inspect the result when visual fidelity matters.

## Operations

The CLI supports these ordered `--op` values:

- `translate:dx,dy`
- `scale:kx,ky`
- `matrix:a,b,c,d,e,f` or `matrix(a,b,c,d,e,f)` for a raw SVG affine matrix
- `rotate:ox,oy,degrees`
- `relative`
- `absolute`
- `reverse` or `reverse:itemIndex`
- `origin:itemIndex` or `origin:itemIndex:subpath`
- `optimize:safe`, `optimize:size`, `optimize:closed`, `optimize:all`, or `optimize:<comma-separated upstream flags>`

Prefer `optimize:safe` for normal icon cleanup. Use `optimize:size` when smaller output is more important and path direction can change. Use `optimize:closed` or `optimize:all` only when closing paths or removing orphan dots will not change stroked rendering.

The `matrix` operation accepts comma or whitespace separators and maps points using the SVG convention `x' = a*x + c*y + e`, `y' = b*x + d*y + f`. Use it to bake group or path transforms into raw path data; it can handle reflected, rotated, skewed, and arc paths.

## SVGO Operations

Use `--svgo` for default whole-file optimization with SVGO's `preset-default`.

- `--svgo-config FILE`: load a project `svgo.config.js`, `.mjs`, or `.cjs`.
- `--svgo-plugin NAME[:JSON]`: run an explicit built-in plugin, optionally with JSON params.
- `--svgo-disable NAME`: keep `preset-default` but disable one of its plugins.
- `--svgo-preset none`: run only explicitly listed `--svgo-plugin` entries.
- `--svgo-multipass`: run repeated optimization passes while output shrinks.
- `--svgo-precision N`: set SVGO global float precision.
- `--svgo-pretty`, `--svgo-indent N`, `--svgo-eol lf|crlf`, `--svgo-final-newline`: control output formatting.
- `--svgo-datauri base64|enc|unenc`: output a data URI.
- `--svgo-list-plugins`: list built-in SVGO plugin names.

Examples:

```bash
node <skill-dir>/scripts/svg-path-cli.mjs --input icon.svg --output icon.min.svg --svgo --svgo-disable cleanupIds
node <skill-dir>/scripts/svg-path-cli.mjs --input icon.svg --output icon.responsive.svg --svgo-preset none --svgo-plugin removeDimensions --svgo-plugin sortAttrs
node <skill-dir>/scripts/svg-path-cli.mjs --input icon.svg --output icon.prefixed.svg --svgo --svgo-plugin 'prefixIds:{"prefix":"icon"}'
```

Avoid `removeViewBox` unless fixed-size, non-scaling SVG output is intentional. Disable `cleanupIds` when IDs are referenced from CSS, scripts, HTML, or external documents.

## References

Read `references/upstream-library.md` before extending path-command behavior. Read `references/svgo.md` before extending SVGO integration or choosing potentially destructive SVGO plugins.

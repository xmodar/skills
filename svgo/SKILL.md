---
name: svgo
description: SVG asset engineering with the published `svgo` CLI via `uvx svgo` only; use for path editing, SVG optimization, validation, measurement, sanitization, viewport normalization, conversion, PNG tracing, centerline reconstruction, and reusable declarative SVG recipes.
---

# SVGO

Use the published `svgo` command through `uvx` for every task.

Base commands:

```bash
uvx svgo --help
uvx svgo <command> --help
uvx svgo recipe --help
```

Do not rely on repository checkouts, local helper scripts, package imports,
language runtimes, Node tooling, or separate image/vector utilities for normal
skill work. If a workflow needs batching, repeatability, heuristics, reports,
or several operations, build a `svgo recipe` JSON file and run it with
`uvx svgo recipe run`.

Do not pin the package in examples. Use the current published command unless
the user explicitly asks for a reproducible historical run.

## Operating Rules

1. Preserve source files unless the user explicitly asks for replacement. Write
   outputs to new paths such as `*.min.svg`, `*.safe.svg`, `*.flat.svg`,
   `*.stroke.svg`, or a dedicated output directory.
2. Prefer a single `uvx svgo` command for one-off work. Prefer a recipe when a
   pipeline has more than two steps, needs batch processing, needs a report, or
   has lossy choices.
3. Run `uvx svgo <command> --help` before using uncommon flags or when the
   package may have changed.
4. Validate after structural changes. Visually inspect rendered output when
   tracing, centerlining, flattening transforms, or editing path geometry.
5. Optimize near the end of the pipeline. For path-index-specific edits, avoid
   whole-SVG optimization before selection unless the user asks for
   `--svgo-order before`, because optimizer passes can change path order and
   structure.
6. Treat PNG tracing and centerline reconstruction as lossy. Keep reports when
   converting many assets or when choosing thresholds.

## Command Map

The CLI commands and aliases are:

- `path` or `p`: edit raw SVG path data or `d` attributes inside SVG files.
- `opt` or `o`: optimize whole SVG documents with built-in SVGO-style passes.
- `trace` or `t`: trace PNG images into filled SVG paths.
- `trace2` or `t2`: trace PNG images with VTracer-compatible option names.
- `center` or `c`: reconstruct approximate centerline strokes from filled
  outlines.
- `info` or `i`: inspect SVG metadata and element counts as JSON.
- `validate` or `v`: validate SVG XML and static structure.
- `measure` or `m`: measure path/SVG bounds, lengths, and point-at-length data.
- `sanitize` or `s`: remove active or unsafe SVG content.
- `viewbox` or `b`: set, fit, resize, or remove root viewport metadata.
- `convert` or `x`: convert shapes, flatten transforms/groups, inline styles,
  sanitize, and remove editor-oriented markup.
- `plugins` or `l`: list built-in optimizer plugins and presets.
- `recipe` or `r`: initialize and run declarative JSON recipes.

## Recipe Building

Use recipes to express reusable SVG workflows as JSON. The recipe runner applies
steps in process through `uvx svgo`, so the invocation stays:

```bash
uvx svgo recipe init --kind cleanup --output cleanup.svgo.json
uvx svgo recipe run --recipe cleanup.svgo.json --input source.svg --output source.min.svg --report report.json
uvx svgo recipe run --recipe cleanup.svgo.json --input icons --output icons-out --report report.json
```

Recipe shape:

```json
{
  "name": "svg-cleanup",
  "description": "Short human note",
  "outputExtension": ".svg",
  "steps": [
    { "command": "sanitize", "removeExternalRefs": true },
    { "command": "convert", "all": true, "precision": 3 },
    { "command": "viewbox", "fitContent": true, "padding": 1, "removeDimensions": true, "precision": 3 },
    { "command": "validate", "strict": true },
    { "command": "opt", "multipass": true, "precision": 3 }
  ]
}
```

Step commands are normal `svgo` commands. Use long option names converted to
JSON keys: `fitContent`, `removeDimensions`, `svgPaths`, `bridgeGap`,
`strokeWidth`, `dropWhite`, `whiteThreshold`, `alphaThreshold`, `minArea`,
`multipass`, and `precision`.

Recipe actions:

- `uvx svgo recipe init --kind cleanup`: starter sanitize/convert/viewbox/validate/opt recipe.
- `uvx svgo recipe init --kind centerline-icons`: starter PNG-to-centerline recipe.
- `uvx svgo recipe init --kind path-edit`: starter path operation recipe.
- `uvx svgo recipe run -r recipe.json -i input.svg -o output.svg`: run one file.
- `uvx svgo recipe run -r recipe.json -i input-dir -o output-dir --report report.json`: batch SVG/PNG files.

Use `validate` steps as gates. Use `info` and `measure` steps for reports
without changing the current SVG. A recipe step with `validate` fails the
recipe on invalid output by default; set `"fail": false` only when the report
should collect invalid cases without stopping.

### Cleanup Recipe

Use this for untrusted, editor-exported, or layout-specific SVGs:

```json
{
  "name": "svg-cleanup",
  "outputExtension": ".svg",
  "steps": [
    { "command": "validate", "strict": false, "fail": false },
    { "command": "sanitize", "removeExternalRefs": true },
    { "command": "convert", "all": true, "precision": 3 },
    { "command": "viewbox", "fitContent": true, "padding": 1, "removeDimensions": true, "precision": 3 },
    { "command": "validate", "strict": true },
    { "command": "opt", "multipass": true, "precision": 3 }
  ]
}
```

Run it:

```bash
uvx svgo recipe run --recipe cleanup.svgo.json --input source.svg --output source.clean.svg --report cleanup.report.json
```

### PNG Centerline Recipe

Use this for palette PNG line icons that should become stroked SVG paths:

```json
{
  "name": "centerline-icons",
  "outputExtension": ".svg",
  "steps": [
    {
      "command": "trace",
      "mode": "palette",
      "palette": ["#143861", "#00b795"],
      "dropWhite": true,
      "whiteThreshold": 245,
      "alphaThreshold": 16,
      "minArea": 80,
      "decimals": 1
    },
    {
      "command": "center",
      "svgPaths": "all",
      "mode": "all",
      "polyline": true,
      "bridgeGap": 12,
      "keepFailed": true,
      "strokeWidth": "auto",
      "decimals": 2
    },
    { "command": "opt", "multipass": true, "precision": 2 }
  ]
}
```

Run it:

```bash
uvx svgo recipe run --recipe centerline-icons.svgo.json --input input-pngs --output output-svgs --report centerline.report.json
```

Tune `palette`, `minArea`, `bridgeGap`, `polyline`, `mode`, `simplify`,
`maxSize`, and `strokeWidth` by inspecting the rendered result and the report.

### Path Edit Recipe

Use this for repeated transforms or normalization of path `d` attributes:

```json
{
  "name": "path-edit",
  "outputExtension": ".svg",
  "steps": [
    {
      "command": "path",
      "select": "all",
      "ops": ["matrix(1,0,0,1,2,-1)", "absolute", "optimize:safe"],
      "decimals": 3,
      "minify": true
    },
    { "command": "opt", "multipass": true, "precision": 3 }
  ]
}
```

## Path Editing

Use `path` for raw path data or SVG `d` attribute edits. Operations are applied
in the order provided.

```bash
uvx svgo path --path "M10 10h5v5z" --op optimize:safe --minify
uvx svgo p --path "M0 0H10V10Z" --op translate:2,-1 --op relative
uvx svgo p --input icon.svg --output edited.svg --select 0,2 --op "matrix(-1,0,0,1,30,0)" --minify
uvx svgo path --input icon.svg --output edited.svg --select all --op absolute --op optimize:safe --decimals 3 --minify
```

Supported `--op` values:

- `translate:dx,dy`
- `scale:kx,ky`
- `matrix:a,b,c,d,e,f` or `matrix(a,b,c,d,e,f)`
- `rotate:ox,oy,degrees`
- `relative`
- `absolute`
- `reverse` or `reverse:itemIndex`
- `origin:itemIndex` or `origin:itemIndex:subpath`
- `cubics`, `cubic`, `to-cubics`, or `toCubics`
- `optimize:safe`, `optimize:size`, `optimize:closed`, `optimize:all`
- `optimize:remove-useless,use-shorthands,use-hv,use-relative-absolute,use-reverse,use-close-path,remove-orphan-dots`

Prefer `optimize:safe` for normal cleanup. Use `optimize:size` only when output
size is more important than preserving path direction. Use closed/all profiles
only when closing paths or removing orphan dots will not alter stroked
rendering.

The affine matrix follows SVG convention:

```text
x' = a*x + c*y + e
y' = b*x + d*y + f
```

Arcs are converted to cubic Beziers when an arbitrary affine transform cannot
be represented as an SVG arc.

## Whole-SVG Optimization

Use `opt` for complete SVG cleanup and minification.

```bash
uvx svgo opt --input icon.svg --output icon.min.svg --svgo-multipass --svgo-precision 3
uvx svgo o -i icon.svg -o icon.keep-ids.svg --svgo-disable cleanupIds
uvx svgo opt -i icon.svg -o icon.responsive.svg --svgo-preset none --svgo-plugin removeDimensions --svgo-plugin sortAttrs
uvx svgo opt -i icon.svg -o icon.prefixed.svg --svgo-plugin 'prefixIds:{"prefix":"icon"}'
uvx svgo plugins
```

Common optimizer options:

- `--svgo-preset default|none`
- `--svgo-plugin NAME[:JSON]`
- `--svgo-disable NAME`
- `--svgo-precision N`
- `--svgo-multipass`
- `--svgo-pretty`
- `--svgo-indent N`
- `--svgo-eol lf|crlf`
- `--svgo-final-newline`
- `--svgo-datauri base64|enc|unenc`
- `--svgo-list-plugins`
- `--svgo-config FILE`

JavaScript config files are accepted for CLI compatibility but are not
executed. Avoid `removeViewBox` unless fixed-size, non-scaling output is
intentional. Disable `cleanupIds` when IDs are referenced by CSS, scripts,
HTML, sprites, masks, clips, gradients, or external documents.

## PNG Tracing

Use `trace` for simple icon-style PNG files. It decodes non-interlaced 8-bit
PNGs, groups visible pixels, traces connected component boundaries, and emits
filled SVG paths or component JSON.

```bash
uvx svgo trace --input icon.png --output traced.svg --mode palette --max-colors 8 --min-area 8 --decimals 3
uvx svgo t -i icon.png -o components.json --components-json --palette "#143861,#00b795" --drop-white
uvx svgo trace --input mono.png --output mono.svg --mode alpha --drop-white --alpha-threshold 16
```

Options include `--mode palette|alpha|exact`, `--curve-mode pixel|exact`,
`--components-json`, `--drop-white`, `--alpha-threshold`, `--white-threshold`,
`--quantize`, `--max-colors`, `--min-area`, `--scale`, `--decimals`,
`--palette`, and `--title`.

Use `trace2` when the user provides VTracer-style settings or expects those
option names:

```bash
uvx svgo trace2 --input icon.png --output traced.svg --curve-mode spline --filter-speckle 4
uvx svgo t2 -i icon.png -o traced.svg --color-mode binary --path-precision 6
```

`trace2` options include `--color-mode`, `--hierarchical` or `--clustering`,
`--color-precision`, `--gradient-step`, `--filter-speckle`, `--curve-mode`,
`--corner-threshold`, `--segment-length`, `--max-iterations`,
`--splice-threshold`, and `--path-precision`.

## Centerline Reconstruction

Use `center` when a filled closed outline visually represents a stroked open
path and normal path optimization cannot infer the simpler stroke.

```bash
uvx svgo center --path "M0 0L100 0L100 20L0 20Z" --emit d --polyline --stroke-width auto
uvx svgo c --input outline.svg --output stroke.svg --emit svg --stroke-width auto
uvx svgo c --input traced.svg --output centerline.svg --svg-paths all --mode all --bridge-gap 12 --keep-failed
uvx svgo opt --input centerline.svg --output centerline.min.svg --svgo-multipass --svgo-precision 3
```

Important options:

- `--emit path|svg|d`
- `--mode longest|all`
- `--scale N`
- `--max-size N`
- `--curve-samples N`
- `--simplify N`
- `--min-length N`
- `--stroke-width auto|N`
- `--linecap VALUE`
- `--linejoin VALUE`
- `--decimals N`
- `--polyline`
- `--fill-rule evenodd|nonzero`
- `--svg-paths first|all`
- `--keep-failed`
- `--bridge-gap N`

Centerline reconstruction is approximate. Inspect the rendered output before
final optimization. Use `--mode all` for branched or multi-loop outlines, and
`--bridge-gap` when skeleton chains are fragmented but should reconnect.

## Inspect, Validate, Measure

Use these commands before and after destructive or visual transformations.

```bash
uvx svgo info --input icon.svg --compact
uvx svgo validate --input icon.svg --strict --json
uvx svgo measure --path "M0 0H10V10H0Z" --decimals 3
uvx svgo measure --input icon.svg --compact
uvx svgo m --path "M0 0H10V10" --at 12 --decimals 3
```

`validate` exits non-zero for invalid SVG. With `--strict`, warnings also fail
the command. `measure --at` requires raw path input or an SVG with exactly one
measurable path.

## Sanitize, Viewport, Convert

Use these commands to normalize untrusted, editor-exported, or layout-specific
SVGs before final optimization.

```bash
uvx svgo sanitize --input unsafe.svg --output safe.svg --remove-external-refs
uvx svgo s -i unsafe.svg -o static.svg --remove-styles --remove-raster-images
uvx svgo viewbox --input icon.svg --output fitted.svg --fit-content --padding 1 --precision 2 --remove-dimensions
uvx svgo b -i icon.svg -o normalized.svg --set "0 0 24 24" --remove-dimensions
uvx svgo convert --input shapes.svg --output paths.svg --shapes-to-paths
uvx svgo x -i drawing.svg -o plain.svg --to-plain
uvx svgo x -i transformed.svg -o flat.svg --shapes-to-paths --flatten-transforms --flatten-groups
uvx svgo x -i source.svg -o converted.svg --all --precision 3
```

Sanitize options include `--precision`, `--remove-external-refs`,
`--disallow-data-images`, `--remove-styles`, and `--remove-raster-images`.

Viewport options include `--set`, `--fit-content`, `--padding`, `--width`,
`--height`, `--remove-dimensions`, and `--precision`.

Convert options include `--to-plain`, `--shapes-to-paths`,
`--flatten-transforms`, `--flatten-groups`, `--inline-styles`, `--sanitize`,
`--all`, and `--precision`. With no conversion flag, `convert` defaults to
shape-to-path conversion.

## SVG Mechanisms Context

Use this context when choosing commands or recipe steps:

- `viewBox` defines the coordinate system. Prefer fitting or setting it before
  final optimization, and remove `width`/`height` for scalable icons when
  appropriate.
- Path `d` order matters for `--select` indexes. Whole-document optimization
  can merge, remove, or reorder paths.
- `transform` attributes compose down the tree. Use `convert --flatten-transforms`
  before measuring, centerlining, or comparing geometry when inherited
  transforms matter.
- CSS classes and style elements may carry fills, strokes, opacity, or display
  state. Use `convert --inline-styles` or `convert --all` when a standalone SVG
  must preserve visible appearance without external CSS.
- IDs can be referenced by gradients, masks, clips, markers, filters, CSS,
  `<use>`, sprites, or host documents. Disable `cleanupIds` or use `prefixIds`
  when references matter.
- Sanitizing removes active content and can remove external references, style
  content, and raster images depending on flags. Preserve semantically useful
  `<title>` or `<desc>` unless the user wants decorative output.
- Tracing turns pixels into filled paths. `center` turns filled paths into
  approximate strokes. Tune thresholds with rendered inspection, not byte size
  alone.

## Common Pipelines

SVG cleanup:

```bash
uvx svgo validate -i source.svg --strict --json
uvx svgo sanitize -i source.svg -o source.safe.svg --remove-external-refs
uvx svgo convert -i source.safe.svg -o source.flat.svg --all --precision 3
uvx svgo viewbox -i source.flat.svg -o source.fit.svg --fit-content --padding 1 --remove-dimensions --precision 3
uvx svgo opt -i source.fit.svg -o source.min.svg --svgo-multipass --svgo-precision 3
```

SVG path edit:

```bash
uvx svgo path -i icon.svg -o icon.edited.svg --select all --op "matrix(1,0,0,1,2,-1)" --op optimize:safe --decimals 3 --minify
uvx svgo opt -i icon.edited.svg -o icon.final.svg --svgo-multipass --svgo-precision 3
```

PNG vectorization:

```bash
uvx svgo trace -i icon.png -o icon.traced.svg --mode palette --max-colors 8 --min-area 8 --drop-white
uvx svgo opt -i icon.traced.svg -o icon.traced.min.svg --svgo-multipass --svgo-precision 3
```

Filled outline to stroke:

```bash
uvx svgo center -i outline.svg -o outline.stroke.svg --svg-paths all --mode all --emit svg --stroke-width auto --bridge-gap 12
uvx svgo opt -i outline.stroke.svg -o outline.stroke.min.svg --svgo-multipass --svgo-precision 3
```

When a task asks for a reusable workflow, create or update a `.svgo.json`
recipe and run it with `uvx svgo recipe run`.

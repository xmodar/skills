---
name: svgo
description: SVG asset engineering with the published `svgo` Python package via `uvx svgo` and `uv run --with svgo`; use for path editing, SVG optimization, validation, measurement, sanitization, viewport normalization, conversion, PNG tracing, centerline reconstruction, and building reusable SVG conversion recipes.
---

# SVGO

Use the published Python package `svgo` as the SVG toolchain. For command-line
work, run it through `uvx` so the command resolves from PyPI without relying on
a repository checkout or a preinstalled executable.

Base commands:

```bash
uvx svgo --help
uvx svgo <command> --help
```

Do not pin the package in skill examples. Use the current published `svgo`
command unless the user explicitly asks for a reproducible historical run.

For Python recipes, run Python through `uv` and install `svgo` into that command
environment:

```bash
uv run --with svgo python recipe.py
uv run --with svgo python -c "from svgo import optimize_svg; print(optimize_svg('<svg><rect width=\"10\" height=\"10\"/></svg>'))"
```

## Operating Rules

1. Preserve source files unless the user explicitly asks for replacement. Write
   outputs to new paths such as `*.min.svg`, `*.safe.svg`, `*.flat.svg`, or a
   dedicated output directory.
2. Prefer existing SVG/vector input over PNG tracing. Trace PNGs only when no
   better vector source exists.
3. Use the shortest reliable workflow first: a single `uvx svgo` command for
   one-off file work, a Python recipe when the task needs batching,
   per-component decisions, reports, heuristics, or multiple public APIs.
4. Run `uvx svgo <command> --help` before using uncommon flags or when the
   local package may have changed.
5. Validate and inspect after structural changes. Render or otherwise visually
   inspect results when tracing, centerlining, flattening transforms, or editing
   path geometry.
6. Optimize near the end of the pipeline. For path-index-specific edits, avoid
   optimizing before selection unless the user asks for `--svgo-order before`,
   because optimizer passes can change path order and structure.

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

## Path Editing

Use `path` for raw path data or SVG `d` attribute edits. Operations are applied
in the order they are provided.

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

Tracing options:

- `--mode palette|alpha|exact`
- `--curve-mode pixel|exact`
- `--components-json`
- `--drop-white`
- `--alpha-threshold N`
- `--white-threshold N`
- `--quantize N`
- `--max-colors N`
- `--min-area N`
- `--scale N`
- `--decimals N`
- `--palette "#RRGGBB,..."`
- `--title TEXT`

Choose `palette` for colored icons, `alpha` for single-color masks, and
`exact` only when color fidelity matters more than path count.

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

Centerline reconstruction is lossy. Inspect the rendered output before final
optimization. Use `--mode all` for branched or multi-loop outlines, and
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

## Recipe Building

Build a Python recipe when the task needs any of these:

- batch conversion with consistent naming, output directories, reports, or
  parallelism;
- per-component decisions from traced PNG component JSON;
- combining trace, centerline, path cleanup, metric checks, and final
  optimization;
- preserving colors/groups while simplifying geometry;
- heuristics such as dot detection, solid-line fallback, branch preservation,
  radial centerline candidates, or custom quality thresholds;
- producing repeatable artifacts for many input files.

Run recipe scripts with:

```bash
uv run --with svgo python recipes/my_recipe.py INPUT OUTPUT
```

Recipe structure:

1. Parse paths and options with `argparse` and `pathlib`.
2. Read inputs without overwriting originals.
3. Normalize unsafe or editor-heavy SVGs with `sanitize_svg`,
   `inline_styles_svg`, `convert_shapes_svg`, `flatten_svg`, or `to_plain_svg`.
4. Use `trace_png_components` for PNGs when component-level color, area, bbox,
   and path decisions matter.
5. Use `centerline_path_data` or `centerline_svg_text` for filled stroke
   outlines; evaluate multiple `CenterlineOptions` when needed.
6. Use path helpers to simplify, stitch, measure, and serialize candidate
   geometry.
7. Use `validate_svg`, `get_svg_info`, `path_metrics`, or `svg_metrics` for
   gates and reports.
8. Run `optimize_svg` last, unless intermediate optimization is needed for a
   specific heuristic.
9. Write a JSON report when a recipe makes lossy choices or processes many
   assets.

Public imports commonly used in recipes:

```python
from svgo import (
    BUILTIN_PLUGINS,
    CenterlineOptions,
    OptimizeOptions,
    PathData,
    PluginSpec,
    TraceOptions,
    VTracerOptions,
    centerline_path_data,
    centerline_svg_text,
    circle_to_path,
    convert_shapes_svg,
    detect_polyline_accuracy,
    ellipse_to_path,
    filled_loops,
    fit_viewbox_svg,
    flatten_svg,
    get_svg_info,
    inline_styles_svg,
    line_to_path,
    normalize_color,
    optimize_path_data,
    optimize_svg,
    path_bbox,
    path_length,
    path_metrics,
    point_at_length,
    polygon_to_path,
    polyline_lengths,
    polyline_subpaths,
    polyline_to_path,
    radial_centerline_candidate,
    rect_to_path,
    remove_collinear_points,
    resize_svg,
    sanitize_svg,
    serialize_polyline_subpaths,
    set_viewbox_svg,
    simplify_closed_points,
    simplify_points,
    simplify_radial_distance,
    simplify_rdp,
    stitch_subpaths,
    svg_metrics,
    to_plain_svg,
    trace_image_vtracer,
    trace_png,
    trace_png_components,
    transform_path,
    validate_svg,
)
```

Minimal batch recipe pattern:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path

from svgo import OptimizeOptions, fit_viewbox_svg, optimize_svg, sanitize_svg, validate_svg


def process_svg(src: Path, dst: Path, decimals: int) -> dict:
    original = src.read_text(encoding="utf-8")
    safe = sanitize_svg(original, remove_external_refs=True)
    fitted = fit_viewbox_svg(safe, padding=1, precision=decimals, remove_dimensions=True)
    optimized = optimize_svg(fitted, OptimizeOptions(float_precision=decimals, multipass=True))
    report = validate_svg(optimized, strict=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(optimized, encoding="utf-8")
    return {"input": str(src), "output": str(dst), "valid": report["valid"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--decimals", type=int, default=3)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    inputs = [args.input] if args.input.is_file() else sorted(args.input.glob("*.svg"))
    results = [
        process_svg(path, args.output / path.name if args.output.suffix == "" else args.output, args.decimals)
        for path in inputs
    ]
    if args.report:
        args.report.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Advanced PNG-to-centerline recipe pattern:

1. `trace_png_components(path, TraceOptions(mode="palette", palette=(...), drop_white=True, min_area=...))`
2. Sort components by color, area, and bbox for deterministic output.
3. For each component, try `radial_centerline_candidate` for two-loop radial
   outlines, `centerline_path_data(..., CenterlineOptions(mode="all",
   polyline=True, bridge_gap=...))` for branched outlines, and
   `centerline_path_data(..., CenterlineOptions(mode="longest"))` for simple
   strokes.
4. Use `polyline_subpaths`, `polyline_lengths`, `stitch_subpaths`,
   `turn_stats`, `remove_collinear_points`, and `simplify_rdp` to decide
   whether to keep polyline output or smooth cubic output.
5. Serialize grouped `<path>` elements by color, then call `optimize_svg`.
6. Include per-file counts, stroke widths, fallback types, and errors in a
   report.

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

Use the existing `recipes/two_color_centerline_icons.py` pattern when a task
asks for two-color antialiased PNG line icons, grouped output paths per color,
branch-preserving centerlines, and conversion reports.

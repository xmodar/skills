---
name: svgo
description: >-
  Optimize and normalize SVG assets, especially brand and product logos, to a strict house style. Runs svgo at
  precision 2, pretty-prints one element per line, replaces currentColor with the real brand hex, and adds the
  structural pass svgo cannot do on its own: collapsing symmetry into use elements, turning paths back into
  ellipse, rect and circle, folding transforms into the viewBox, stripping Figma filter boilerplate, and
  deleting attributes that merely restate their defaults. Use this skill whenever the user asks to optimize,
  minify, clean up, shrink, simplify, or normalize an SVG or a folder of SVGs; whenever they paste raw SVG
  markup and ask what can be improved; whenever they mention svgo, viewBox, path data, gradientUnits,
  gradientTransform, or a Figma SVG export; and whenever they add a logo to an icon set that has to match the
  files already there. Also use it to convert a path into a primitive shape, deduplicate repeated path data, or
  check that an optimized SVG still renders identically.
---

# SVG optimization, house style

Logo SVGs arrive as exports — from Figma, from a brand kit, from an icon CDN — and
exports are written by machines that do not know what the shape *is*. They emit a
rounded rectangle as a Bézier path, four copies of one mirrored shape as four
separate paths, a solid mask as two stacked paths behind a gradient, and a blur as
three filter primitives where two are no-ops. svgo cleans up the *encoding*. This
skill is about the encoding **and** the layer svgo cannot reach: recognizing what the
drawing actually is and saying it in the shortest form the format allows.

Three commitments make this safe to do aggressively:

1. **Every change is verified by rendering.** Never ship a "simplification" you did
   not rasterize and diff. `scripts/render_diff.cjs` does this in one command.
2. **Geometry claims are measured, not eyeballed.** "That's an ellipse", "that's the
   same shape flipped", "that's clipped" are testable propositions.
   `scripts/fit_shapes.py` and `scripts/ink_bbox.cjs` test them.
3. **Measure from pixels when transforms are involved.** `getBBox()` is a trap here;
   the Framing section explains why, and it has fooled this workflow more than once.

## Workflow

0. **Ask whether this is even the right asset.** Render it and look. The most
   valuable move is often not optimizing this file at all — see *Right asset first*
   below. Skipping this step means lavishing clever structural work on the wrong
   picture, which is the single most wasteful thing you can do here.
1. **Read the file and identify the drawing.** What is this logo? A circle with
   gradient washes? A rounded square with a glyph knocked out? Four copies of one
   curl? The answer determines which structural passes are worth trying.
2. **Check the framing** with `scripts/ink_bbox.cjs` — does the art fit its viewBox,
   is it clipped, does an icon have breathing room? Settle this before optimizing,
   because the answer can delete geometry.
3. **Run svgo** with `scripts/svgo.config.mjs` — this is the encoding pass.
4. **Structural pass** — the sections below, in roughly descending payoff.
5. **Format** to the house style with `scripts/house_format.py`.
6. **Verify** with `scripts/render_diff.cjs` against the original.
7. **Report** before/after bytes (raw and gzipped) and the measured RMSE.

Work in a scratch directory, never in place, until the diff comes back clean.

`references/worked-examples.md` holds real before/after cases — a circle under
gradient washes, a four-fold mirror, blurred blobs behind a mask, a rounded
rectangle written as a path. When a file resembles one of them, read that entry
first; the saving comes from recognizing the pattern, not from squeezing digits.

## Right asset first

An encoding pass on the wrong picture is wasted work, and the wrong picture is
common. Render the file and compare it against the brand's current official mark
before touching anything. Replace rather than optimize when:

- **It is a stand-in.** A generic or emoji glyph standing in for a real logo — a
  cartoon banana where the product's actual mark is a line-art icon. No amount of
  path golf fixes this.
- **It is a variant, not the mark.** A monochrome silhouette of a logo that has a
  colour; a wordmark where you need the icon; a crop that lost the padding.
- **It is drawn far more elaborately than it looks.** Tens of KB, thousands of
  nodes, stacked `mix-blend-mode` layers or half a dozen gradients producing what
  reads as a flat two-tone shape. The official SVG will be smaller than anything
  you can achieve by cleaning up the export.
- **The brand redesigned.** The file is the old mark.

When you replace, keep the source's natural viewBox and its padding rather than
re-cropping to taste, and say plainly which files you *replaced* versus *optimized* —
replacing is a content change the user has to agree with, and it is not reversible
by re-running the optimizer.

## Framing and the viewBox

```bash
node scripts/ink_bbox.cjs file.svg [--pad 30] [--px 3000]
```

Reports where the ink actually lands, the margin on each side, and a verdict:
`fits`, `flush` (touching an edge), or `CLIPPED`. Run it on the input and on your
output.

**Do not use `getBBox()` for this.** On a container it unions its children's boxes
*after transforming the corners of each child's axis-aligned box* — and the AABB of
a rotated AABB is strictly larger than the AABB of the rotated shape. At 120° that
inflates the answer enormously. Worse, hand-rolled corner math makes the identical
mistake, so the two agree and look like corroboration. A pixel scan is the only
arbiter that cannot be fooled this way.

The same script has a second trap worth knowing if you write your own: to re-render
with a padded viewBox you must *edit* the root tag, never rebuild it. Rebuilding
drops inherited presentation attributes — a `stroke-width` or `fill` on the root —
and the art then measures as if it had a hairline stroke. The number looks plausible
and is wrong.

How to read the verdict:

- **fits** — an icon-shaped mark should land here, with real margin on all four
  sides, roughly centred. Icons live next to other icons at a common box size, and
  one that bleeds to its edges reads as oversized in the row. A tight crop is right
  for a wordmark, not for an icon.
- **flush** — the art touches an edge. Often deliberate (a mark designed to bleed);
  by itself it is not a defect. Do not "fix" it without asking.
- **CLIPPED** — the art runs outside the box and is being cut. Now decide *which* is
  wrong, the crop or the shape, and say so with the number. If the flat cut is the
  intended design, the fix is not a bigger viewBox: **extend the shapes to the edge
  and delete the geometry that lived outside it.** Rounded ends nobody can see are
  pure bytes.

## House format

Output is pretty-printed and readable — the files are read and hand-edited by
people, so a single 4KB line is worse than a slightly larger file that a human can
scan. Two-space indent, one element per line:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <path fill="#0143d9" d="M3 0h19v1.8L13.9 12 22 22.2V24H3Z"/>
</svg>
```

The root element carries `xmlns` and `viewBox` and nothing else — no `width`,
no `height`, no `fill="none"`, no `fill-rule="evenodd"`, no `xmlns:xlink`, no
stray space before `>`. The one exception: a paint attribute that genuinely
factors out of every child belongs on the root, because that is real deduplication
(`fill="#7d2ae7"` when every shape is that purple, `fill-opacity=".56"` when the
whole mark is dimmed).

Use `href`, never `xlink:href`. Ids are single letters — `a`, `b`, `c` in document
order, or `g` when there is exactly one gradient.

## Color

Exports hedge with `currentColor` and `fill="none"`. Resolve them:

- Replace `currentColor` with the actual brand hex, lowercase, shortest form.
  Look the color up rather than guessing — brand hexes are published, and a logo
  in the wrong color is worse than an unoptimized one.
- A black mark gets **no** `fill` at all; black is already the default. But check
  that it really is black: plenty of "monochrome" brands use a specific near-black
  (Manus is `#34322d`), and a source that ships light/dark variants tells you the
  mark is monochrome, not that it is `#000`. Spend the lookup — a logo in the wrong
  colour is worse than an unoptimized one, and "it looked black" is not a finding.
- White fills are a trap. An exported logo often assumes a dark background, so
  `fill="#fff"` renders as an invisible hole on a white page. Flip it to `#000`
  (or the brand color) when the asset will sit on light backgrounds, and say so
  in your report — this is a judgment call the user may want to override.
- For a fully transparent gradient stop, 8-digit hex (`#6420ff00`) beats
  `stop-color="#6420ff" stop-opacity="0"`.

## Structural passes

These are ordered by how much they typically save. Not all apply to every file;
skim for the ones that match what you saw in step 1.

### Fold transforms into the viewBox

A `transform="translate(0 1)"` repeated on every element is the same as shifting
the viewport the other way. `viewBox="0 0 24 24"` + six `translate(0 1)` becomes
`viewBox="0 -1 24 24"` and zero transforms, with no path data touched.

A uniform `scale(k)` wrapping everything can be folded into the geometry instead
(multiply coordinates), which is worth it when it also lets shapes collapse into
primitives.

### Recognize primitives

Run `scripts/fit_shapes.py <file.svg>`. It samples each path, fits a conic, and
reports center, radii, rotation, and the max radial residual. A residual under
about 0.5% of the viewBox means the path *is* that ellipse and the export just
wrote it as Béziers.

- Axis-aligned, `rx == ry` → `<circle>`
- Axis-aligned, `rx != ry` → `<ellipse>`
- Rotated → `<ellipse>` plus `transform="rotate(a)"`, with `cx`/`cy` pre-rotated
  by `-a` so the rotation can be about the origin and you avoid repeating the
  center inside `rotate(a cx cy)`.
- A rounded rectangle path (four corner arcs of equal radius) → `<rect rx>`.
  `ry` defaults to `rx`, `y` defaults to 0, so a full-bleed rounded square is
  `<rect width="100%" height="100%" rx="300"/>`.

One caveat with rotation: `filterUnits="userSpaceOnUse"` and
`gradientUnits="userSpaceOnUse"` resolve in the coordinate system the element
establishes, which now includes its own rotation. Convert those to bounding-box
units in the same pass or the paint will be applied at the wrong angle.

### Exploit symmetry

`scripts/fit_shapes.py --symmetry <file.svg>` compares every pair of paths with a
Procrustes fit and reports the rotation, scale, and max residual. A residual near
zero and a scale of 1.000 means one path is a rigid copy of another:

```svg
<g id="a">
  <path id="b" d="…"/>
  <use href="#b" transform="matrix(1 0 0 -1 0 30.8)"/>
</g>
<use href="#a" transform="matrix(-1 0 0 1 33.5 0)"/>
```

Four copies from one outline. Nest the groups so each `<use>` doubles the content.

Be skeptical: shapes that *look* symmetric often are not. A best fit that needs a
2.7% scale change and still leaves half a unit of error is two different shapes,
and merging them changes the artwork. Report the number and leave them alone.

When two elements share identical path data but different paint, hoist the
geometry into `<defs>` and reference it twice. The referenced element must carry
**no** `fill` of its own — a presentation attribute on the referenced element beats
the one inherited from `<use>`, so a `fill` there silently makes every copy the
same color.

### Delete default attributes

Exports write out defaults constantly. All of these can go when they match:

| Attribute | Default |
|---|---|
| `gradientUnits` / `filterUnits` / `maskUnits` | `objectBoundingBox` (so bbox-relative coords need no declaration) |
| `fx` / `fy` | `cx` / `cy` |
| `x1`, `y1`, `x2`, `y2` on a linear gradient | `0`, `0`, `1`, `0` — a top-to-bottom gradient is just `y2="1"` |
| `offset` on the first stop | `0` |
| `ry` | `rx` |
| `x`, `y` | `0` |
| `mask-type` | `luminance` — so an opaque white path needs no `style` |

When a `gradientTransform` is close to a uniform scale — its two column vectors
similar in length and nearly perpendicular — you can sometimes delete it outright and
put the geometry in `cx`/`cy`/`r`. The centre is the matrix's translation. The radius
is **not** 1: use the equal-area radius `√|det|`, which is what the ellipse is worth
as a circle. On one real case `r="1"` cost 0.021 RMSE while `√|det|` = 0.79 cost
0.010 — half the error for the same bytes. This is a visible change either way, so
measure it, report the number, and let the user accept it rather than slipping it in.

Converting a `userSpaceOnUse` gradient to bbox fractions is worth the arithmetic
because it deletes the whole attribute: divide each coordinate by the bounding box
of the element being filled (`(coord - bbox.x) / bbox.width`). The divisor is the
*bbox*, not the viewBox — they coincide only when the art reaches all four edges.

`<defs>` is only needed for geometry that must not render on its own. Gradients,
filters, masks, and patterns are never drawn directly, so they can sit as plain
children of the root.

### Strip Figma filter boilerplate

Every blurred layer in a Figma export looks like this:

```svg
<feFlood flood-opacity="0" result="BackgroundImageFix"/>
<feBlend in="SourceGraphic" in2="BackgroundImageFix" result="shape"/>
<feGaussianBlur result="effect1_foregroundBlur_2001_67" stdDeviation="10.11"/>
```

The flood makes transparent black; the blend composites the source over transparent
nothing. Both are no-ops that exist for Figma's own round-tripping. Only the
`feGaussianBlur` survives, and the long `result` names go with them. Filters with
identical `stdDeviation` can then share one definition.

Do **not** replace `feGaussianBlur` with CSS `filter="blur(Npx)"` as a size win,
tempting as it is. SVG filters default to `color-interpolation-filters: linearRGB`
and CSS `blur()` works in sRGB, so every blurred edge blends differently. If the
user *wants* the sRGB look, that is a deliberate design change — tell them, don't
smuggle it in.

### Collapse redundant masks

A mask whose contents are fully opaque is just a silhouette. Exports often stack
two copies of a shape inside one, the first inheriting `fill="none"` from the root
(painting nothing at all) and the second filled with a gradient whose stops are all
opaque. Under `mask-type:alpha` only the alpha matters, so the whole thing reduces
to one white path — and the gradient it referenced becomes dead code.

### Absorb filled extensions back into the stroke

Exports routinely split one stroked shape into a stroke plus separate filled pieces
that continue it — an arc that stops short, with rectangles standing in for the
straight runs at each end, and small filled caps for the rounded terminals. If those
pieces are the same colour and width as the stroke, lengthening the stroke's own path
absorbs them and the extra elements disappear along with the stubs that bridged the
seams.

This pairs with the framing check: when the extensions run past the viewBox anyway,
extending the stroke to the edge and deleting the caps is both smaller and closer to
what the mark actually looks like.

### Factor shared attributes onto a group

The root is not the only place to hoist paint. When a subset of elements shares
`stroke`, `stroke-width`, `stroke-linejoin`, or `fill`, a `<g>` around them pays for
itself quickly, and groups nest — an inner `<g fill="#ffdb0f">` overriding an outer
`<g fill="none" stroke="#000">` is cheaper and much easier to read than repeating
both attributes on every child:

```svg
<g fill="none" stroke="#000" stroke-width="1.5" stroke-linejoin="round">
  <rect width="24" height="24" x="4" y="4" rx="6"/>
  <path d="…"/>
  <g fill="#ffdb0f">
    <path d="…"/>
  </g>
</g>
```

Count before committing: a wrapper costs about 22 bytes, so it wants two or three
shared attributes, or three or more children, to come out ahead.

### Merge and tidy paths

Subpaths sharing a fill belong in one `<path>`. Order paths so the file reads
top-to-bottom in a sensible way when their z-order does not interact.

## Verification

```bash
node scripts/render_diff.cjs original.svg optimized.svg [--size 1024]
```

Reports RMSE and max per-channel delta. Interpretation:

- **0.000** — reformatting, default-attribute deletion, `<use>` dedup. Expect exactly this.
- **< 0.005** — precision reduction to 2 decimals, primitive substitution. Fine.
- **< 0.02** — a rotated element resampling its own filter, or corner arcs replacing
  Bézier approximations. Acceptable, but say so in the report.
- **higher** — something changed. Find out what before shipping.

Check at more than one size. Precision loss on a mark with thin features shows up
at small sizes too, not just under magnification, and a residual that only appears at
one scale usually means rasterizer phase rather than a real difference.

The script flattens onto white before comparing. This matters more than it sounds:
a transparent PNG of a black logo has undefined RGB in the transparent region, so
comparing RGBA directly reports a perfect match between two files that differ. A
"0.000" you did not flatten for is meaningless.

## Precision

Two decimals is the house default and it is a real choice, not a habit. On a 24-unit
viewBox that is ~0.4% of the width — invisible at any display size, and it typically
takes 35-50% off the path data. One decimal breaks down: curves visibly deform and
tight corners round off. If a mark is drawn on a large viewBox (1000+ units) the
absolute error at 2 decimals is negligible and you can consider fewer digits; check
with a render diff rather than assuming.

Keep transform matrices and gradient geometry at full precision when they are exact
(`matrix(1 0 0 -1 0 30.8)` is a reflection, not a measurement).

Calibrate the acceptable residual against work the user has already shipped rather
than picking a threshold: optimize a file they previously accepted, measure it, and
use that as the bar. On one icon set the accepted precision-2 change measured 0.024
RMSE at 640px and 0.016 at 64px, which made anything in that range obviously fine and
anything well above it worth explaining.

## Reporting

For each file give before → after bytes (raw and gzipped), the measured RMSE, and a
one-line note on what actually did the work ("merged 4 paths into one, dropped the
Figma filter boilerplate"). When you decline an optimization, give the number that
made you decline it. The user is trying to learn where the bytes are, not just
receive smaller files.

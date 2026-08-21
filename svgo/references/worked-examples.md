# Worked examples

Real before/after cases. Read this when a file resembles one of them — the
saving usually comes from recognizing the pattern, not from squeezing digits.

## Circle with gradient washes (Canva)

**Was** 1050 B: four `radialGradient`s with `gradientUnits="userSpaceOnUse"` and
`gradientTransform`, five stacked `<circle r="950">` inside `<g transform="scale(.26718)">`.

**Now** ~720 B:
- The group scale folded into the circles, then into `cx="50%" cy="50%" r="50%"`.
- Gradient coordinates divided by the bbox (1900), which deletes every
  `gradientUnits`. Two of the four had uniform-scale matrices, so their
  `gradientTransform` vanished too — rotating a circular gradient about its own
  center is a no-op.
- The other two decomposed exactly into `rotate(a cx cy)scale(sx sy)`. Check for
  shear first: derive the angle from each matrix column (`atan2(B,A)` and
  `atan2(-C,D)`); if they agree, the matrix is rotation+scale and the readable
  form is exact, not an approximation.
- Base color hoisted to the root; `<circle id="o">` referenced by four `<use>`.

The trap: the referenced `<circle>` must not carry `fill` itself, or all four
`<use>` clones inherit that color instead of their gradients.

## Rotated elliptical gradient (also Canva)

A `gradientTransform` with real shear cannot be expressed without
`gradientTransform`. Bounding-box units only give axis-aligned scaling, so a
*rotated* ellipse gradient is unreachable — approximating it with a circle of
equal area cost 4% RMSE. Convert to bbox units to delete `gradientUnits`, keep
`gradientTransform`, and say why.

## Four-fold mirror symmetry (Ideogram)

One quadrant outline, flipped vertically inside a group, then the group flipped
horizontally: four copies, one `d`. Already optimal — the remaining win was the
path encoding (absolute → relative, 3 decimals → 2), 1283 → 806 B.

Recentering the viewBox so both mirrors become bare `scale(1 -1)` / `scale(-1 1)`
*looks* cleaner and saves 17 raw bytes, but loses on gzip (the repeated
`matrix(...)` strings compress well) and worsens rounding. Measure before
believing.

## Two-fold rotational symmetry (Copilot ribbon)

Two of the four paths were byte-identical; two more were a 180° rotation of them
about (12, 11) — `fit_shapes.py --symmetry` returns scale 1.00005, residual 0.0047.
Collapsing them means the gradients travel with the rotation, so pre-flip the
gradient geometry in bbox space: `(u,v) → (1-u, 1-v)`, i.e. subtract each linear
endpoint from 1, and negate a radial gradient's matrix linear part while its
translation becomes `(1-E, 1-F)`.

The other pair *looked* symmetric and was not: best fit needed 177.4° with a 2.7%
scale change and still left 0.51 units of error — two differently drawn end-caps.
Merging them showed a visibly different silhouette at 3.1% RMSE.

## Blurred blobs behind a mask (Gemini)

6409 → 2098 B:
- The mask held the sparkle twice — once inheriting `fill="none"` from the root
  (painting nothing) and once filled by a gradient with all-opaque stops. Under
  `mask-type:alpha` that is a plain silhouette: one white path, and the gradient
  became dead code.
- Every filter's `feFlood`/`feBlend` pair was a no-op; only `feGaussianBlur` survives.
- All ten blobs were exact ellipses (max residual 0.011 on a 65-unit viewBox).
- Rotating them forced the filter regions to bbox units, which then let the three
  σ=10.11 filters merge into one.

## Rounded rectangle written as a path (Humain)

`M4 300v969c0 165 134 300 300 300h961…` is `<rect x="4" width="1561" height="1569" rx="300"/>`
— 135 → 64 B. The export's Bézier corners used integer control offsets (165/134)
where the exact quarter-circle constant wants 165.685/134.315, so `<rect>` is
slightly *more* correct than the path it replaces.

Watch for asymmetry that signals an export bug: width 1561 against height 1569,
inset 4 on the left with 4 units of slack on the right. Flag it; don't silently
"fix" it, since squaring it up is a design change.

## Gradient snapped to the diagonal (Hailuo)

`x1=".02" y1=".04" x2="1.15" y2="1.13"` → `y2="1"` alone, because `x1`/`y1`/`x2`
are already the defaults for a corner-to-corner gradient. Offsets remap by
`o' = (o - t₀)/(t₁ - t₀)` where t₀/t₁ are the old axis projections of the bbox
corners (0,0) and (1,1).

Two things to check: an offset that maps past 1 is invalid, so drop that stop and
replace it with the color the ramp actually reaches at 1 (linear sRGB blend
between the last two stops). And if the old axis was not exactly 45°, the residual
tilt cannot be absorbed by offsets — measure it (here 0.87° → 4/255 on one channel)
and decide whether that is acceptable.

## Legs absorbed into the stroke, clip embraced (NotebookLM)

A four-arc rainbow: two stroked arcs stopping at mid-height, two filled rectangles
with rounded bottoms standing in for the right-hand legs, plus a gradient-filled path
for the left half. `ink_bbox` said `CLIPPED`, bottom margin −4 — the rounded leg ends
hung below the viewBox.

The wrong fix is a taller viewBox. The right one, once the flat bottom turns out to
be the design: extend both stroked arcs down to the bottom edge, which absorbs the
filled legs entirely, and flatten the gradient path's rounded ends to meet the edge
too. Four elements become two, the stroke stubs that bridged the seams go with them,
and the file lands at 856 bytes from 1375 — where a careful transcription of the
export had only reached 1139.

The gradient in the same file lost its `gradientTransform` for a plain
`cx`/`cy`/`r`. Note the radius: `r="1"` measures 0.021 RMSE against the export, while
the equal-area `√|det|` = 0.79 measures 0.010 for the same bytes.

## Padding is part of the asset (Manus)

The export wrapped a 16-unit drawing in `<g transform="scale(32)">` inside a 512
viewBox. Folding the scale into `viewBox="0 0 16 16"` is correct and drops the group
— but it also produces a mark whose ink runs 0 → 16.02 vertically, bleeding off both
edges, because the export's own box was the tight one.

Replacing it with the official 32-unit asset gives margins of 6.7/7.4 left/right and
4.3/4.5 top/bottom, and the real brand colour `#34322d` rather than the black the
monochrome variant implied. An icon that bleeds to its edges reads as oversized
beside its neighbours, so the padding is not slack to be optimized away.

## The file was never the logo (Nano Banana)

Six flat paths in the shape of a peeled-banana emoji, cleanly encoded, 1300 bytes,
and completely wrong — the product's mark is a line-art icon of a banana inside a
rounded square. The replacement is 612 bytes and uses a `<g>` to factor
`fill="none" stroke="#000" stroke-width="1.5" stroke-linejoin="round"` across its
children, with a nested `<g fill="#ffdb0f">` for the two yellow ones.

The lesson is the order of operations: render and identify the mark *before*
optimizing, because no structural cleverness recovers from working on the wrong
picture.

## Refetch, don't optimize (Flux, Firefly, Luma)

- **Flux**: a three-path 24×24 mark replaced by the current 196×140 logo.
- **Firefly**: a 512×512 export with hundreds of Bézier nodes replaced by a
  54×54 `<rect>` + glyph.
- **Luma**: six paths with `mix-blend-mode` overlays and five gradients that
  rendered as a flat two-tone mark — replaced by two plain paths plus
  `fill-opacity=".56"` on the root.

When the drawing is far more complex than what you see, the file is the wrong
asset, and no amount of encoding work fixes that.

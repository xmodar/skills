# Yqnn/svg-path-editor Library Notes

Studied upstream repository: `https://github.com/Yqnn/svg-path-editor`

- Snapshot inspected: commit `937d75a83b6be2bdda11d02b9b3594841315223a` (`937d75a`, 2026-06-18, "Bump lib version").
- License: Apache-2.0.
- Reusable package: `svg-path-editor-lib` version `1.0.4`, exported from `src/lib`.
- The Angular app is UI-only for this skill; use the library package from CLI scripts.

## Public API

```js
import { SvgPath, optimizePath, reversePath, changePathOrigin } from 'svg-path-editor-lib';

const svg = new SvgPath('M 0 0 L 10 0 L 10 10 Z');
svg.translate(dx, dy);
svg.scale(kx, ky);
svg.rotate(ox, oy, degrees);
svg.setRelative(true);  // relative commands
svg.setRelative(false); // absolute commands
reversePath(svg, optionalItemIndex);
changePathOrigin(svg, itemIndex, optionalSubpathBoolean);
optimizePath(svg, options);
const d = svg.asString(decimals, minify);
```

## Optimizer Flags

- `removeUselessCommands`
- `removeOrphanDots`: can affect stroked paths.
- `useShorthands`
- `useHorizontalAndVerticalLines`
- `useRelativeAbsolute`
- `useReverse`: may reverse path direction.
- `useClosePath`: can affect stroked paths.

## Modeling Notes

- `new SvgPath(path)` validates and parses the path, throwing on malformed input.
- Operations mutate the `SvgPath` instance in place.
- `path.path` is the array of command items; item indexes used by `reversePath` and `changePathOrigin` refer to this array.
- `asString(decimals = 4, minify = false)` serializes the final path.

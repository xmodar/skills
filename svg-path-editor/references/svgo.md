# SVGO Notes

Studied upstream repository: `https://github.com/svg/svgo`

- Snapshot inspected: commit `581fe687825740e425012bbdf6491ee4bbc9dc65` (`581fe68`, 2026-04-17, "performance: speed up mergePath child node removal (#2216)").
- Package inspected: `svgo` version `4.0.1`.
- License: MIT.
- Node requirement: Node.js 16 or newer.
- Node API: `import { optimize, loadConfig, builtinPlugins } from 'svgo';`

## Core API

```js
import { optimize, loadConfig } from 'svgo';

const config = await loadConfig('svgo.config.mjs');
const { data } = optimize(svgText, {
  ...config,
  multipass: true,
  floatPrecision: 3,
  plugins: ['preset-default'],
});
```

`optimize(svgText, config)` returns `{ data }`. By default, SVGO uses `preset-default`.

## Useful CLI Features to Expose

- `multipass`: run up to 10 passes while the output shrinks.
- `floatPrecision`: global numeric precision override.
- `datauri`: output `base64`, `enc`, or `unenc` data URI strings.
- `js2svg.pretty`, `indent`, `eol`, `finalNewline`: output formatting.
- `plugins`: explicit plugin list.
- `preset-default` with `params.overrides`: disable default plugins safely.
- `loadConfig`: load `.js`, `.mjs`, or `.cjs` config files.

## Default Preset Plugins

`preset-default` includes these plugins in order:

`removeDoctype`, `removeXMLProcInst`, `removeComments`, `removeDeprecatedAttrs`, `removeMetadata`, `removeEditorsNSData`, `cleanupAttrs`, `mergeStyles`, `inlineStyles`, `minifyStyles`, `cleanupIds`, `removeUselessDefs`, `cleanupNumericValues`, `convertColors`, `removeUnknownsAndDefaults`, `removeNonInheritableGroupAttrs`, `removeUselessStrokeAndFill`, `cleanupEnableBackground`, `removeHiddenElems`, `removeEmptyText`, `convertShapeToPath`, `convertEllipseToCircle`, `moveElemsAttrsToGroup`, `moveGroupAttrsToElems`, `collapseGroups`, `convertPathData`, `convertTransform`, `removeEmptyAttrs`, `removeEmptyContainers`, `mergePaths`, `removeUnusedNS`, `sortAttrs`, `sortDefsChildren`, `removeDesc`.

Additional built-in plugins include `addAttributesToSVGElement`, `addClassesToSVGElement`, `cleanupListOfValues`, `convertOneStopGradients`, `convertStyleToAttrs`, `prefixIds`, `removeAttributesBySelector`, `removeAttrs`, `removeDimensions`, `removeElementsByAttr`, `removeOffCanvasPaths`, `removeRasterImages`, `removeScripts`, `removeStyleElement`, `removeTitle`, `removeViewBox`, `removeXlink`, `removeXMLNS`, and `reusePaths`.

## Cautions

- `removeViewBox` can prevent scaling; disable it unless fixed-size output is desired.
- `removeDimensions` is effectively the opposite of `removeViewBox`; do not use both without checking output.
- `cleanupIds` can break externally referenced IDs.
- `prefixIds` is useful when inlining multiple SVGs into one document.
- `removeScripts`, `removeRasterImages`, `removeTitle`, and `removeDesc` intentionally remove content that may be semantically important.
- `mergePaths` and `convertPathData` can alter path structure and command indexes, so run them after path-index-specific edits unless the user requests otherwise.

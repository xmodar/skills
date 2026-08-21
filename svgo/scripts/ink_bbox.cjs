#!/usr/bin/env node
// Ground-truth bounding box, measured from pixels.
//
// Use this instead of getBBox() whenever transforms are involved. getBBox() on a
// container unions its children's *axis-aligned boxes after transforming their
// corners* -- and the AABB of a rotated AABB is strictly larger than the AABB of
// the rotated shape. For a 120-degree rotation that inflates the answer enormously,
// and both the manual corner math and the browser's own container getBBox() make
// the same mistake, so they agree with each other and look like corroboration.
//
// This renders into a padded canvas, scans for ink, and maps back to user units.
// It also reports whether the artwork fits its viewBox and how much margin it has.
//
// usage: node ink_bbox.cjs file.svg [--pad 30] [--px 3000]
const { execSync } = require('child_process');
const { chromium } = require(execSync('npm root -g', { encoding: 'utf8' }).trim() + '/playwright');
const fs = require('fs');

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf('--' + k); return i < 0 ? d : Number(argv[i + 1]); };
const file = argv.find(a => a.endsWith('.svg'));
const src = fs.readFileSync(file, 'utf8');
const vbm = src.match(/viewBox="([-\d.eE\s,]+)"/);
const VB = vbm ? vbm[1].trim().split(/[\s,]+/).map(Number) : [0, 0, 100, 100];
const PAD = opt('pad', Math.max(VB[2], VB[3]) * 0.25);
const X0 = VB[0] - PAD, Y0 = VB[1] - PAD, W = VB[2] + 2 * PAD, H = VB[3] + 2 * PAD;
const PX = opt('px', 3000);
// the raster must match the canvas aspect, or preserveAspectRatio letterboxes the
// render and every measurement on the short axis comes back shifted and squashed
const PXW = PX, PXH = Math.max(1, Math.round(PX * H / W));
// Re-open the file with a padded viewBox but keep every other root attribute.
// Rebuilding the <svg> tag from scratch silently drops inherited presentation
// attributes -- a stroke-width or fill on the root -- and the artwork then measures
// as if it had a hairline stroke, which looks like a plausible number and is wrong.
const svg = src.replace(/<svg\b[^>]*>/, tag =>
  (/\sviewBox="/.test(tag)
    ? tag.replace(/\sviewBox="[^"]*"/, ` viewBox="${X0} ${Y0} ${W} ${H}"`)
    : tag.replace(/>$/, ` viewBox="${X0} ${Y0} ${W} ${H}">`)));

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: PXW, height: PXH } });
  await p.setContent(`<style>html,body{margin:0;background:#fff}img{display:block;width:${PXW}px;height:${PXH}px}</style>`
    + `<img src="data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}">`);
  await p.waitForLoadState('networkidle');
  const png = (await p.screenshot({ type: 'png' })).toString('base64');
  const r = await p.evaluate(async ([src, w, h]) => {
    const img = await new Promise(res => { const i = new Image(); i.onload = () => res(i); i.src = src; });
    const c = new OffscreenCanvas(w, h), x = c.getContext('2d', { willReadFrequently: true });
    x.drawImage(img, 0, 0);
    const d = x.getImageData(0, 0, w, h).data;
    let x0 = w, y0 = h, x1 = -1, y1 = -1;
    for (let j = 0; j < h; j++) for (let i = 0; i < w; i++) {
      const o = (j * w + i) * 4;
      if (d[o] < 250 || d[o+1] < 250 || d[o+2] < 250) {
        if (i < x0) x0 = i; if (i > x1) x1 = i;
        if (j < y0) y0 = j; if (j > y1) y1 = j;
      }
    }
    return [x0, y0, x1, y1];
  }, ['data:image/png;base64,' + png, PXW, PXH]);
  await b.close();
  const s = W / PXW;
  const box = { x: X0 + r[0]*s, y: Y0 + r[1]*s, w: (r[2]-r[0]+1)*s, h: (r[3]-r[1]+1)*s };
  const f = v => +v.toFixed(2);
  const margin = {
    left:   f(box.x - VB[0]),
    right:  f(VB[0] + VB[2] - (box.x + box.w)),
    top:    f(box.y - VB[1]),
    bottom: f(VB[1] + VB[3] - (box.y + box.h)),
  };
  const worst = Math.min(...Object.values(margin));
  console.log(JSON.stringify({
    viewBox: VB.join(' '),
    ink: { x: f(box.x), y: f(box.y), w: f(box.w), h: f(box.h) },
    margin,
    verdict: worst < -s ? 'CLIPPED - artwork runs outside the viewBox'
           : worst < s  ? 'flush - artwork touches the edge (fine if intended)'
           : 'fits',
    resolution: f(s) + ' user units/pixel',
  }, null, 1));
})();

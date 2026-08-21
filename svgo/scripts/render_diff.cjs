#!/usr/bin/env node
// Rasterize two SVGs and report how far apart they render.
//
// The important detail: both images are flattened onto white before comparing.
// A transparent PNG has undefined RGB wherever alpha is 0, so comparing RGBA
// buffers directly can report a perfect match between files that plainly differ.
//
// usage: node render_diff.cjs a.svg b.svg [--size 1024] [--bg '#fff']
// needs: npm i -g playwright   (chromium only; no browser download in sandboxes
//        that preinstall it -- PLAYWRIGHT_BROWSERS_PATH is respected)
const { execSync } = require('child_process');
function loadPlaywright() {
  try { return require('playwright'); } catch (e) {}
  try {
    const root = execSync('npm root -g', { encoding: 'utf8' }).trim();
    return require(root + '/playwright');
  } catch (e) {
    console.error('playwright not found: npm i -g playwright'); process.exit(2);
  }
}
const { chromium } = loadPlaywright();
const { readFileSync } = require('fs');

const args = process.argv.slice(2);
const files = args.filter(a => !a.startsWith('--') && a.endsWith('.svg'));
const opt = k => { const i = args.indexOf('--' + k); return i < 0 ? null : args[i + 1]; };
if (files.length !== 2) { console.error('usage: render_diff.cjs a.svg b.svg [--size N] [--bg #fff]'); process.exit(2); }
const SIZE = Number(opt('size') || 1024);
const BG = opt('bg') || '#ffffff';

function box(file) {
  const m = readFileSync(file, 'utf8').match(/viewBox="([-\d.eE\s,]+)"/);
  if (!m) return [1, 1];
  const v = m[1].trim().split(/[\s,]+/).map(Number);
  return [v[2], v[3]];
}
const [vw, vh] = box(files[0]);
const W = SIZE, H = Math.max(1, Math.round(SIZE * vh / vw));

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  const shots = [];
  for (const f of files) {
    await page.setContent(
      `<style>html,body{margin:0;background:${BG}}img{display:block;width:${W}px;height:${H}px}</style>` +
      `<img src="data:image/svg+xml;base64,${readFileSync(f).toString('base64')}">`);
    await page.waitForLoadState('networkidle');
    shots.push((await page.screenshot({ type: 'png' })).toString('base64'));
  }
  const stats = await page.evaluate(async ([a, b, w, h]) => {
    const load = src => new Promise(res => { const i = new Image(); i.onload = () => res(i); i.src = src; });
    const px = async src => {
      const img = await load(src);
      const c = new OffscreenCanvas(w, h), x = c.getContext('2d', { willReadFrequently: true });
      x.drawImage(img, 0, 0, w, h);
      return x.getImageData(0, 0, w, h).data;
    };
    const A = await px(a), B = await px(b);
    let sum = 0, max = 0, n = 0, over = 0;
    for (let i = 0; i < A.length; i += 4) {
      let worst = 0;
      for (let k = 0; k < 3; k++) {
        const d = Math.abs(A[i + k] - B[i + k]);
        sum += d * d; if (d > max) max = d; n++;
        if (d > worst) worst = d;
      }
      if (worst > 12) over++;
    }
    return { rmse: Math.sqrt(sum / n) / 255, maxChannelDelta: max, pixelsOver5pct: over, pixels: n / 3 };
  }, ['data:image/png;base64,' + shots[0], 'data:image/png;base64,' + shots[1], W, H]);
  await browser.close();
  const verdict = stats.rmse === 0 ? 'identical'
    : stats.rmse < 0.005 ? 'equivalent (sub-pixel)'
    : stats.rmse < 0.02 ? 'close - explain the residual'
    : 'CHANGED - investigate';
  console.log(JSON.stringify({ size: `${W}x${H}`, ...stats, verdict }, null, 2));
})();

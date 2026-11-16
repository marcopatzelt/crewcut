// Runs every 2D scene in jsdom (no layout, no browser): build plus every frame, both formats, each decor, with a logo.
// It catches script errors in the scenes; it says nothing about the picture. Text widths are estimated.
// Usage: NODE_PATH=web/node_modules node tests/render/scenes_dom.js templates/2d
'use strict';
const path = require('path'), fs = require('fs');
const { JSDOM, VirtualConsole } = require('jsdom');
const dir = path.resolve(process.argv[2]);
const scenes = fs.readdirSync(dir).filter(f => f.endsWith('.html')).sort();

function brand(decor, logo) {
  return {
    css: { '--c-accent': '#2A7AE2' }, edit: { min_text_px: 40 },
    fonts: { display: { family: 'Inter', weight: 800, files: [] }, body: { family: 'Inter', weight: 500, files: [] } },
    motion: { entrance_frames: 10, entrance_from: 0.94, stagger_frames: 6, drift_per_s: 0.01, decor },
    logo: logo ? { file: '/tmp/logo.svg', placement: 'top-right', size: 54, text: 'Brand' } : { file: null, placement: 'none' },
  };
}

async function run(file, data, b, transparent) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', e => errors.push('jsdom: ' + (e.detail || e.message || e)));
  vc.on('error', m => errors.push('console.error: ' + m));
  const dom = new JSDOM(fs.readFileSync(path.join(dir, file), 'utf8'), {
    url: 'file://' + path.join(dir, file), runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse(w) {
      w.DATA = data; w.BRAND = b; if (transparent) w.TRANSPARENT = true;
      w.FontFace = class { constructor(f) { this.family = f; this.status = 'loaded'; } load() { return Promise.resolve(this); } };
      const fonts = [];
      w.document.fonts = { add: f => fonts.push(f), load: () => Promise.resolve([]), ready: Promise.resolve(), [Symbol.iterator]: () => fonts[Symbol.iterator]() };
      w.HTMLImageElement.prototype.decode = function () { return Promise.resolve(); };
      const size = el => { for (let e = el; e && e.style; e = e.parentElement) { const v = parseFloat(e.style.fontSize); if (v) return v; } return 40; };
      Object.defineProperty(w.HTMLElement.prototype, 'offsetWidth', { get() {
        const fixed = parseFloat(this.style.width); if (fixed) return fixed;
        return Math.round((this.textContent || '').length * size(this) * 0.56); } });
      Object.defineProperty(w.HTMLElement.prototype, 'offsetHeight', { get() {
        const fixed = parseFloat(this.style.height); if (fixed) return fixed;
        return Math.round(size(this) * 1.2 * Math.max(1, this.querySelectorAll('.hl-line').length)); } });
    },
  });
  const w = dom.window;
  await new Promise(r => w.addEventListener('load', r));
  if (!w.SCENE_READY) errors.push('no SCENE_READY');
  else {
    await w.SCENE_READY;
    if (typeof w.setFrame !== 'function') errors.push('no setFrame');
    else for (let n = 0; n < w.FRAMES; n++) { try { await w.setFrame(n); } catch (e) { errors.push(`frame ${n}: ${e.stack}`); break; } }
  }
  w.close();
  return errors;
}

(async () => {
  let bad = 0, ok = 0;
  for (const f of scenes) {
    for (const [format, decor, logo] of [['landscape', 'none', false], ['portrait', 'none', false], ['landscape', 'shapes', true], ['portrait', 'float', true]]) {
      const errors = await run(f, { example: true, format }, brand(decor, logo), f === 'keyword.html');
      if (errors.length) { bad++; console.log(`BAD ${f} ${format} ${decor}: ${errors.join(' | ').slice(0, 800)}`); } else ok++;
    }
  }
  console.log(`scenes ok ${ok}, bad ${bad}`);
  process.exit(bad ? 1 : 0);
})();

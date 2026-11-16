#!/usr/bin/env node
// Portrait capture for Crewcut's Shorts (crewcut/render/capture.py): records a page frame by frame as PNG files.
//
// Usage: node tools/capture_page.js <url> <out_dir> --frames N [--fps 25] [--width 1080 --height 1920] [--zoom 2.5]
//                                   [--scroll '[[0,0],[1.5,0],[6,"end"]]'] [--wait 1.5] [--hide-overlays] [--strict]
//   <url>            http(s):// or file:// address.
//   --frames N       number of frames (0 ... N-1); the video is N / fps seconds long.
//   --zoom Z         the page gets a viewport of width/Z x height/Z CSS pixels at device scale Z (2.5 gives 432 x 768,
//                    a phone): it lays out like on a phone, every text is Z times bigger, screenshots are width x height.
//   --scroll keys    [[second, position], ...]; position: CSS pixels from the top, "end" (bottom of the page) or "40%"
//                    (of the scrollable height). Between keys the page eases in and out, rounded to whole device
//                    pixels, so the motion stays calm. Without keys the page stands still.
//   --wait S         seconds after loading before the first frame (lazy images, entrance animations).
//   --hide-overlays  hides dialogs and fixed layers that cover more than a quarter of the screen (cookie banners).
//   --strict         a page error fails the run (for Crewcut's own pages, such as the terminal page).
// A page with window.setFrame(n) (Crewcut's own pages) is driven by it frame by frame; it does not scroll.
// Time: a screenshot takes longer than a frame. So the page's JavaScript clock (Date, timers, requestAnimationFrame)
// is paused and advanced one frame per screenshot, CSS animations are slowed to the measured capture speed, and
// <video> elements are paused and set to each frame's time. Then the video plays at the page's own speed.
// Output: <out_dir>/0000.png, 0001.png, ... and one JSON line on stdout (title, address, scroll, warnings).
// playwright-core comes from tools/node_modules or NODE_PATH; Chromium from env CHROMIUM_PATH when set.
'use strict';
const path = require('path'), fs = require('fs');
const FLAGS = new Set(['hide-overlays', 'strict', 'help']);
const USAGE = 'Usage: node tools/capture_page.js <url> <out_dir> --frames N [--fps 25] [--width 1080 --height 1920] ' +
  '[--zoom 2.5] [--scroll JSON] [--wait 1.5] [--hide-overlays] [--strict]';

function fail(code, msg) { console.error(msg); process.exit(code); }
function parse(argv) {
  const pos = [], opt = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const k = a.slice(2);
      if (FLAGS.has(k)) opt[k] = true;
      else { if (i + 1 >= argv.length) fail(2, `--${k} needs a value\n${USAGE}`); opt[k] = argv[++i]; }
    } else pos.push(a);
  }
  return { pos, opt };
}
function num(v, name, min) {
  const n = Number(v);
  if (!Number.isFinite(n) || n < min) fail(2, `--${name} must be a number of at least ${min}, got ${v}`);
  return n;
}
function chromium() {
  for (const name of ['playwright-core', 'playwright']) {
    try { return require(name).chromium; } catch (e) { if (e.code !== 'MODULE_NOT_FOUND') throw e; }
  }
  fail(1, 'playwright-core not found. Run "npm ci" in tools/ or set NODE_PATH to a node_modules folder that has it.');
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ease = x => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);

const { pos, opt } = parse(process.argv.slice(2));
if (opt.help || pos.length < 2 || opt.frames == null) fail(2, USAGE);
const target = pos[0], out = path.resolve(pos[1]);
if (!/^(https?|file):\/\//.test(target)) fail(2, 'The page must be an http(s):// or file:// address, got ' + target);
const N = Math.round(num(opt.frames, 'frames', 1));
const fps = Math.round(num(opt.fps || 25, 'fps', 1));
const W = Math.round(num(opt.width || 1080, 'width', 16)), H = Math.round(num(opt.height || 1920, 'height', 16));
const zoom = num(opt.zoom || 2.5, 'zoom', 0.25), wait = num(opt.wait == null ? 1.5 : opt.wait, 'wait', 0);
let keys = [];
if (opt.scroll) {
  try { keys = JSON.parse(opt.scroll); } catch (e) { fail(2, '--scroll is not valid JSON: ' + e.message); }
  const okPos = p => (typeof p === 'number' && p >= 0) || p === 'end' || (typeof p === 'string' && /^\d+(\.\d+)?%$/.test(p));
  if (!Array.isArray(keys) || !keys.every((k, i) => Array.isArray(k) && k.length === 2 && typeof k[0] === 'number' &&
      k[0] >= 0 && (i === 0 || k[0] >= keys[i - 1][0]) && okPos(k[1])))
    fail(2, '--scroll must be [[second, position], ...] with rising seconds; position: pixels, "end" or "40%"');
}

// Position at second t, from the keys resolved to pixels.
function scrollAt(t, ys) {
  if (t <= keys[0][0]) return ys[0];
  for (let i = 0; i < keys.length - 1; i++) {
    const ta = keys[i][0], tb = keys[i + 1][0];
    if (t <= tb) return ys[i] + (ys[i + 1] - ys[i]) * ease((t - ta) / Math.max(1e-6, tb - ta));
  }
  return ys[ys.length - 1];
}

// In the page: hide dialogs and fixed or sticky layers that cover more than a quarter of the screen.
function hideOverlays() {
  const vw = innerWidth, vh = innerHeight;
  let n = 0;
  for (const e of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(e);
    const modal = e.getAttribute('role') === 'dialog' || e.getAttribute('aria-modal') === 'true';
    let big = false;
    if (cs.position === 'fixed' || cs.position === 'sticky') {
      const r = e.getBoundingClientRect();
      big = r.width * r.height > vw * vh * 0.25;
    }
    if (modal || big) { e.style.setProperty('display', 'none', 'important'); n++; }
  }
  for (const e of [document.documentElement, document.body]) if (e) e.style.setProperty('overflow', 'auto', 'important');
  return n;
}

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium().launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    // --disable-dev-shm-usage: Docker's small /dev/shm crashes Chromium on big pages. CREWCUT_CHROMIUM_ARGS adds flags,
    // e.g. "--no-zygote --single-process --disable-gpu" under CPU emulation (QEMU) in CI.
    args: ['--force-color-profile=srgb', '--disable-dev-shm-usage', '--hide-scrollbars',
      ...(process.env.CREWCUT_CHROMIUM_ARGS || '').split(/\s+/).filter(Boolean)],
  });
  const close = async (code, msg) => { if (msg) console.error(msg); await browser.close().catch(() => {}); process.exit(code); };
  const ctx = await browser.newContext({ viewport: { width: Math.round(W / zoom), height: Math.round(H / zoom) },
    deviceScaleFactor: zoom, locale: 'en-US', colorScheme: 'light' });
  const page = await ctx.newPage();
  const warnings = [], errors = [];
  page.on('pageerror', e => errors.push('Page error: ' + String(e).slice(0, 300)));
  page.on('console', m => { if (m.type() === 'error') warnings.push('Console error: ' + m.text().slice(0, 300)); });
  let clock = true;
  try { await ctx.clock.install(); } catch (e) { clock = false; warnings.push('JavaScript clock not controlled: ' + e.message); }
  let resp = null;
  try { resp = await page.goto(target, { waitUntil: 'load', timeout: 60000 }); }
  catch (e) { await close(1, `Page not loaded: ${target} (${e.message})`); }
  if (resp && resp.status() >= 400) await close(1, `Page answered ${resp.status()}: ${target}`);
  await page.evaluate(() => document.fonts.ready.then(() => true));
  const own = await page.evaluate(() => typeof window.setFrame === 'function');
  if (own) await page.evaluate(() => window.SCENE_READY || null);
  if (opt.strict && errors.length) await close(1, errors.join('\n'));
  await page.addStyleTag({ content: 'html,body{scroll-behavior:auto !important}' }).catch(() => {});
  let hidden = 0;
  if (opt['hide-overlays'] && !own) hidden = await page.evaluate(hideOverlays);
  if (!own && keys.length) {
    // Walk down the page once in real time so lazy content loads, then back to the top.
    await page.evaluate(async () => {
      const step = Math.max(200, innerHeight * 0.8);
      for (let y = 0, i = 0; y < document.documentElement.scrollHeight && i < 60; y += step, i++) {
        window.scrollTo(0, y); await new Promise(r => setTimeout(r, 80));
      }
      window.scrollTo(0, 0);
    });
  }
  await sleep(wait * 1000);
  if (opt['hide-overlays'] && !own) hidden += await page.evaluate(hideOverlays);    // late banners
  const ys = own || !keys.length ? [] : await page.evaluate(keys => {
    const max = Math.max(0, document.documentElement.scrollHeight - innerHeight);
    return keys.map(([, p]) => {
      const y = typeof p === 'number' ? p : (p === 'end' ? max : max * parseFloat(p) / 100);
      return Math.max(0, Math.min(max, y));
    });
  }, keys);
  if (clock) {
    try { const now = await page.evaluate(() => Date.now()); await ctx.clock.pauseAt(now + 50); }
    catch (e) { clock = false; warnings.push('JavaScript clock not paused: ' + e.message); }
  }
  let cdp = null;
  if (!own) {
    try { cdp = await ctx.newCDPSession(page); await cdp.send('Animation.enable'); }
    catch (e) { cdp = null; warnings.push('CSS animations not slowed: ' + e.message); }
  }
  const frameMs = 1000 / fps;
  let rate = 1;
  const setRate = async perFrameMs => {
    // CSS time runs on the wall clock: slow it to the measured capture speed
    rate = Math.max(0.01, Math.min(1, frameMs / Math.max(1, perFrameMs)));
    await cdp.send('Animation.setPlaybackRate', { playbackRate: rate }).catch(() => {});
  };
  if (cdp) {                                  // three trial screenshots measure the speed before the first frame
    const t0 = Date.now();
    for (let i = 0; i < 3; i++) await page.screenshot({ type: 'png' });
    await setRate((Date.now() - t0) / 3 * 1.1);
  }
  const started = Date.now();
  for (let n = 0; n < N; n++) {
    const t = n / fps;
    if (clock && n > 0) await ctx.clock.runFor(Math.round(n * frameMs) - Math.round((n - 1) * frameMs));
    if (own) await page.evaluate(n => window.setFrame(n), n);
    else {
      if (ys.length) {
        const y = Math.round(scrollAt(t, ys) * zoom) / zoom;
        await page.evaluate(y => window.scrollTo({ top: y, left: 0, behavior: 'instant' }), y);
      }
      // videos on the page show the frame's time; a seek that does not finish in 400 ms is left as it is
      await Promise.race([sleep(400), page.evaluate(async t => {
        await Promise.all([...document.querySelectorAll('video')].map(v => new Promise(done => {
          if (v.dataset.crewcutT0 === undefined) v.dataset.crewcutT0 = String(v.currentTime || 0);
          v.pause();
          let want = parseFloat(v.dataset.crewcutT0) + t;
          if (v.duration) want = v.loop ? want % v.duration : Math.min(want, v.duration);
          if (Math.abs(v.currentTime - want) < 0.001) return done();
          v.addEventListener('seeked', done, { once: true });
          v.currentTime = want;
        })));
      }, t)]);
    }
    await page.screenshot({ path: path.join(out, String(n).padStart(4, '0') + '.png'), type: 'png', caret: 'initial' });
    if (opt.strict && errors.length) await close(1, errors.join('\n'));
    if (cdp && n > 0 && n % 25 === 0) await setRate((Date.now() - started) / (n + 1));
  }
  const info = await page.evaluate(() => ({ title: document.title, url: location.href,
    scroll_height: document.documentElement.scrollHeight, viewport: [innerWidth, innerHeight] }));
  await browser.close();
  console.log(JSON.stringify({ ...info, frames: N, fps, size: `${W}x${H}`, zoom, own_frames: own, scroll_px: ys,
    clock, css_rate: Math.round(rate * 1000) / 1000, overlays_hidden: hidden,
    warnings: [...errors, ...warnings].slice(0, 50) }));
})().catch(e => { console.error(e && e.stack || String(e)); process.exit(1); });

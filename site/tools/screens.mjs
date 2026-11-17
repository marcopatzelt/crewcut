// Renders the built landing page at 1440, 1024, 768 and 390 px, light and dark: the whole page and the first screen.
// Runs on GitHub's runner only (.github/workflows/pages.yml), never on a developer laptop.
//
//   node screens.mjs <url of site/_site/index.html> <output folder>
//
// Reduced motion is on, so every shot shows the finished state: the hero standing, the statement in full ink, the
// meadow's poster. A second pass at 1440 and 390 px turns motion on and shoots the meadow loops while they play.
// The page is scrolled through once first, so the lazy app window has loaded before the full-page shot.
import { mkdirSync } from 'node:fs';
import { chromium } from 'playwright';

const [url, out] = process.argv.slice(2);
if (!url || !out) { console.error('usage: node screens.mjs <url> <output folder>'); process.exit(2); }
mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
for (const scheme of ['light', 'dark']) {
  for (const [w, h] of [[1440, 900], [1024, 768], [768, 1024], [390, 844]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, colorScheme: scheme, reducedMotion: 'reduce' });
    const page = await ctx.newPage();
    await page.goto(url, { waitUntil: 'networkidle' });
    await page.evaluate(async () => {
      await document.fonts.ready;
      for (let y = 0; y < document.documentElement.scrollHeight; y += innerHeight / 2) { scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); }
      scrollTo(0, 0);
      await Promise.all([...document.images].map(i => i.complete ? null : new Promise(r => { i.onload = i.onerror = r; })));
    });
    await page.waitForTimeout(600);
    await page.screenshot({ path: `${out}/site-${w}-${scheme}.png`, fullPage: true });
    await page.screenshot({ path: `${out}/site-${w}-${scheme}-first-screen.png` });
    const height = await page.evaluate(() => document.documentElement.scrollHeight);
    console.log(`site-${w}-${scheme}.png: ${w} x ${height} px (${(height / h).toFixed(2)} screens)`);
    await ctx.close();
  }
}
// The meadow loops with motion on (hero and close, 1440 and 390 px): the first screen and the close once the video
// plays over the poster, and one line per loop with the file it chose and how far it played.
for (const scheme of ['light', 'dark']) {
  for (const [w, h] of [[1440, 900], [390, 844]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1, colorScheme: scheme, reducedMotion: 'no-preference' });
    const page = await ctx.newPage();
    await page.goto(url, { waitUntil: 'load' });
    const state = (sel) => page.evaluate((s) => { const v = document.querySelector(s); return v ? { src: (v.currentSrc || '').split('/').pop(), on: v.classList.contains('is-on'), t: +v.currentTime.toFixed(2), ready: v.readyState } : null; }, sel);
    const playing = (sel) => page.waitForFunction((s) => { const v = document.querySelector(s); return v && v.classList.contains('is-on') && v.currentTime > 0.5; }, sel, { timeout: 20000 }).then(() => true, () => false);
    await page.evaluate(() => document.fonts.ready);
    await playing('.meadow--hero video');
    await page.screenshot({ path: `${out}/site-${w}-${scheme}-motion.png` });
    console.log(`motion ${w} ${scheme} hero: ${JSON.stringify(await state('.meadow--hero video'))}`);
    await page.evaluate(() => document.getElementById('start').scrollIntoView({ block: 'end' }));
    await playing('.meadow--foot video');
    await page.waitForTimeout(2600);   // the finger trail through the fog takes 2.2 s
    await page.screenshot({ path: `${out}/site-${w}-${scheme}-close-motion.png` });
    console.log(`motion ${w} ${scheme} close: ${JSON.stringify(await state('.meadow--foot video'))}`);
    await ctx.close();
  }
}
await browser.close();

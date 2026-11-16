/* Crewcut landing page: the little motion that CSS cannot do alone. Own code, no library.
   Everything starts at load; nothing waits for the scroll. One button pauses all motion;
   prefers-reduced-motion keeps the fog still and the drum where it is. */
(function () {
  const root = document.documentElement;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let paused = false;

  // one button pauses every animation on the page (WCAG 2.2.2) and plays it again
  for (const b of document.querySelectorAll("[data-pause]")) {
    b.addEventListener("click", () => {
      paused = !paused;
      root.classList.toggle("is-paused", paused);
      for (const x of document.querySelectorAll("[data-pause]")) {
        x.setAttribute("aria-pressed", String(paused));
        x.textContent = paused ? "Play motion" : "Pause motion";
      }
    });
  }

  // the drum also turns with the scroll
  const tilt = document.getElementById("tilt");
  if (tilt && !reduce) {
    addEventListener("scroll", () => { if (!paused) tilt.style.setProperty("--scroll-turn", (scrollY * -0.12) + "deg"); }, { passive: true });
  }

  // the closing section: condensation on glass over the landscape. A blurred copy of the wallpaper with drops is
  // painted on a canvas; the pointer wipes it away, and the glass slowly fogs up again.
  const sec = document.getElementById("start"), cv = document.getElementById("mist"), img = document.getElementById("finalbg");
  if (!sec || !cv || !img || !cv.getContext) return;
  const ctx = cv.getContext("2d");
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  if (dark && img.dataset.dark) img.src = img.dataset.dark;
  const word = sec.querySelector(".final__word");
  let W = 0, H = 0, dpr = Math.min(devicePixelRatio || 1, 2), fogged = null;
  const cover = (iw, ih) => { const s = Math.max(W / iw, H / ih); return [(W - iw * s) / 2, (H - ih * s) / 2, iw * s, ih * s]; };
  function paintFog(alpha) {
    if (!fogged) return;
    ctx.save(); ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = alpha; ctx.drawImage(fogged, 0, 0, W, H); ctx.restore();
  }
  function buildFog() {
    const off = document.createElement("canvas"); off.width = W; off.height = H;
    const o = off.getContext("2d");
    o.filter = "blur(" + Math.round(22 * dpr) + "px) saturate(0.75) brightness(1.12)";
    const [x, y, w, h] = cover(img.naturalWidth, img.naturalHeight);
    o.drawImage(img, x - 40, y - 40, w + 80, h + 80);
    if (word) {
      const fs = parseFloat(getComputedStyle(word).fontSize) * dpr, wr = word.getBoundingClientRect(), sr = sec.getBoundingClientRect();
      o.filter = "blur(" + Math.round(10 * dpr) + "px)"; o.fillStyle = "rgba(255,255,255,0.9)";
      o.font = "900 " + fs + "px 'Inter Tight', Inter, sans-serif"; o.textAlign = "center"; o.textBaseline = "bottom";
      o.fillText("Crewcut", W / 2, (wr.bottom - sr.top) * dpr);
    }
    o.filter = "none"; o.fillStyle = dark ? "rgba(190,225,215,0.16)" : "rgba(235,248,243,0.28)"; o.fillRect(0, 0, W, H);
    let seed = 11; const r = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < 2600; i++) {
      const px = r() * W, py = r() * H, rad = (0.6 + r() * r() * 3.2) * dpr;
      o.beginPath(); o.arc(px, py, rad, 0, 7); o.fillStyle = "rgba(255,255,255," + (0.18 + r() * 0.3) + ")"; o.fill();
      o.beginPath(); o.arc(px + rad * 0.3, py + rad * 0.35, rad * 0.7, 0, 7); o.fillStyle = "rgba(0,20,15,0.12)"; o.fill();
    }
    fogged = off;
  }
  function size() { W = Math.round(sec.clientWidth * dpr); H = Math.round(sec.clientHeight * dpr); cv.width = W; cv.height = H; buildFog(); paintFog(1); }
  function wipe(x, y, rad) {
    ctx.save(); ctx.globalCompositeOperation = "destination-out";
    const g = ctx.createRadialGradient(x, y, 0, x, y, rad);
    g.addColorStop(0, "rgba(0,0,0,1)"); g.addColorStop(0.65, "rgba(0,0,0,0.9)"); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, rad, 0, 7); ctx.fill(); ctx.restore();
  }
  sec.addEventListener("pointermove", (e) => { const b = cv.getBoundingClientRect(); wipe((e.clientX - b.left) * dpr, (e.clientY - b.top) * dpr, 70 * dpr); });
  let t0 = 0;
  function frame(t) {
    // a finger trail draws through the word right away, so the glass is alive from the first frame
    const k = (t - t0) / 2200;
    if (k < 1) for (let j = 0; j < 4; j++) { const kk = Math.min(1, k + j * 0.004); wipe(W * (0.12 + 0.76 * kk), H * (0.80 - 0.08 * Math.sin(kk * 3.1)), 42 * dpr); }
    if (!reduce && !paused) paintFog(0.0016);
    requestAnimationFrame(frame);
  }
  function start() { (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => { size(); t0 = performance.now(); requestAnimationFrame(frame); }); }
  if (img.complete && img.naturalWidth) start(); else img.addEventListener("load", start, { once: true });
  addEventListener("resize", () => { if (Math.round(sec.clientWidth * dpr) !== W) size(); });
})();

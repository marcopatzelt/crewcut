/* Crewcut landing page: the launch film in #film, the meadow loops of the hero and the close, and the fogged glass of
   the close. Own code, no library. */
/* The launch film (#film): loads when it comes within 200 px of the view, plays muted in a loop, pauses when it
   leaves. Sound only on the button (the first time it starts the film from the beginning). With reduced motion
   it never starts by itself: the poster and the Play button. Without this script the video keeps its own controls. */
(function () {
  const v = document.getElementById("film-video");
  const ctl = document.querySelector(".film__ctl");
  const play = document.getElementById("film-play"), sound = document.getElementById("film-sound");
  if (!v || !ctl || !play || !sound) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  v.removeAttribute("controls"); v.muted = true; ctl.hidden = false;
  let near = false, userPaused = reduce, unmutedOnce = false;
  const show = () => { play.textContent = v.paused ? "Play" : "Pause"; sound.setAttribute("aria-pressed", String(!v.muted)); };
  const start = () => { if (v.preload !== "auto") v.preload = "auto"; const p = v.play(); if (p && p.catch) p.catch(show); };
  v.addEventListener("play", show); v.addEventListener("pause", show); v.addEventListener("volumechange", show);
  play.addEventListener("click", () => { if (v.paused) { userPaused = false; start(); } else { userPaused = true; v.pause(); } });
  sound.addEventListener("click", () => {
    v.muted = !v.muted;
    if (!v.muted && !unmutedOnce) { unmutedOnce = true; v.currentTime = 0; }
    if (!v.muted && v.paused) { userPaused = false; start(); }
    show();
  });
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((es) => {
      for (const e of es) {
        near = e.isIntersecting;
        if (near && !userPaused) start(); else if (!near && !v.paused) v.pause();
      }
    }, { rootMargin: "200px 0px" }).observe(v);
  } else if (!reduce) { start(); }
  show();
})();

/* The meadow (hero and close): the poster paints first. Once the page has loaded, a seamless 8 s loop of the web
   meadow (rendered for the page at 3840 x 2160, the same in light and dark mode) fades in over it. AV1 where the
   browser plays it (3840 px when the screen needs it, else 2560), else H.264 at 2560; phones get a 1080 x 1920 crop.
   Each loop plays only while it is near the view. With reduced motion or Save-Data nothing loads and the poster stays.
   A change of width or motion setting is followed at once. */
(function () {
  const layers = Array.from(document.querySelectorAll(".meadow"));
  const probe = document.createElement("video");
  if (!layers.length || !probe.canPlayType) return;
  const can = (t) => probe.canPlayType(t) !== "";
  const av1 = can('video/mp4; codecs="av01.0.12M.08"'), avc = can('video/mp4; codecs="avc1.640032"');
  if (!av1 && !avc) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)"), phone = matchMedia("(max-width: 760px)");
  const saveData = !!(navigator.connection && navigator.connection.saveData);
  // the hero's meadow covers about 1.45 times the window's width; 3840 px only where that many device pixels show
  const size = () => phone.matches ? "phone" : av1 && innerWidth * 1.45 * (devicePixelRatio || 1) > 2700 ? "3840" : "2560";
  const url = () => new URL("media/meadow/meadow-day-" + size() + (av1 ? ".av1" : ".h264") + ".mp4", document.baseURI).href;
  const loops = layers.map((el) => ({ el, v: el.querySelector("video"), near: false })).filter((l) => l.v);
  let ready = false;
  function apply(l) {
    const v = l.v;
    if (reduce.matches || saveData) { v.classList.remove("is-on"); if (!v.paused) v.pause(); return; }
    if (!l.near) { if (!v.paused) v.pause(); return; }
    const want = url();
    if (v.src !== want) { v.classList.remove("is-on"); v.src = want; }
    v.muted = true;
    const p = v.play(); if (p && p.catch) p.catch(() => {});
  }
  loops.forEach((l) => l.v.addEventListener("playing", () => l.v.classList.add("is-on")));
  const all = () => { if (ready) loops.forEach(apply); };
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver((es) => {
      for (const e of es) { const l = loops.find((x) => x.el === e.target); if (l) { l.near = e.isIntersecting; if (ready) apply(l); } }
    }, { rootMargin: "200px 0px" });
    loops.forEach((l) => io.observe(l.el));
  } else loops.forEach((l) => { l.near = true; });
  [reduce, phone].forEach((m) => { if (m.addEventListener) m.addEventListener("change", all); });
  const go = () => setTimeout(() => { ready = true; all(); }, 0);
  if (document.readyState === "complete") go(); else addEventListener("load", go, { once: true });
})();

/* The close: rain on a window that looks onto the meadow. The fog is the live meadow, blurred at a quarter of the
   canvas resolution about 30 times a second, with the big word "Crewcut" blurred into it, a pale wash and drops on
   top. A mask says where the glass is fogged: the pointer wipes it away (sharp word and live meadow behind), a finger
   trail runs through the word at the start, and the glass fogs up again slowly. It runs only while the close is near
   the view. With reduced motion the fog is built once from the poster and stays still (wiping still works). */
(function () {
  const sec = document.getElementById("start"), cv = document.getElementById("mist"), wordCv = document.getElementById("word");
  const layer = sec && sec.querySelector(".meadow--foot");
  if (!sec || !cv || !wordCv || !layer || !cv.getContext) return;
  const video = layer.querySelector("video"), poster = layer.querySelector("img"), foot = sec.querySelector(".foot");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)"), dark = matchMedia("(prefers-color-scheme: dark)");
  const ctx = cv.getContext("2d"), wctx = wordCv.getContext("2d");
  const mk = () => { const c = document.createElement("canvas"); return [c, c.getContext("2d")]; };
  const [fogC, fctx] = mk(), [maskC, mctx] = mk(), [dropsC, dctx] = mk(), [wordFogC, wfctx] = mk(), [tinyC, tctx] = mk();
  const S = 4;                                   // fog and mask at a quarter of the canvas resolution
  fctx.filter = "blur(1px)"; const hasFilter = fctx.filter === "blur(1px)"; fctx.filter = "none";
  let q = 1, W = 0, H = 0, w = 0, h = 0, fs = 0, base = 0, ready = false, near = false, queued = false, last = 0, ticks = 0, t0 = 0;
  const wash = () => "rgba(235,248,243,0.28)";        // the same daylight glass in light and dark mode
  function wordAt(c, k, blur, colour) {
    c.save(); c.filter = blur ? "blur(" + blur + "px)" : "none"; c.fillStyle = colour;
    c.font = "900 " + fs * k + "px 'Inter Tight', Inter, sans-serif"; c.textAlign = "center"; c.textBaseline = "alphabetic";
    if ("letterSpacing" in c) c.letterSpacing = (-0.06 * fs * k) + "px";
    c.fillText("Crewcut", W * k / 2, base * k); c.restore();
  }
  function source() {
    if (video && video.classList.contains("is-on") && video.readyState >= 2 && video.videoWidth) return [video, video.videoWidth, video.videoHeight];
    if (poster && poster.complete && poster.naturalWidth) return [poster, poster.naturalWidth, poster.naturalHeight];
    return null;
  }
  // the meadow's own framing: object-fit cover, object-position 50% 70%
  const cover = (iw, ih, cw, ch) => { const s = Math.max(cw / iw, ch / ih), dw = iw * s, dh = ih * s; return [(cw - dw) * 0.5, (ch - dh) * 0.7, dw, dh]; };
  function drawFog() {
    const src = source(); if (!src) return false;
    const [el, iw, ih] = src;
    fctx.globalCompositeOperation = "copy";
    if (hasFilter) {
      const [x, y, dw, dh] = cover(iw, ih, w, h), p = 8;
      fctx.filter = "blur(" + (22 * q / S).toFixed(1) + "px) saturate(0.75) brightness(1.12)";
      fctx.drawImage(el, x - p, y - p, dw + 2 * p, dh + 2 * p); fctx.filter = "none";
    } else {                                     // no canvas filter (older Safari): down to a tiny copy and back up
      const [x, y, dw, dh] = cover(iw, ih, tinyC.width, tinyC.height);
      tctx.drawImage(el, x, y, dw, dh); fctx.imageSmoothingQuality = "high"; fctx.drawImage(tinyC, 0, 0, w, h);
    }
    fctx.globalCompositeOperation = "source-over";
    fctx.drawImage(wordFogC, 0, 0);
    fctx.fillStyle = wash(); fctx.fillRect(0, 0, w, h);
    return true;
  }
  function compose() {
    ctx.globalCompositeOperation = "copy"; ctx.drawImage(fogC, 0, 0, W, H);
    ctx.globalCompositeOperation = "source-over"; ctx.drawImage(dropsC, 0, 0);
    ctx.globalCompositeOperation = "destination-in"; ctx.drawImage(maskC, 0, 0, W, H);
    ctx.globalCompositeOperation = "source-over";
  }
  function wipe(x, y, rad) {                     // canvas pixels in, mask pixels inside
    x /= S; y /= S; rad /= S;
    mctx.save(); mctx.globalCompositeOperation = "destination-out";
    const gr = mctx.createRadialGradient(x, y, 0, x, y, rad);
    gr.addColorStop(0, "rgba(0,0,0,1)"); gr.addColorStop(0.65, "rgba(0,0,0,0.9)"); gr.addColorStop(1, "rgba(0,0,0,0)");
    mctx.fillStyle = gr; mctx.beginPath(); mctx.arc(x, y, rad, 0, 7); mctx.fill(); mctx.restore();
  }
  // a finger trail through the word, so the glass is alive from the first look
  const trail = (k) => { for (let j = 0; j < 4; j++) { const kk = Math.min(1, k + j * 0.004); wipe(W * (0.12 + 0.76 * kk), base - fs * 0.32 - 0.06 * H * Math.sin(kk * 3.1), 42 * q); } };
  function size() {
    q = Math.min(devicePixelRatio || 1, 1.5);
    W = Math.round(sec.clientWidth * q); H = Math.round(sec.clientHeight * q); w = Math.ceil(W / S); h = Math.ceil(H / S);
    cv.width = wordCv.width = dropsC.width = W; cv.height = wordCv.height = dropsC.height = H;
    fogC.width = maskC.width = wordFogC.width = w; fogC.height = maskC.height = wordFogC.height = h;
    tinyC.width = Math.max(8, Math.round(w / 3)); tinyC.height = Math.max(8, Math.round(h / 3));
    // the word: as wide as the screen allows, standing on the footer row
    fs = Math.min(300, Math.max(104, sec.clientWidth * 0.21)) * q;
    const fr = foot ? foot.getBoundingClientRect() : null, sr = sec.getBoundingClientRect();
    base = fr ? (fr.top - sr.top) * q - 14 * q : H - 90 * q;
    wctx.clearRect(0, 0, W, H); wordAt(wctx, 1, 0, "rgba(255,255,255,0.94)");
    wfctx.clearRect(0, 0, w, h); wordAt(wfctx, 1 / S, 10 * q / S, "rgba(255,255,255,0.9)");
    dctx.clearRect(0, 0, W, H);
    let seed = 11; const r = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    for (let i = 0; i < 2600; i++) {
      const px = r() * W, py = r() * H, rad = (0.6 + r() * r() * 3.2) * q;
      dctx.beginPath(); dctx.arc(px, py, rad, 0, 7); dctx.fillStyle = "rgba(255,255,255," + (0.18 + r() * 0.3) + ")"; dctx.fill();
      dctx.beginPath(); dctx.arc(px + rad * 0.3, py + rad * 0.35, rad * 0.7, 0, 7); dctx.fillStyle = "rgba(0,20,15,0.12)"; dctx.fill();
    }
    mctx.globalCompositeOperation = "source-over"; mctx.fillStyle = "#000"; mctx.fillRect(0, 0, w, h);
    t0 = performance.now(); ticks = 0;
    if (reduce.matches) { for (let k = 0; k <= 1; k += 0.01) trail(k); still(); }
  }
  function still() { if (drawFog()) compose(); }
  function tick(t) {
    queued = false;
    if (!ready || !near || document.hidden || reduce.matches) return;
    if (t - last >= 32) {                        // about 30 times a second, the loop's own frame rate
      last = t;
      const k = (t - t0) / 2200;
      if (k < 1) trail(k);
      if (++ticks % 6 === 0) { mctx.globalCompositeOperation = "source-over"; mctx.fillStyle = "rgba(0,0,0,0.02)"; mctx.fillRect(0, 0, w, h); }
      if (drawFog()) compose();
    }
    run();
  }
  function run() { if (!queued && ready && near && !reduce.matches && !document.hidden) { queued = true; requestAnimationFrame(tick); } }
  sec.addEventListener("pointermove", (e) => {
    if (!ready) return;
    const b = cv.getBoundingClientRect(); wipe((e.clientX - b.left) * q, (e.clientY - b.top) * q, 70 * q);
    if (reduce.matches) compose();
  });
  let started = false;
  function start() {
    if (started) return; started = true;
    (document.fonts ? document.fonts.ready : Promise.resolve()).then(() => { size(); ready = true; run(); });
  }
  if ("IntersectionObserver" in window) {
    new IntersectionObserver((es) => { for (const e of es) { near = e.isIntersecting; if (near) { start(); run(); } } }, { rootMargin: "300px 0px" }).observe(sec);
  } else { near = true; start(); }
  if (poster) poster.addEventListener("load", () => { if (ready && reduce.matches) still(); });
  if (video) video.addEventListener("playing", () => { if (ready && reduce.matches) still(); });
  document.addEventListener("visibilitychange", run);
  [reduce, dark].forEach((m) => { if (m.addEventListener) m.addEventListener("change", () => { if (!ready) return; size(); run(); }); });
  addEventListener("resize", () => { if (ready && Math.round(sec.clientWidth * Math.min(devicePixelRatio || 1, 1.5)) !== W) { size(); run(); } });
})();

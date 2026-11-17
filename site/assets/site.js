/* Crewcut landing page: the launch film in #film and the meadow loops of the hero and the close. Own code, no library. */
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

/* The meadow (hero and close): the poster paints first. Once the page has loaded, an 8 s loop of the launch film's
   meadow fades in over it: day in light mode, dusk in dark mode, a 540 x 960 crop on phones, VP9 WebM where the
   browser plays it, else H.264 MP4. Each loop plays only while it is near the view. With reduced motion or Save-Data
   nothing loads and the poster stays. A change of colour scheme, width or motion setting is followed at once. */
(function () {
  const layers = Array.from(document.querySelectorAll(".meadow"));
  const probe = document.createElement("video");
  if (!layers.length || !probe.canPlayType) return;
  const ext = probe.canPlayType('video/webm; codecs="vp9"') ? "webm" : probe.canPlayType('video/mp4; codecs="avc1.640028"') ? "mp4" : "";
  if (!ext) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)"), dark = matchMedia("(prefers-color-scheme: dark)"), phone = matchMedia("(max-width: 760px)");
  const saveData = !!(navigator.connection && navigator.connection.saveData);
  const url = () => new URL("media/meadow/meadow-" + (dark.matches ? "dusk" : "day") + "-" + (phone.matches ? "phone" : "1920") + "." + ext, document.baseURI).href;
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
  [reduce, dark, phone].forEach((m) => { if (m.addEventListener) m.addEventListener("change", all); });
  const go = () => setTimeout(() => { ready = true; all(); }, 0);
  if (document.readyState === "complete") go(); else addEventListener("load", go, { once: true });
})();

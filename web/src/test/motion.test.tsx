// Motion graphics in the web UI: the four motion cards (render, the strike call, accessible names), the motion tiles
// on the film strip and the motion panel of an episode, the Motion shelf of the style pack, and the sample data.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { Card, EpisodeMedia, EpisodeMotion, MotionPlanData, ShelfRow } from "../api/types";
import { acceptLabel, foldedText } from "../components/CardView";
import { moneyWords, pieceName } from "../components/Motion";
import { createSampleBackend } from "../../../tests/web-sample/backend";
import { setBackend } from "../api/client";
import { card, episode, episodeRoutes, mockApi, openAt, Reply, resetApp, state } from "./helpers";

beforeEach(() => resetApp());
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const ep = episode({ id: "003-local-ai", title: "Local AI, privately", step: "edit", open_cards: 1 });

function plan(over: Partial<MotionPlanData> = {}): MotionPlanData {
  return {
    version: 2,
    file: "edit/motion-plan-v002.json",
    md: "edit/motion-plan-v002.md",
    json_sha256: "abc",
    columns: {
      a: [
        {
          row: "beat:2",
          beat: 2,
          time: "0:06",
          purpose: "believe the price",
          picture: "the price rolls and lands on thirty as the word is said",
          piece: "number_roll",
          params: { value: "30", unit: "cents" },
          length_s: 3.6,
          cost_usd: 0,
          media: { loop: "/api/motion/app/samples/number_roll-v2-landscape.mp4", poster: "/api/motion/app/samples/number_roll-v2.jpg" },
          struck: false,
        },
        {
          row: "beat:5",
          beat: 5,
          time: "0:40",
          purpose: "remember the name",
          picture: "the name with a line under it",
          piece: "lower_third",
          params: {},
          length_s: 2,
          cost_usd: 0,
          media: { loop: null, poster: null },
          struck: true,
        },
      ],
      b: [
        {
          row: "new:handoff",
          id: "handoff",
          beat: 3,
          brief: "Four jobs leave the laptop for a rented GPU.",
          why_new: "No shelf piece shows work moving between machines.",
          kind: "full",
          plates: 1,
          effort: "M",
          cost_usd: 0.3,
          cap_usd: 1,
          struck: false,
          beats: [{ row: "beat:3", beat: 3, time: "0:12", purpose: "see the hand-off", picture: "four jobs leave", piece: "handoff", length_s: 5, struck: false }],
        },
      ],
      c: [
        {
          row: "upgrade:u1",
          id: "u1",
          upgrade: "Every exit from a full-frame piece is caused by a motion",
          source: { kind: "lesson", ref: "2026-11-17-3" },
          effort: "S",
          cost_usd: 0,
          chosen: true,
          struck: false,
          beats: [],
        },
        {
          row: "upgrade:u2",
          id: "u2",
          upgrade: "A pricing table as a custom comparison",
          source: { kind: "baseline", ref: "002-local-ai" },
          effort: "M",
          cost_usd: 0,
          chosen: false,
          struck: false,
          beats: [],
        },
      ],
    },
    quiet: [{ row: "beat:1", beat: 1, time: "0:00", purpose: "know what this is", picture: "the speaker alone", struck: false }],
    density: "full-frame 2 of max 5 · all motion 3 in 6:10 (max 12) · heroes 0",
    budget: "GPU about $0.30, cap $2",
    estimate_usd: 0.3,
    cap_usd: 2,
    bar: "002-local-ai",
    short: false,
    ...over,
  };
}

function planCard(over: Partial<Card> = {}, p: MotionPlanData = plan()): Card {
  return card({
    id: 12,
    episode: ep.id,
    step: "edit",
    kind: "motion-plan",
    identity: "editor",
    title: "Motion plan v002: 2 motion moments",
    body: "full-frame 2 of max 5 · … Tap a row to strike it.",
    options: null,
    file: "edit/motion-plan-v002.md",
    sha256: "aaaa1111",
    data: { motion_plan: p, cap_usd: p.cap_usd, images: [] },
    ...over,
  });
}

function openCardIn(c: Card, extra: Record<string, unknown> = {}) {
  const calls = mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], [c]), ...extra });
  openAt(ep.id);
  render(<App />);
  return calls;
}

/** prefers-reduced-motion: reduce, for the posters-only case. */
function reduceMotion() {
  vi.stubGlobal(
    "matchMedia",
    (q: string) =>
      ({ matches: q.includes("prefers-reduced-motion"), media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} }) as unknown as MediaQueryList,
  );
}

describe("the motion-plan card", () => {
  it("shows the three columns as media, density and budget with the cap in one line, and one yes", async () => {
    openCardIn(planCard());
    const group = await screen.findByRole("group", { name: "Motion plan v002: 2 motion moments" });
    for (const h of ["What we have that fits", "What we build new for this video", "What makes this video clearly better than the last one"]) {
      expect(within(group).getByRole("heading", { level: 3, name: new RegExp(`^${h}`) })).toBeTruthy();
    }
    // (a) a loop of each shelf piece: muted, looping, decorative inside its named row
    const shelfRow = within(group).getByRole("button", { name: "Not this one: 0:06 Number roll, believe the price" });
    expect(shelfRow.getAttribute("aria-pressed")).toBe("false");
    const video = shelfRow.querySelector("video");
    expect(video?.muted).toBe(true);
    expect(video?.loop).toBe(true);
    expect(video?.getAttribute("src")).toBe("/api/motion/app/samples/number_roll-v2-landscape.mp4");
    // a struck row stays, pressed, and says so
    const struck = within(group).getByRole("button", { name: /^Not this one: 0:40 Lower third/ });
    expect(struck.getAttribute("aria-pressed")).toBe("true");
    expect(within(struck).getByText("Struck")).toBeTruthy();
    // (b) the brief's line, (c) the upgrade with its reason; an upgrade not chosen is not a row to strike
    expect(within(group).getByRole("button", { name: "Not this one: Four jobs leave the laptop for a rented GPU." })).toBeTruthy();
    expect(within(group).getByText(/0:12 · effort M · 1 plate · about \$0\.30 · cap \$1\.00/)).toBeTruthy();
    expect(within(group).getByText(/Lesson 2026-11-17-3 · effort S/)).toBeTruthy();
    expect(within(group).queryByRole("button", { name: /pricing table/ })).toBeNull();
    expect(within(group).getByText(/For a later video · Behind the bar/)).toBeTruthy();
    // density and budget in one line, with the cap per video
    expect(
      within(group).getByText("Full-frame 2 of max 5 · all motion 3 in 6:10 (max 12) · heroes 0 · GPU about $0.30, cap $2 for this video"),
    ).toBeTruthy();
    expect(within(group).getByText(/Without motion: 0:00\. Tap a row to strike it\. The bar is 002\./)).toBeTruthy();
    expect(within(group).getByRole("button", { name: "Build this motion plan" })).toBeTruthy();
    expect(within(group).getByRole("link", { name: "edit/motion-plan-v002.md" })).toBeTruthy();
    // the body repeats the plan's lines, so the card does not show it
    expect(within(group).queryByText(/Tap a row to strike it\.$/, { selector: ".card-body" })).toBeNull();
  });

  it("strikes a row with one tap and shows the next plan version in place", async () => {
    const before = planCard();
    const next = plan({ version: 3, file: "edit/motion-plan-v003.json" });
    next.columns.a[0] = { ...next.columns.a[0]!, struck: true };
    const after = planCard({ title: "Motion plan v003: 1 motion moment", file: "edit/motion-plan-v003.md", sha256: "bbbb2222" }, next);
    const calls = openCardIn(before, { "POST /api/cards/12/strike": after });
    const group = await screen.findByRole("group", { name: "Motion plan v002: 2 motion moments" });
    await userEvent.click(within(group).getByRole("button", { name: "Not this one: 0:06 Number roll, believe the price" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toEqual({
        method: "POST",
        path: "/api/cards/12/strike",
        body: { row: "beat:2", struck: true },
      }),
    );
    const updated = await screen.findByRole("group", { name: "Motion plan v003: 1 motion moment" });
    expect(within(updated).getByRole("button", { name: /^Not this one: 0:06 Number roll/ }).getAttribute("aria-pressed")).toBe("true");
    expect(within(updated).getByRole("link", { name: "edit/motion-plan-v003.md" })).toBeTruthy();
    expect(calls.some((c) => c.path.includes("/accept"))).toBe(false);
  });

  it("brings a struck row back with a second tap", async () => {
    const calls = openCardIn(planCard(), { "POST /api/cards/12/strike": planCard() });
    const group = await screen.findByRole("group", { name: "Motion plan v002: 2 motion moments" });
    await userEvent.click(within(group).getByRole("button", { name: /^Not this one: 0:40 Lower third/ }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ row: "beat:5", struck: false }),
    );
  });

  it("says why when the server refuses, without a retry that cannot help", async () => {
    const detail = "This is the only chosen upgrade, and every video needs one. Say in the chat which other upgrade to take instead.";
    openCardIn(planCard(), { "POST /api/cards/12/strike": new Reply(409, { detail }) });
    const group = await screen.findByRole("group", { name: "Motion plan v002: 2 motion moments" });
    await userEvent.click(within(group).getByRole("button", { name: /^Not this one: Every exit/ }));
    const alert = await within(group).findByRole("alert");
    expect(alert.textContent).toContain(`Couldn't strike this row. ${detail}`);
    expect(within(alert).queryByRole("button", { name: "Try again" })).toBeNull();
    expect(within(group).getByRole("button", { name: /^Not this one: Every exit/ }).getAttribute("aria-pressed")).toBe("false");
  });

  it("shows the cap of a Short and no tappable rows once decided", () => {
    expect(moneyWords({ estimate_usd: 0, cap_usd: 0.5, budget: null, short: true })).toBe("No GPU money, cap $0.50 for this Short");
    expect(moneyWords({ estimate_usd: 0.3, cap_usd: 2, budget: null, short: false })).toBe("GPU about $0.30, cap $2 for this video");
    expect(pieceName("gpu_handoff@1")).toBe("Gpu handoff");
    const decided = planCard({ status: "accepted" });
    expect(foldedText(decided)).toBe("Motion plan approved · version 2");
    expect(acceptLabel(decided)).toBe("Build this motion plan");
  });
});

const frameCard = card({
  id: 20,
  episode: ep.id,
  step: "edit",
  kind: "style-frame",
  identity: "designer",
  title: "Style frame of m3, round 1",
  body: "Our frame of the strongest moment next to the reference, per format.",
  options: null,
  file: "motion/m3/frame-v1-landscape.png",
  data: {
    insert: "m3",
    round: 1,
    frames: [
      {
        format: "landscape",
        ours: "motion/m3/frame-v1-landscape.png",
        ours_url: "/api/files/003-local-ai/motion/m3/frame-v1-landscape.png",
        ref: "motion/m3/refs/reel.png",
        ref_url: "/api/files/003-local-ai/motion/m3/refs/reel.png",
        ref_label: "reference",
        hue: { dominant_share: 0.24, ok: true },
      },
      {
        format: "portrait",
        ours: "motion/m3/frame-v1-portrait.png",
        ours_url: "/api/files/003-local-ai/motion/m3/frame-v1-portrait.png",
        ref: null,
        ref_url: null,
        ref_label: "no reference: say what it should beat",
        hue: { dominant_share: 0.28, ok: true },
      },
    ],
  },
});

describe("the style-frame card", () => {
  it("puts our frame next to the reference per format, and the yes builds from it", async () => {
    const calls = openCardIn(frameCard, { "POST /api/cards/20/accept": { ...frameCard, status: "accepted" } });
    const group = await screen.findByRole("group", { name: "Style frame of m3, round 1" });
    expect(within(group).getByRole("img", { name: "Our frame, Landscape 16:9" }).getAttribute("src")).toBe(
      "/api/files/003-local-ai/motion/m3/frame-v1-landscape.png",
    );
    expect(within(group).getByRole("img", { name: "Reference, Landscape 16:9" })).toBeTruthy();
    expect(within(group).getByRole("img", { name: "Our frame, Portrait 9:16" })).toBeTruthy();
    expect(within(group).getByText("No reference: say what it should beat.")).toBeTruthy();
    expect(within(group).getByText("Landscape 16:9 · Hue check passed: the strongest hue holds 24 %")).toBeTruthy();
    expect(within(group).getByText("Or say what to change.")).toBeTruthy();
    await userEvent.click(within(group).getByRole("button", { name: "Build from this frame" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/cards/20/accept")).toBe(true));
    expect(await screen.findByText("Style frame approved · m3, round 1")).toBeTruthy();
  });
});

const templateCard = card({
  id: 30,
  episode: ep.id,
  step: "edit",
  kind: "template",
  identity: "editor",
  title: "Keep 'GPU hand-off' in your library?",
  body: "New motion graphic from m3, version 2.",
  options: null,
  file: null,
  data: {
    template: {
      name: "gpu_handoff",
      title: "GPU hand-off",
      version: 2,
      kind: "full",
      formats: ["landscape", "portrait"],
      params: { comp: "Main", jobs: 4, label: "GPU" },
      samples: { landscape: "/api/files/_onboarding/brand/templates/motion/samples/gpu_handoff-v2-landscape.mp4", portrait: "/api/files/_onboarding/brand/templates/motion/samples/gpu_handoff-v2-portrait.mp4" },
      poster: "/api/files/_onboarding/brand/templates/motion/samples/gpu_handoff-v2.jpg",
      made_from: { episode: "003-local-ai", insert: "m3" },
      replaces: 1,
    },
  },
});

describe("the template card", () => {
  it("asks to keep it with its sample loops and params", async () => {
    openCardIn(templateCard);
    const group = await screen.findByRole("group", { name: "Keep 'GPU hand-off' in your library?" });
    const loop = group.querySelector<HTMLVideoElement>('video[aria-label="Sample of GPU hand-off, Landscape 16:9"]');
    expect(loop?.muted).toBe(true);
    expect(loop?.loop).toBe(true);
    expect(loop?.hasAttribute("controls")).toBe(false);
    expect(group.querySelector('video[aria-label="Sample of GPU hand-off, Portrait 9:16"]')).toBeTruthy();
    expect(within(group).getByText("jobs")).toBeTruthy();
    expect(within(group).getByText("4")).toBeTruthy();
    expect(within(group).queryByText("comp")).toBeNull();
    expect(within(group).getByText("Made from 003, m3 · version 2 · replaces version 1")).toBeTruthy();
    expect(within(group).getByText("Landscape 16:9, Portrait 9:16")).toBeTruthy();
    expect(within(group).getByRole("button", { name: "Keep it in the library" })).toBeTruthy();
    expect(foldedText({ ...templateCard, status: "accepted" })).toBe("Motion template approved · GPU hand-off, version 2");
  });

  it("shows only the poster with reduced motion", async () => {
    reduceMotion();
    openCardIn(templateCard);
    const group = await screen.findByRole("group", { name: "Keep 'GPU hand-off' in your library?" });
    expect(group.querySelector("video")).toBeNull();
    expect(within(group).getByRole("img", { name: "Sample of GPU hand-off, Landscape 16:9" }).getAttribute("src")).toBe(
      "/api/files/_onboarding/brand/templates/motion/samples/gpu_handoff-v2.jpg",
    );
  });
});

const baselineCard = card({
  id: 40,
  episode: "003-local-ai",
  step: "edit",
  kind: "baseline",
  identity: "critic",
  title: "Raise the motion bar from 002-local-ai to 003-local-ai?",
  body: "Better: the number lands on the spoken word",
  options: null,
  file: "review/motion-report-v002.md",
  data: {
    old: {
      episode: "002-local-ai",
      strengths: [{ name: "numbers land heavy", time: 7, frame: "review/motion-v001/m1/sheet.jpg" }],
      measured: { motion_moments: 5, critic_errors: 0 },
    },
    new: {
      episode: "003-local-ai",
      report: "review/motion-report-v002.json",
      strengths: [{ name: "every exit is caused by a motion", time: 41.2, frame: "review/motion-v002/m3/sheet.jpg" }],
      measured: { motion_moments: 6, critic_errors: 0, upgrades_landed_share: 1 },
      better: [{ what: "the number lands on the spoken word", time: 7.2, against: "numbers land heavy", frame: null }],
    },
  },
});

describe("the baseline card", () => {
  it("shows the bar now and this video with their named strengths", async () => {
    openCardIn(baselineCard);
    const group = await screen.findByRole("group", { name: "Raise the motion bar from 002-local-ai to 003-local-ai?" });
    const old = within(group).getByRole("region", { name: "The bar now, 002" });
    expect(within(old).getByText("numbers land heavy")).toBeTruthy();
    expect(within(old).getByRole("img", { name: "numbers land heavy at 0:07" }).getAttribute("src")).toBe(
      "/api/files/002-local-ai/review/motion-v001/m1/sheet.jpg",
    );
    const now = within(group).getByRole("region", { name: "This video, 003" });
    expect(within(now).getByText("every exit is caused by a motion")).toBeTruthy();
    expect(within(group).getByRole("heading", { name: "Better than the bar" })).toBeTruthy();
    expect(within(group).getByText("0:07 · against “numbers land heavy”")).toBeTruthy();
    expect(within(group).getByText("5 to 6")).toBeTruthy();
    expect(within(group).getByText("Upgrades landed")).toBeTruthy();
    expect(within(group).getByRole("button", { name: "Raise the bar to 003" })).toBeTruthy();
    expect(foldedText({ ...baselineCard, status: "accepted" })).toBe("Motion bar approved · from 002 to 003");
    const first = { ...baselineCard, data: { ...baselineCard.data, old: null } };
    expect(acceptLabel(first)).toBe("Make 003 the bar");
  });
});

// ---------- the episode view ----------

const cut: EpisodeMedia["cut"] = {
  version: "v2",
  seconds: 120,
  shots: 20,
  frames: Array.from({ length: 10 }, (_, i) => ({ t: 6 + i * 12, url: `f${i}.jpg` })),
  peaks: [0.2, 0.8, 0.4, 1],
  markers: [],
  facts: [],
};

function motion(over: Partial<EpisodeMotion> = {}): EpisodeMotion {
  const p = plan();
  return {
    plan: {
      file: p.file,
      md_url: "/api/files/003-local-ai/edit/motion-plan-v002.md",
      version: 2,
      card: { id: 12, status: "open" },
      approved: false,
      columns: p.columns,
      quiet: p.quiet,
      density: p.density,
      budget: p.budget,
      estimate_usd: p.estimate_usd,
      cap_usd: p.cap_usd,
      bar: p.bar,
      short: false,
    },
    pieces: [
      { id: "m1", kind: "library", scene: "number_roll", source: null, beat: 2, column: "a", state: "done", brief: null, loop: "/api/files/003-local-ai/render/inserts/m1-abc.mp4", poster: "/api/files/003-local-ai/render/inserts/m1-abc/0040.png", start: 6.2, end: 9.8, transparent: false },
      { id: "m2", kind: "library", scene: "keyword_pop", source: null, beat: 4, column: "a", state: "building", brief: null, loop: null, poster: "p2.png", start: { word: "offline", offset: -0.4 }, end: 22, transparent: true },
      { id: "m3", kind: "custom", scene: null, source: "motion/m3/comp.jsx", beat: 3, column: "b", state: "style frame", brief: "Show how the agent hands a render job to a rented GPU", loop: null, poster: "frame.png", start: 41, end: 47.5, transparent: false },
      { id: "m4", kind: "library", scene: "lower_third", source: null, beat: 6, column: "a", state: "in review", brief: null, loop: null, poster: "p4.png", start: 70, end: 72, transparent: true },
      { id: "m5", kind: "custom", scene: null, source: "motion/m5/comp.jsx", beat: null, column: null, state: "planned", brief: "A table that sorts itself", loop: null, poster: null, start: null, end: null, transparent: false },
    ],
    report: null,
    retention: null,
    ...over,
  };
}

function openEpisode(media: Partial<EpisodeMedia>, m: EpisodeMotion | Reply, cards: Card[] = []) {
  mockApi({
    "GET /api/state": state({ episodes: [ep] }),
    ...episodeRoutes(ep, [], cards),
    [`GET /api/episodes/${ep.id}/media`]: { thumbnails: [], cut: null, scenes: null, gpu: null, ...media },
    [`GET /api/episodes/${ep.id}/motion`]: m,
  });
  openAt(ep.id);
  render(<App />);
}

describe("motion in the episode view", () => {
  it("puts each motion insert as a tile on the film strip, with its loop and its state", async () => {
    openEpisode({ cut }, motion(), [planCard()]);
    const cutPanel = (await screen.findByText("Cut v2")).closest("section") as HTMLElement;
    const lane = within(cutPanel).getByRole("list", { name: "Motion on the strip" });
    const tiles = within(lane).getAllByRole("listitem");
    // in the order they play: by time, a word anchor by its beat, the unplaced custom piece last
    expect(tiles.map((t) => t.getAttribute("aria-label"))).toEqual([
      "0:06, Number roll. Done.",
      "0:41, Show how the agent hands a render job to a rented GPU. Style frame.",
      "1:10, Lower third. In review.",
      "on “offline”, Keyword pop. Building.",
      "A table that sorts itself. Planned.",
    ]);
    expect(within(tiles[0]!).getByText("Done")).toBeTruthy();
    expect(within(tiles[1]!).getByText("0:41 · Made for this video")).toBeTruthy();
    expect(within(tiles[3]!).getByText("on “offline” · Overlay")).toBeTruthy();
    const loop = tiles[0]!.querySelector("video");
    expect(loop?.muted).toBe(true);
    expect(loop?.getAttribute("poster")).toBe("/api/files/003-local-ai/render/inserts/m1-abc/0040.png");
    expect(tiles[4]!.querySelector(".loop-blank")).toBeTruthy();
    // the bands on the waveform: only the pieces with a start in seconds
    expect(cutPanel.querySelectorAll(".wave-band")).toHaveLength(3);
  });

  it("shows the plan's three columns compact and read-only, and the open card one tap away", async () => {
    openEpisode({ cut }, motion(), [planCard()]);
    const panel = await screen.findByRole("region", { name: "Motion" });
    expect(within(panel).getByText("Plan v2 waits for your yes")).toBeTruthy();
    expect(within(panel).getByRole("heading", { level: 3, name: /^What we have that fits/ })).toBeTruthy();
    expect(within(panel).getByRole("heading", { level: 3, name: /^New for this video/ })).toBeTruthy();
    expect(within(panel).getByRole("heading", { level: 3, name: /^Better than the last one/ })).toBeTruthy();
    expect(within(panel).queryByRole("button", { name: /^Not this one/ })).toBeNull();
    expect(within(panel).getByText(/GPU about \$0\.30, cap \$2 for this video$/)).toBeTruthy();
    expect(within(panel).getByRole("button", { name: "Show the card" })).toBeTruthy();
    // the tiles sit on the strip, not twice in the panel
    expect(within(panel).queryByRole("list", { name: "Motion on the strip" })).toBeNull();
  });

  it("after the build shows the report's three lines, better, behind and next", async () => {
    const m = motion({
      plan: { ...motion().plan!, approved: true, card: { id: 12, status: "accepted" } },
      report: {
        better: "the number lands on the spoken word (0:07.2)",
        behind: "the reference holds the board a beat longer",
        next: "promote m3 as gpu_handoff",
        verdict: "better",
        file: "review/motion-report-v002.json",
        url: "/api/files/003-local-ai/review/motion-report-v002.md",
      },
      retention: { fetched: "2026-11-20", summary: { moments: 4, held: 3, dropped: 0, held_share: 0.75 }, unproven: true },
    });
    openEpisode({}, m);
    const panel = await screen.findByRole("region", { name: "Motion" });
    expect(within(panel).getByText("Plan v2, approved")).toBeTruthy();
    expect(within(panel).getByText("Better than the bar")).toBeTruthy();
    for (const [k, v] of [
      ["Better", "the number lands on the spoken word (0:07.2)"],
      ["Behind", "the reference holds the board a beat longer"],
      ["Next", "promote m3 as gpu_handoff"],
    ]) {
      expect(within(panel).getByText(k!).nextElementSibling?.textContent).toBe(v);
    }
    expect(within(panel).getByRole("link", { name: "Read the motion report" }).getAttribute("href")).toBe(
      "/api/files/003-local-ai/review/motion-report-v002.md",
    );
    expect(within(panel).getByText(/Retention: 3 of 4 motion moments held the viewers\. A hint, not proof/)).toBeTruthy();
    // no cut: the tiles sit in the motion panel
    expect(within(panel).getAllByRole("listitem", { name: /\.$/ }).length).toBeGreaterThanOrEqual(5);
    expect(screen.queryByText(/No pictures yet/)).toBeNull();
  });

  it("shows nothing about motion before the motion pass or on a server without the route", async () => {
    openEpisode({ cut }, new Reply(404, { detail: "No such route." }));
    expect(await screen.findByText("Cut v2")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Motion" })).toBeNull();
    expect(screen.queryByRole("list", { name: "Motion on the strip" })).toBeNull();
  });

  it("says so with a retry when the motion cannot be loaded", async () => {
    openEpisode({ cut }, new Reply(500, { detail: "Broken plan file." }));
    const alert = await screen.findByText(/Couldn't load the motion of this episode\. Broken plan file\./);
    expect(within(alert.closest("[role=alert]") as HTMLElement).getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(screen.getByText("Cut v2")).toBeTruthy();
  });
});

// ---------- the Motion shelf ----------

const profile = { source: "brand", rows: [], preview: null, rules: [] };

const shelf: ShelfRow[] = [
  {
    name: "gpu_handoff",
    origin: "pack",
    title: "GPU hand-off",
    description: "Jobs leave the laptop for a rented GPU.",
    kind: "full",
    formats: ["landscape", "portrait"],
    version: 2,
    versions: [1, 2],
    params: { comp: "Main", jobs: 4, label: "GPU" },
    samples: { landscape: "/api/files/_onboarding/brand/templates/motion/samples/gpu_handoff-v2-landscape.mp4", poster: "/api/files/_onboarding/brand/templates/motion/samples/gpu_handoff-v2.jpg" },
    made_from: { episode: "003-local-ai", insert: "m3" },
    approved: { date: "2026-11-18", by: "user", card: 30 },
    notes: [{ text: "used in 004-agents (m1): review 0 error(s)", source: "review" }],
    uses: [{ episode: "004-agents", insert: "m1", version: null }, { episode: "005-gpu", insert: "m2", version: 1 }],
  },
  {
    name: "number_roll",
    origin: "app",
    title: "Number roll",
    description: "A number rolls and lands on its value.",
    kind: "full",
    formats: ["landscape", "portrait", "stage"],
    version: 2,
    versions: [1, 2],
    params: { comp: "Main", value: "30" },
    samples: { landscape: "/api/motion/app/samples/number_roll-v2-landscape.mp4", poster: "/api/motion/app/samples/number_roll-v2.jpg" },
    overridden: false,
    uses: [],
  },
  { name: "lower_third", origin: "app", title: "Lower third", description: "", kind: "overlay", formats: ["landscape"], version: 1, params: {}, samples: {}, overridden: true, uses: [] },
  { name: "003-local-ai/m3", origin: "episode", episode: "003-local-ai", insert: "m3", title: "Show the hand-off", description: "", kind: "full", formats: [], version: 1, params: {}, samples: {}, promoted_as: "gpu_handoff" },
  { name: "004-agents/m9", origin: "episode", episode: "004-agents", insert: "m9", title: "A table that sorts itself", description: "", kind: "full", formats: [], version: 1, params: {}, samples: { poster: "/api/files/004-agents/motion/m9/frame-v1-landscape.png" }, promoted_as: null },
];

function openProfile(routes: Record<string, unknown>) {
  mockApi({
    "GET /api/state": state({ episodes: [ep, episode({ id: "004-agents", title: "Agents at work" })] }),
    "GET /api/profile": profile,
    ...routes,
  });
  window.history.replaceState(null, "", "/#/profile");
  render(<App />);
}

describe("the Motion shelf of the style pack", () => {
  it("shows your templates and Crewcut's as a grid of loops; opened, the params, the videos and the versions", async () => {
    const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(() => Promise.resolve());
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
    openProfile({
      "GET /api/motion/library": { templates: shelf },
      "GET /api/motion/ratchet": { bar: { episode: "003-local-ai", strengths: [{ name: "numbers land heavy", time: 7, frame: null }] }, lessons: [{ id: "a", date: "2026-11-17", rule: "r" }], merge_needed: false, references: [] },
    });
    const grid = await screen.findByRole("list", { name: "Motion templates" });
    const items = within(grid).getAllByRole("button");
    expect(items.map((b) => b.getAttribute("aria-label"))).toEqual([
      "GPU hand-off, version 2, made for 003",
      "Number roll, version 2, comes with Crewcut",
    ]);
    expect(within(items[1]!).getByText("Crewcut")).toBeTruthy();
    expect(within(items[0]!).getByText("v2 · made for 003")).toBeTruthy();
    expect(within(items[0]!).getByText("Landscape 16:9, Portrait 9:16")).toBeTruthy();
    expect(screen.getByText("The bar is Local AI, privately: numbers land heavy. 1 lesson so far.")).toBeTruthy();
    // muted loops that stand still until pointed at
    const video = items[0]!.querySelector("video") as HTMLVideoElement;
    expect(video.muted).toBe(true);
    expect(play).not.toHaveBeenCalled();
    await userEvent.hover(items[0]!);
    expect(play).toHaveBeenCalled();

    await userEvent.click(items[0]!);
    expect(items[0]!.getAttribute("aria-expanded")).toBe("true");
    const detail = screen.getByRole("region", { name: "GPU hand-off" });
    expect(within(detail).getByText("jobs")).toBeTruthy();
    expect(within(detail).getByText("GPU")).toBeTruthy();
    expect(within(detail).queryByText("comp")).toBeNull();
    expect(within(detail).getByRole("button", { name: "Agents at work" })).toBeTruthy();
    expect(within(detail).getByText("m2 · pinned to version 1")).toBeTruthy();
    expect(within(detail).getByText("Version 2 is the newest. Older: version 1. A plan can pin one, as gpu_handoff@1.")).toBeTruthy();
    expect(within(detail).getByText("used in 004-agents (m1): review 0 error(s)")).toBeTruthy();
    await userEvent.click(within(detail).getByRole("button", { name: "Agents at work" }));
    expect(window.location.hash).toBe("#/e/004-agents");
  });

  it("lists pieces made for one video below the shelf, and not those kept as templates", async () => {
    openProfile({ "GET /api/motion/library": { templates: shelf }, "GET /api/motion/ratchet": new Reply(404, {}) });
    await screen.findByRole("list", { name: "Motion templates" });
    expect(screen.getByText("Made for one video, not in your library")).toBeTruthy();
    expect(screen.getByRole("button", { name: "A table that sorts itself, made for Agents at work. Open the episode." })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Show the hand-off/ })).toBeNull();
  });

  it("shows waiting templates, and nothing on a server without the shelf", async () => {
    const waiting: ShelfRow = { ...shelf[0]!, approved: null };
    openProfile({ "GET /api/motion/library": { templates: [waiting] } });
    expect(await screen.findByRole("button", { name: "GPU hand-off, version 2, made for 003, waiting for your yes" })).toBeTruthy();
    resetApp();
    document.body.innerHTML = "";
    openProfile({});
    expect(await screen.findByRole("heading", { name: "Values" })).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Motion" })).toBeNull());
  });
});

// ---------- the sample data of the CI pictures ----------

describe("motion in the sample data", () => {
  it("keeps the workflow's order: the commercial's plan has its yes, its style frame is the open motion card", async () => {
    window.history.replaceState(null, "", "/#/e/015-thinking-levels-commercial");
    setBackend(createSampleBackend({ latency: 0 }));
    render(<App />);
    expect(await screen.findByRole("group", { name: "Style frame of dial, round 1" })).toBeTruthy();
    expect(await screen.findByText("Motion plan approved · version 2")).toBeTruthy();
    expect(screen.queryByRole("group", { name: /^Motion plan/ })).toBeNull();
    // the approved plan, read-only in the Motion panel, with the row struck before the yes
    const panel = await screen.findByRole("region", { name: "Motion" });
    expect(within(panel).getByText("Plan v2, approved")).toBeTruthy();
    expect(within(panel).queryByRole("button", { name: /^Not this one/ })).toBeNull();
    expect(within(panel).queryByRole("button", { name: "Show the card" })).toBeNull();
    expect(within(panel).getByText("Struck")).toBeTruthy();
    expect(within(panel).getByText(/cap \$2 for this video/)).toBeTruthy();
    const lane = await screen.findByRole("list", { name: "Motion on the strip" });
    expect(within(lane).getAllByRole("listitem").map((t) => t.getAttribute("aria-label"))).toEqual([
      "0:05, Keyword pop. Done.",
      "0:10, A dial turns from low to high and the needle lands as the word high is said. Style frame.",
      "0:15, Number roll. In review.",
    ]);
  });

  it("refuses a strike on the sample's answered plan, as the server does", async () => {
    const sample = createSampleBackend({ latency: 0 });
    await expect(sample.request("POST", "/api/cards/61/strike", { row: "beat:2", struck: true })).rejects.toMatchObject({
      status: 409,
      message: "This card is answered already.",
    });
    const cards = await sample.request<Card[]>("GET", "/api/cards?episode=015-thinking-levels-commercial&status=open");
    expect(cards.map((c) => c.kind).sort()).toEqual(["preview", "style-frame"]);
  });

  it("shows the shelf in the style pack", async () => {
    window.history.replaceState(null, "", "/#/profile");
    setBackend(createSampleBackend({ latency: 0 }));
    render(<App />);
    const grid = await screen.findByRole("list", { name: "Motion templates" });
    expect(within(grid).getAllByRole("button").length).toBe(7);
    expect(within(grid).getByRole("button", { name: /^Board build, version 1, made for 013/ })).toBeTruthy();
    expect(within(grid).getAllByText("Crewcut")).toHaveLength(5);
  });
});

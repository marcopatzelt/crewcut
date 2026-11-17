// Motion graphics in the demo, shaped like docs/api.md ("Motion cards", "Motion"). Made-up data: the commercial (015)
// has its motion plan open (version 2, after one struck row) and the style frame of its one new piece; the published
// 013 shows the finished loop (all pieces done, the report's three lines, the bar moved to it); the shelf holds two
// templates of the pack, the app's five and one piece made for one video. The pictures are small posters drawn with
// plain shapes (public/demo/motion/); the demo has no loops, so every tile shows its poster.
import type {
  Card,
  EpisodeMotion,
  Message,
  MotionBeat,
  MotionNew,
  MotionPlanData,
  MotionRatchet,
  MotionUpgrade,
  ShelfRow,
} from "../api/types";

const POSTER = {
  keyword: "demo/motion/keyword-pop.svg",
  number: "demo/motion/number-roll.svg",
  lower: "demo/motion/lower-third.svg",
  dial: "demo/motion/dial-landscape.svg",
  dialPortrait: "demo/motion/dial-portrait.svg",
  board: "demo/motion/board-build.svg",
  price: "demo/motion/price-tag.svg",
  prompt: "demo/motion/prompt-bar.svg",
  reel: "demo/motion/word-reel.svg",
};

export interface MotionDemo {
  cards: Card[];
  messages: Record<string, Message[]>;
  motion: Record<string, EpisodeMotion>;
  shelf: ShelfRow[];
  ratchet: MotionRatchet;
  /** paths inside episode folders that the motion cards name, mapped to pictures in public/ */
  files: Record<string, string>;
}

const beat = (n: number, time: string, purpose: string, picture: string, extra: Partial<MotionBeat> = {}): MotionBeat => ({
  row: `beat:${n}`,
  beat: n,
  time,
  purpose,
  picture,
  struck: false,
  ...extra,
});

const shelfBeat = (n: number, time: string, purpose: string, picture: string, piece: string, params: Record<string, unknown>, length: number, poster: string, struck = false) =>
  beat(n, time, purpose, picture, { piece, params, length_s: length, cost_usd: 0, media: { loop: null, poster }, struck });

/** The motion moments a plan shows (the server's card title counts them the same way). */
export function momentsOf(plan: Pick<MotionPlanData, "columns">): number {
  const live = (b: MotionBeat) => !b.struck;
  const c = plan.columns;
  return (
    c.a.filter(live).length +
    c.b.filter((x) => !x.struck).reduce((n, x) => n + x.beats.filter(live).length, 0) +
    c.c.filter((x) => !x.struck).reduce((n, x) => n + x.beats.filter(live).length, 0)
  );
}

export function planTitle(plan: Pick<MotionPlanData, "columns" | "version">): string {
  const n = momentsOf(plan);
  return `Motion plan v${String(plan.version).padStart(3, "0")}: ${n} motion moment${n === 1 ? "" : "s"}`;
}

export function makeMotionDemo(ids: { e015: string; e013: string; e011: string }, ago: (seconds: number) => string): MotionDemo {
  const MIN = 60;
  const D = 86400;
  const { e015, e013, e011 } = ids;

  // ----- 015, the commercial: the plan is open, the dial's style frame waits beside it -----
  const dial: MotionNew = {
    row: "new:dial",
    id: "dial",
    beat: 3,
    brief: "A dial turns from low to high and the needle lands as the word high is said.",
    why_new: "No shelf piece shows one setting turning up; a number alone does not show effort.",
    kind: "full",
    plates: 1,
    effort: "M",
    cost_usd: 0.2,
    cap_usd: 1,
    struck: false,
    beats: [beat(3, "0:10", "feel the jump in effort", "a dial turns from low to high; the needle lands on the spoken word", { piece: "dial", length_s: 4 })],
  };
  const upgrades015: MotionUpgrade[] = [
    {
      row: "upgrade:u1",
      id: "u1",
      upgrade: "Every exit from a full-frame piece is caused by a motion",
      source: { kind: "lesson", ref: "2026-11-12-2" },
      effort: "S",
      cost_usd: 0,
      chosen: true,
      struck: false,
      beats: [],
    },
    {
      row: "upgrade:u2",
      id: "u2",
      upgrade: "The number lands on the spoken word, not a beat before it",
      source: { kind: "baseline", ref: e013 },
      effort: "S",
      cost_usd: 0,
      chosen: true,
      struck: false,
      beats: [],
    },
    {
      row: "upgrade:u3",
      id: "u3",
      upgrade: "The opening shot pushes in slowly instead of standing still",
      source: { kind: "reference", ref: "ref-004" },
      effort: "M",
      cost_usd: 0,
      chosen: false,
      struck: false,
      beats: [],
    },
  ];
  const plan015: MotionPlanData = {
    version: 2,
    file: "edit/motion-plan-v002.json",
    md: "edit/motion-plan-v002.md",
    json_sha256: "4f1c0e9a7b2d",
    columns: {
      a: [
        shelfBeat(2, "0:05", "see that thinking has levels", "three words rise beside the Rhine front as they are said: low, medium, high", "keyword_pop", { words: ["low", "medium", "high"] }, 2.4, POSTER.keyword),
        shelfBeat(4, "0:15", "believe the number", "the token count rolls and lands on 32,000 as the word is said", "number_roll", { value: "32000", unit: "tokens" }, 3, POSTER.number),
        // struck in version 1 ("not this one"): the street at the end says the name already
        shelfBeat(5, "0:20", "remember the name", "the name with a line under it", "lower_third", { name: "Thinking levels" }, 2, POSTER.lower, true),
      ],
      b: [dial],
      c: upgrades015,
    },
    quiet: [beat(1, "0:00", "know what this is", "the Rhine front alone")],
    density: "full-frame 2 of max 2 · all motion 3 in 0:25 (max 3) · heroes 0",
    budget: "GPU about $0.20, cap $2",
    estimate_usd: 0.2,
    cap_usd: 2,
    bar: e013,
    short: false,
  };
  const planCard: Card = {
    id: 61,
    episode: e015,
    step: "edit",
    kind: "motion-plan",
    identity: "editor",
    title: planTitle(plan015),
    body: null,
    options: null,
    file: "edit/motion-plan-v002.md",
    preview: null,
    sha256: "7d2a91c4e05b",
    status: "open",
    created: ago(30 * MIN),
    data: { motion_plan: plan015, cap_usd: 2, images: [POSTER.keyword, POSTER.number] },
  };
  const frameCard: Card = {
    id: 62,
    episode: e015,
    step: "edit",
    kind: "style-frame",
    identity: "designer",
    title: "Style frame of dial, round 1",
    body: "Our frame of the strongest moment next to the bar, per format. Nothing animated is built before your yes; a note goes back to the Designer.",
    options: null,
    file: "motion/dial/frame-v1-landscape.png",
    preview: null,
    sha256: "c39e5a0d81f2",
    status: "open",
    created: ago(12 * MIN),
    data: {
      insert: "dial",
      round: 1,
      frames: [
        {
          format: "landscape",
          ours: "motion/dial/frame-v1-landscape.png",
          ours_url: POSTER.dial,
          ref: null,
          ref_url: POSTER.board,
          ref_label: "the bar",
          hue: { dominant_share: 0.24, ok: true },
        },
        {
          format: "portrait",
          ours: "motion/dial/frame-v1-portrait.png",
          ours_url: POSTER.dialPortrait,
          ref: null,
          ref_url: null,
          ref_label: "no reference: say what it should beat",
          hue: { dominant_share: 0.27, ok: true },
        },
      ],
      images: [POSTER.dial, POSTER.board, POSTER.dialPortrait],
    },
  };

  // ----- 013, published: the whole loop has run -----
  const plan013: MotionPlanData = {
    version: 1,
    file: "edit/motion-plan-v001.json",
    md: "edit/motion-plan-v001.md",
    json_sha256: "0a9d3e7c5b11",
    columns: {
      a: [
        shelfBeat(2, "0:07", "believe the price", "the cost rolls and lands on 78 cents as it is said", "number_roll", { value: "0.78", unit: "dollars" }, 3, POSTER.number),
        shelfBeat(5, "0:31", "hear the two words", "two words rise beside the speaker: one prompt", "keyword_pop", { words: ["one", "prompt"] }, 2, POSTER.keyword),
      ],
      b: [
        {
          row: "new:m3",
          id: "m3",
          beat: 9,
          brief: "The board fills tile by tile while the prompt runs.",
          why_new: "No shelf piece shows a game being built from one sentence.",
          kind: "full",
          plates: 0,
          effort: "M",
          cost_usd: 0,
          cap_usd: null,
          struck: false,
          beats: [beat(9, "1:02", "see the game appear", "the board fills tile by tile; the last tile lands on the word done", { piece: "m3", length_s: 5.5 })],
        },
      ],
      c: [
        {
          row: "upgrade:u1",
          id: "u1",
          upgrade: "The price lands on the spoken word, with a hit",
          source: { kind: "lesson", ref: "2026-11-08-1" },
          effort: "S",
          cost_usd: 0,
          chosen: true,
          struck: false,
          beats: [],
        },
        {
          row: "upgrade:u2",
          id: "u2",
          upgrade: "A custom comparison instead of the pricing screenshot",
          source: { kind: "baseline", ref: e011 },
          effort: "M",
          cost_usd: 0,
          chosen: false,
          struck: false,
          beats: [],
        },
      ],
    },
    quiet: [beat(1, "0:00", "know what this is", "the speaker alone"), beat(3, "0:14", "trust the speaker", "the speaker, punch-in")],
    density: "full-frame 2 of max 5 · all motion 3 in 3:33 (max 7) · heroes 0",
    budget: "no GPU money, cap $2",
    estimate_usd: 0,
    cap_usd: 2,
    bar: e011,
    short: false,
  };
  const decided = (at: number) => ({ status: "accepted" as const, created: ago(at + 20 * MIN), decided_at: ago(at) });
  const cards013: Card[] = [
    {
      id: 71,
      episode: e013,
      step: "edit",
      kind: "motion-plan",
      identity: "editor",
      title: planTitle(plan013),
      body: null,
      options: null,
      file: "edit/motion-plan-v001.md",
      preview: null,
      sha256: "1e7b4d09c2aa",
      data: { motion_plan: plan013, cap_usd: 2, images: [POSTER.number, POSTER.keyword] },
      ...decided(5 * D),
    },
    {
      id: 72,
      episode: e013,
      step: "edit",
      kind: "style-frame",
      identity: "designer",
      title: "Style frame of m3, round 2",
      body: "Our frame of the strongest moment next to the bar. Nothing animated is built before your yes; a note goes back to the Designer.",
      options: null,
      file: "motion/m3/frame-v2-landscape.png",
      preview: null,
      sha256: "9b0c2f6e4d13",
      data: {
        insert: "m3",
        round: 2,
        frames: [
          { format: "landscape", ours: "motion/m3/frame-v2-landscape.png", ours_url: POSTER.board, ref: null, ref_url: POSTER.price, ref_label: "the bar", hue: { dominant_share: 0.22, ok: true } },
        ],
      },
      ...decided(4 * D + 6 * 3600),
    },
    {
      id: 73,
      episode: e013,
      step: "edit",
      kind: "template",
      identity: "editor",
      title: "Keep 'Board build' in your library?",
      body: "New motion graphic from m3, version 1. Its params: tiles, prompt, landAt. A second video can use it with other params, without touching the comp.",
      options: null,
      file: null,
      preview: null,
      sha256: null,
      data: {
        template: {
          name: "board_build",
          title: "Board build",
          version: 1,
          kind: "full",
          formats: ["landscape", "portrait"],
          params: { comp: "Main", tiles: 24, prompt: "make a small puzzle game", landAt: 3.2 },
          samples: {},
          poster: POSTER.board,
          made_from: { episode: e013, insert: "m3" },
          replaces: null,
        },
      },
      ...decided(2 * D + 3 * 3600),
    },
    {
      id: 74,
      episode: e013,
      step: "edit",
      kind: "baseline",
      identity: "critic",
      title: `Raise the motion bar from ${e011} to ${e013}?`,
      body: "Better: the number lands on the spoken word",
      options: null,
      file: "review/motion-report-v001.md",
      preview: null,
      sha256: "e2d47a90b6c1",
      data: {
        old: {
          episode: e011,
          strengths: [{ name: "the price lands with a hit", time: 9, frame: "review/motion-v001/m2/sheet.jpg" }],
          measured: { motion_moments: 3, critic_errors: 1 },
        },
        new: {
          episode: e013,
          report: "review/motion-report-v001.json",
          strengths: [
            { name: "the board fills on the spoken word", time: 62, frame: "review/motion-v001/m3/sheet.jpg" },
            { name: "every exit is caused by a motion", time: 66.5, frame: null },
          ],
          measured: { motion_moments: 3, critic_errors: 0, upgrades_landed_share: 1 },
          better: [{ what: "the number lands on the spoken word", time: 7.2, against: "the price lands with a hit", frame: null }],
        },
      },
      ...decided(2 * D),
    },
  ];

  const messages: Record<string, Message[]> = {
    [e015]: [
      {
        id: 402,
        at: ago(30 * MIN),
        author: "editor",
        step: "edit",
        text: "Motion plan for the commercial. Most of it stays with the 3D shots; three moments get motion, one of them new.",
        card: 61,
        cite: "Purpose and picture first, the shelf second",
      },
      {
        id: 403,
        at: ago(12 * MIN),
        author: "designer",
        step: "edit",
        text: "The dial is the one new piece. Its frame at the strongest moment, next to the board from 013, so you can judge it with the plan.",
        card: 62,
      },
    ],
    // the Editor's and the Critic's cards on the way to publishing; each message only names its card
    [e013]: cards013.map((c, i) => ({ id: 480 + i, at: c.created, author: c.identity ?? "editor", step: "edit", text: c.title, card: c.id })),
  };

  const motion: Record<string, EpisodeMotion> = {
    [e015]: {
      plan: {
        file: plan015.file,
        md_url: null,
        version: plan015.version,
        card: { id: 61, status: "open" },
        approved: false,
        columns: plan015.columns,
        quiet: plan015.quiet,
        density: plan015.density,
        budget: plan015.budget,
        estimate_usd: plan015.estimate_usd,
        cap_usd: plan015.cap_usd,
        bar: plan015.bar,
        short: false,
      },
      pieces: [
        { id: "m1", kind: "library", scene: "keyword_pop", source: null, beat: 2, column: "a", state: "done", brief: null, loop: null, poster: POSTER.keyword, start: 5.2, end: 7.6, transparent: true },
        { id: "m2", kind: "library", scene: "number_roll", source: null, beat: 4, column: "a", state: "in review", brief: null, loop: null, poster: POSTER.number, start: 15, end: 18, transparent: false },
        { id: "dial", kind: "custom", scene: null, source: "motion/dial/comp.jsx", beat: null, column: null, state: "style frame", brief: dial.brief, loop: null, poster: POSTER.dial, start: null, end: null, transparent: false },
      ],
      report: null,
      retention: null,
    },
    [e013]: {
      plan: {
        file: plan013.file,
        md_url: null,
        version: 1,
        card: { id: 71, status: "accepted" },
        approved: true,
        columns: plan013.columns,
        quiet: plan013.quiet,
        density: plan013.density,
        budget: plan013.budget,
        estimate_usd: 0,
        cap_usd: 2,
        bar: e011,
        short: false,
      },
      pieces: [
        { id: "m1", kind: "library", scene: "number_roll", source: null, beat: 2, column: "a", state: "done", brief: null, loop: null, poster: POSTER.number, start: 6.2, end: 9, transparent: false },
        { id: "m2", kind: "library", scene: "keyword_pop", source: null, beat: 5, column: "a", state: "done", brief: null, loop: null, poster: POSTER.keyword, start: 30.5, end: 32.5, transparent: true },
        { id: "m3", kind: "custom", scene: null, source: "motion/m3/comp.jsx", beat: 9, column: "b", state: "done", brief: "The board fills tile by tile while the prompt runs.", loop: null, poster: POSTER.board, start: 61, end: 66.5, transparent: false },
      ],
      report: {
        better: "the number lands on the spoken word (0:07.2)",
        behind: "the reference holds the full board a beat longer before the exit",
        next: "keep m3 as Board build; try it on a ranking next",
        verdict: "better",
        file: "review/motion-report-v001.json",
        url: null,
      },
      retention: { fetched: ago(2 * D).slice(0, 10), summary: { moments: 3, held: 2, dropped: 0, held_share: 0.67 }, unproven: true },
    },
  };

  const used = (episode: string, insert: string, version: number | null = null) => ({ episode, insert, version });
  const approved = (date: string, card: number) => ({ date, by: "user", card });
  const shelf: ShelfRow[] = [
    {
      name: "board_build",
      origin: "pack",
      title: "Board build",
      description: "A board fills tile by tile while a prompt runs; the last tile lands on a cue.",
      kind: "full",
      formats: ["landscape", "portrait"],
      version: 1,
      versions: [1],
      params: { comp: "Main", tiles: 24, prompt: "make a small puzzle game", landAt: 3.2 },
      samples: { poster: POSTER.board },
      made_from: { episode: e013, insert: "m3" },
      approved: approved("2026-11-15", 73),
      needs_plates: false,
      notes: [{ date: "2026-11-15", text: `used in ${e013} (m3): review 0 error(s)`, source: "review" }],
      uses: [],
    },
    {
      name: "price_tag",
      origin: "pack",
      title: "Price tag",
      description: "A price tag drops in and swings until it settles on the spoken price.",
      kind: "overlay",
      formats: ["landscape", "portrait", "stage"],
      version: 2,
      versions: [1, 2],
      params: { comp: "Main", price: "$0.10", swing: 8 },
      samples: { poster: POSTER.price },
      made_from: { episode: e011, insert: "m2" },
      approved: approved("2026-11-10", 44),
      needs_plates: false,
      notes: [{ date: "2026-11-15", text: "held viewers in 2 of 2 uses (watch, not a lesson yet)", source: "retention" }],
      uses: [used(e011, "m2", 1), used(e013, "m4")],
    },
    {
      name: "number_roll",
      origin: "app",
      title: "Number roll",
      description: "A number rolls and lands on its value as it is spoken; whole digits on the hold, never clipped.",
      kind: "full",
      formats: ["landscape", "portrait", "stage"],
      version: 2,
      versions: [1, 2],
      params: { comp: "Main", value: "30", unit: "", landAt: 1.4 },
      samples: { poster: POSTER.number },
      overridden: false,
      uses: [used(e011, "m1"), used(e013, "m1"), used(e015, "m2")],
    },
    {
      name: "keyword_pop",
      origin: "app",
      title: "Keyword pop",
      description: "One or two words rise beside the speaker, never over the face.",
      kind: "overlay",
      formats: ["landscape", "portrait"],
      version: 1,
      versions: [1],
      params: { comp: "Main", words: ["runs", "offline"] },
      samples: { poster: POSTER.keyword },
      overridden: false,
      uses: [used(e013, "m2"), used(e015, "m1")],
    },
    {
      name: "lower_third",
      origin: "app",
      title: "Lower third",
      description: "A name with a line under it.",
      kind: "overlay",
      formats: ["landscape", "portrait"],
      version: 1,
      versions: [1],
      params: { comp: "Main", name: "Your name", line: "" },
      samples: { poster: POSTER.lower },
      overridden: false,
      uses: [],
    },
    {
      name: "prompt_bar",
      origin: "app",
      title: "Prompt bar",
      description: "A prompt is typed into a bar and sent.",
      kind: "overlay",
      formats: ["landscape", "portrait"],
      version: 1,
      versions: [1],
      params: { comp: "Main", text: "Make it better" },
      samples: { poster: POSTER.prompt },
      overridden: false,
      uses: [],
    },
    {
      name: "word_reel",
      origin: "app",
      title: "Word reel",
      description: "Words roll past until the one that matters stops in the middle.",
      kind: "full",
      formats: ["landscape", "portrait", "stage"],
      version: 1,
      versions: [1],
      params: { comp: "Main", words: ["faster", "cheaper", "private"] },
      samples: { poster: POSTER.reel },
      overridden: false,
      uses: [],
    },
    {
      name: `${e015}/dial`,
      origin: "episode",
      episode: e015,
      insert: "dial",
      title: dial.brief ?? "dial",
      description: "",
      kind: "full",
      formats: ["landscape", "portrait"],
      version: 1,
      params: {},
      samples: { poster: POSTER.dial },
      promoted_as: null,
      header_ok: true,
    },
    {
      name: `${e013}/m3`,
      origin: "episode",
      episode: e013,
      insert: "m3",
      title: "The board fills tile by tile while the prompt runs.",
      description: "",
      kind: "full",
      formats: ["landscape", "portrait"],
      version: 1,
      params: {},
      samples: { poster: POSTER.board },
      promoted_as: "board_build",
      header_ok: true,
    },
  ];

  const ratchet: MotionRatchet = {
    bar: {
      episode: e013,
      report: "review/motion-report-v001.json",
      strengths: [
        { name: "the board fills on the spoken word", time: 62, frame: null },
        { name: "every exit is caused by a motion", time: 66.5, frame: null },
        { name: "the number lands on the spoken word", time: 7.2, frame: null },
      ],
      measured: { motion_moments: 3, critic_errors: 0 },
    },
    lessons: [
      { id: "2026-11-08-1", date: "2026-11-08", rule: "A price lands on the spoken word, with a hit." },
      { id: "2026-11-12-2", date: "2026-11-12", rule: "Every exit from a full-frame piece is caused by a motion." },
      { id: "2026-11-15-1", date: "2026-11-15", rule: "Hold a finished board one beat before the exit." },
    ],
    merge_needed: false,
    references: [{ id: "ref-004", link: null, file: null, by: "user", reason: "the slow push at the start" }],
  };

  return {
    cards: [planCard, frameCard, ...cards013],
    messages,
    motion,
    shelf,
    ratchet,
    files: {
      "motion/dial/frame-v1-landscape.png": POSTER.dial,
      "motion/dial/frame-v1-portrait.png": POSTER.dialPortrait,
      "review/motion-v001/m3/sheet.jpg": POSTER.board,
      "review/motion-v001/m2/sheet.jpg": POSTER.price,
    },
  };
}

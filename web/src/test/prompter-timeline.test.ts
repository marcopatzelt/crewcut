// The shared timeline and the mapping of a place to a screen: pure functions, the same rules as crewcut/prompter.py.
import { describe, expect, it } from "vitest";
import type { PrompterControl } from "../api/types";
import { placeOn, scrollFor, type Layout } from "../prompter/geometry";
import { DEFAULT_CONTROL } from "../prompter/sync";
import {
  advance, ClockSync, JUMP_HOLD_MS, normalizeBlocks, PAUSE_CHARS, placeAt, reduce, SECTION_PAUSE_CHARS, stepTarget,
} from "../prompter/timeline";

describe("the shared timeline", () => {
  it("moves through the blocks and stops at the end (the same cases as the Python test)", () => {
    const w = [10, 20, 30];
    expect(advance(w, 0, 0, 5)).toEqual({ block: 0, offset: 0.5, end: false });
    expect(advance(w, 0, 0.5, 15)).toEqual({ block: 1, offset: 0.5, end: false });
    expect(advance(w, 1, 0, 20)).toEqual({ block: 2, offset: 0, end: false });
    expect(advance(w, 2, 0.5, 100)).toEqual({ block: 2, offset: 1, end: true });
    expect(advance([], 3, 0.2, 1)).toEqual({ block: 0, offset: 0, end: true });
  });

  it("computes the place from the anchor, the speed and the server time, and waits during a hold", () => {
    const c: PrompterControl = { ...DEFAULT_CONTROL, playing: true, speed: 2, block: 0, offset: 0, at: 1000 };
    expect(placeAt(c, [1000], 17, 2000).offset).toBeCloseTo(34 / 1000);
    expect(placeAt(c, [1000], 17, 500)).toEqual({ block: 0, offset: 0, end: false });
    expect(placeAt({ ...c, playing: false }, [1000], 17, 9000).offset).toBe(0);
  });

  it("numbers spoken blocks, skips headings and gives breaths to blocks without weights", () => {
    const blocks = normalizeBlocks([
      { text: "Intro", points: [], heading: true },
      { text: "One.", points: [] },
      { text: "Two.", points: [], section: 2 },
    ]);
    expect(blocks.map((b) => b.n)).toEqual([null, 1, 2]);
    expect(blocks[1]?.weight).toBe(4 + SECTION_PAUSE_CHARS);
    expect(blocks[2]?.weight).toBe(4 + PAUSE_CHARS);
    expect(stepTarget(blocks, 2, -1)).toBe(1);
    expect(stepTarget(blocks, 1, -1)).toBeNull();
    expect(stepTarget(blocks, 2, 1)).toBeNull();
  });

  it("makes the same change as the server: jumps hold while playing, scrolls move, start pauses", () => {
    const w = [100, 100, 100];
    const playing: PrompterControl = { ...DEFAULT_CONTROL, playing: true, block: 0, offset: 0, at: 0, cue: 2 };
    const jumped = reduce(playing, { action: "repeat", block: 1 }, w, 10, 5000);
    expect([jumped.block, jumped.offset, jumped.cue, jumped.at]).toEqual([1, 0, 3, 5000 + JUMP_HOLD_MS]);
    const scrolled = reduce(playing, { action: "scroll", block: 2, offset: 0.25 }, w, 10, 5000);
    expect([scrolled.block, scrolled.offset, scrolled.at, scrolled.cue]).toEqual([2, 0.25, 5000, 2]);
    const paused = reduce(playing, { playing: false }, w, 10, 5000);
    expect([paused.block, paused.offset, paused.playing]).toEqual([0, 0.5, false]);
    const start = reduce(scrolled, { action: "start" }, w, 10, 6000);
    expect([start.block, start.offset, start.playing]).toEqual([0, 0, false]);
    expect(reduce(playing, { action: "end" }, w, 10, 1000)).toBe(playing);
    expect(reduce(playing, { action: "end" }, w, 10, 100_000).playing).toBe(false);
  });
});

describe("the server clock", () => {
  it("uses the answer with the shortest network time and leaves out the time the server waited", () => {
    let local = 10_000;
    const clock = new ClockSync(() => local);
    clock.sample(10_000, 10_100, 50_050); // 100 ms round trip: server = local + 40_000
    clock.sample(10_000, 30_040, 70_020, 20_000); // a long poll: 40 ms on the network
    local = 40_000;
    expect(clock.now()).toBe(80_000);
    clock.reset();
    expect(clock.now()).toBe(80_000); // keeps the last estimate until a new answer comes
  });
});

describe("a place on a screen", () => {
  const phone: Layout = { tops: [0, 100, 200, 300], slots: [100, 100, 100, 100], half: 20, offsetY: 30, max: 10_000 };
  const glass: Layout = { tops: [0, 60, 120, 180], slots: [60, 60, 60, 60], half: 30, offsetY: 50, max: 10_000 };

  it("puts the same block and share of it on the reading line on screens that wrap differently", () => {
    const top = scrollFor(phone, 2, 0.4);
    expect(top).toBe(200 + 20 + 40 - 30);
    expect(placeOn(phone, top)).toEqual({ block: 2, offset: 0.4 });
    const there = placeOn(phone, top);
    expect(placeOn(glass, scrollFor(glass, there.block, there.offset)).block).toBe(2);
    expect(placeOn(glass, scrollFor(glass, there.block, there.offset)).offset).toBeCloseTo(0.4);
  });

  it("starts a block with its first line on the reading line and clamps at the ends", () => {
    expect(scrollFor(phone, 1, 0)).toBe(100 + 20 - 30);
    expect(scrollFor({ ...phone, max: 50 }, 3, 1)).toBe(50);
    expect(placeOn({ ...phone, offsetY: phone.half }, 0)).toEqual({ block: 0, offset: 0 }); // as in the CSS
    expect(placeOn(phone, 99_999).block).toBe(3);
  });
});

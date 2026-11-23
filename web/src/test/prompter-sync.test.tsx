// Several teleprompter screens on one shared server: the phone in Marco's hand, the desktop window on the prompter
// glass and a phone remote. Regression tests for the sync bug of 23 Nov 2026: a hand scroll on the phone reached the
// glass only now and then (never while paused; while playing the glass's own progress reports undid it), the phone
// snapped back when Play was pressed, and a newly opened screen started at the top.
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { PrompterControl, PrompterScript } from "../api/types";
import { DEFAULT_CONTROL, Prompter, type PrompterSource } from "../prompter/Prompter";
import { normalizeBlocks, reduce, type ControlPatch } from "../prompter/timeline";

const script: PrompterScript = {
  title: "Synthetic episode",
  mode: "full",
  cps: 17,
  blocks: Array.from({ length: 20 }, (_, i) => ({ text: `Spoken block number ${i + 1} of the synthetic script.`,
    points: [`Point ${i + 1}`], n: i + 1, section: i < 10 ? 1 : 2 })),
};
const weights = normalizeBlocks(script.blocks).map((b) => b.weight);

/** The shared server: the same change as crewcut/prompter.py (reduce), a new seq per write, and answers that wait
 * until something newer exists. */
class Server {
  state: PrompterControl = { ...DEFAULT_CONTROL, block: 0, offset: 0, at: Date.now(), seq: 1, cue: 0 };
  posts: Array<ControlPatch & { client?: string }> = [];
  private waiting = new Set<() => void>();

  write(patch: ControlPatch & { client?: string }): PrompterControl {
    this.posts.push(patch);
    const next = reduce(this.state, patch, weights, 17, Date.now());
    if (next !== this.state) this.state = { ...next, seq: (this.state.seq ?? 0) + 1, by: patch.client ?? "" };
    const waiting = [...this.waiting];
    this.waiting.clear();
    waiting.forEach((answer) => answer());
    return { ...this.state, now: Date.now() };
  }

  source(): PrompterSource {
    return {
      shared: true,
      script: async () => script,
      getControl: (o = {}) =>
        new Promise<PrompterControl>((resolve, reject) => {
          const answer = () => resolve({ ...this.state, now: Date.now(), waited: 0 });
          if (o.after === undefined || o.after !== this.state.seq || !o.wait) {
            answer();
            return;
          }
          const done = () => {
            clearTimeout(timer);
            answer();
          };
          const timer = setTimeout(() => {
            this.waiting.delete(done);
            answer();
          }, o.wait * 1000);
          this.waiting.add(done);
          o.signal?.addEventListener("abort", () => {
            clearTimeout(timer);
            this.waiting.delete(done);
            reject(new DOMException("The read was stopped.", "AbortError"));
          });
        }),
      setControl: async (patch) => this.write(patch),
    };
  }
}

// jsdom has no layout: give every screen its own block heights, as a phone and the glass wrap the text differently.
const SLOT: Record<string, number> = { phone: 100, glass: 60, remote: 40 };
const HEIGHT = 600; // the visible height of every scroller
const LINE = HEIGHT * 0.33; // the reading line at 33 %
const kind = (el: Element) => el.closest("[data-screen]")?.getAttribute("data-screen") ?? "phone";
const saved = new Map<string, PropertyDescriptor | undefined>();
function stub(name: string, get: (this: HTMLElement) => number) {
  saved.set(name, Object.getOwnPropertyDescriptor(HTMLElement.prototype, name));
  Object.defineProperty(HTMLElement.prototype, name, { configurable: true, get });
}
let rect: PropertyDescriptor | undefined;

beforeEach(() => {
  stub("offsetTop", function () {
    return this.dataset.index === undefined ? 0 : Number(this.dataset.index) * SLOT[kind(this)]!;
  });
  stub("offsetHeight", function () {
    return this.dataset.index === undefined ? 0 : SLOT[kind(this)]! - 10;
  });
  stub("clientHeight", function () {
    return this.classList.contains("pr-scroll") ? HEIGHT : 0;
  });
  stub("scrollHeight", function () {
    return this.classList.contains("pr-scroll") ? script.blocks.length * SLOT[kind(this)]! + HEIGHT : 0;
  });
  rect = Object.getOwnPropertyDescriptor(Element.prototype, "getBoundingClientRect");
  Object.defineProperty(Element.prototype, "getBoundingClientRect", {
    configurable: true,
    value(this: Element) {
      // The text column starts with the first line on the reading line, like the CSS padding.
      const top = this.classList.contains("pr-copy") ? LINE - (this.closest(".pr-scroll")?.scrollTop ?? 0) : 0;
      return { top, bottom: top, left: 0, right: 0, width: 0, height: 0, x: 0, y: top, toJSON: () => ({}) } as DOMRect;
    },
  });
});

afterEach(() => {
  for (const [name, descriptor] of saved) {
    if (descriptor) Object.defineProperty(HTMLElement.prototype, name, descriptor);
    else delete (HTMLElement.prototype as unknown as Record<string, unknown>)[name];
  }
  saved.clear();
  if (rect) Object.defineProperty(Element.prototype, "getBoundingClientRect", rect);
});

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));
/** Lets answers arrive and React render (inside act, renders wait for the end of the act), then one more frame. */
async function wait(ms: number) {
  await act(() => sleep(ms));
  await act(() => sleep(20));
}

function open(server: Server, name: "phone" | "glass" | "remote") {
  const view = render(
    <div data-screen={name}>
      <Prompter source={server.source()} remote={name === "remote"} />
    </div>,
  );
  return { view, scroller: () => view.container.querySelector<HTMLDivElement>(".pr-scroll")! };
}

/** A hand scroll on a screen: touch, move, let go. */
async function handScroll(el: HTMLElement, top: number) {
  fireEvent.touchStart(el);
  el.scrollTop = top;
  fireEvent.scroll(el);
  await wait(30);
  fireEvent.touchEnd(el);
}

const placeOf = (name: string, top: number) => {
  const slot = SLOT[name]!;
  return { block: Math.floor(top / slot), offset: (top % slot) / slot };
};

describe("several screens on one teleprompter", () => {
  it("moves the glass with a hand scroll on the phone at once while paused, up and down", async () => {
    const server = new Server();
    const phone = open(server, "phone");
    const glass = open(server, "glass");
    await wait(60);
    for (const top of [1250, 430, 1720, 150]) {
      await handScroll(phone.scroller(), top);
      await wait(60); // one answer and one frame
      const place = placeOf("phone", top);
      expect(glass.scroller().scrollTop).toBeCloseTo(place.block * SLOT.glass! + place.offset * SLOT.glass!, 0);
    }
    expect(server.state.playing).toBe(false);
  });

  it("opens a new screen at the shared place, not at the top", async () => {
    const server = new Server();
    server.write({ action: "jump", block: 7 });
    const glass = open(server, "glass");
    await wait(60);
    expect(glass.scroller().scrollTop).toBe(7 * SLOT.glass!);
    expect(glass.view.container.querySelector("[aria-current='true']")?.getAttribute("data-index")).toBe("7");
  });

  it("keeps the place the phone scrolled to when Play is pressed", async () => {
    const server = new Server();
    server.write({ action: "jump", block: 12 });
    const phone = open(server, "phone");
    const glass = open(server, "glass");
    await wait(60);
    await handScroll(phone.scroller(), 350);
    await wait(320); // the end of the scroll
    fireEvent.click(within(phone.view.container).getByRole("button", { name: "Play" }));
    await wait(80);
    expect(server.state.playing).toBe(true);
    expect(server.state.block).toBe(3);
    expect(phone.scroller().scrollTop).toBeGreaterThanOrEqual(349);
    expect(phone.scroller().scrollTop).toBeLessThan(380);
    expect(glass.scroller().scrollTop).toBeGreaterThanOrEqual(3.5 * SLOT.glass! - 1);
    expect(server.posts.filter((p) => p.action === "scrolled")).toHaveLength(1);
  });

  it("follows every scroll up while both screens play, the first time, without progress reports", async () => {
    const server = new Server();
    server.write({ action: "jump", block: 15 });
    server.write({ playing: true, speed: 1 });
    const phone = open(server, "phone");
    const glass = open(server, "glass");
    await wait(60);
    const before = server.posts.length;
    for (const top of [1300, 1000, 700, 400, 100]) {
      await handScroll(phone.scroller(), top);
      await wait(60);
      const place = placeOf("phone", top);
      // the glass is at the phone's place, plus what the text moved on since (17 characters a second)
      const glassTop = glass.scroller().scrollTop;
      const expected = (place.block + place.offset) * SLOT.glass!;
      expect(glassTop).toBeGreaterThanOrEqual(expected - 1);
      expect(glassTop).toBeLessThan(expected + 12);
    }
    await wait(300);
    // only hand scrolls were written: no screen reports where it is while it plays
    const written = server.posts.slice(before).map((p) => p.action);
    expect(written.every((a) => a === "scroll" || a === "scrolled")).toBe(true);
    expect(server.state.playing).toBe(true);
  });

  it("jumps every screen to a tapped block and marks it, and Previous, Repeat and Next work from any screen", async () => {
    const server = new Server();
    const phone = open(server, "phone");
    const glass = open(server, "glass");
    const remote = open(server, "remote");
    await wait(60);
    const tapped = phone.view.container.querySelector<HTMLElement>("[data-index='5']")!;
    fireEvent.click(tapped);
    await wait(60);
    expect(glass.scroller().scrollTop).toBe(5 * SLOT.glass!);
    const marked = glass.view.container.querySelector<HTMLElement>("[data-index='5']")!;
    expect(marked.getAttribute("aria-current")).toBe("true");
    expect(marked.classList.contains("cued")).toBe(true);
    expect(within(remote.view.container).getByRole("button", { name: /^Block 6:/ }).getAttribute("aria-current")).toBe("true");

    fireEvent.click(within(remote.view.container).getByRole("button", { name: "Next block" }));
    await wait(60);
    expect(server.state.block).toBe(6);
    expect(phone.scroller().scrollTop).toBe(6 * SLOT.phone!);
    fireEvent.click(within(glass.view.container).getByRole("button", { name: "Previous block" }));
    await wait(60);
    expect(server.state.block).toBe(5);
    fireEvent.click(within(phone.view.container).getByRole("button", { name: /^Repeat block 6 of 20$/ }));
    await wait(60);
    expect([server.state.block, server.state.cue]).toEqual([5, 4]);
    fireEvent.click(within(remote.view.container).getByRole("button", { name: /^Block 12:/ }));
    await wait(60);
    expect(glass.scroller().scrollTop).toBe(11 * SLOT.glass!);
    expect(server.posts.map((p) => p.action)).toEqual(["jump", "next", "prev", "repeat", "jump"]);
  });

  it("asks again at once when the phone wakes up", async () => {
    const server = new Server();
    const reads: number[] = [];
    const source = server.source();
    const counting: PrompterSource = { ...source, getControl: (o) => { reads.push(Date.now()); return source.getControl(o); } };
    render(<div data-screen="phone"><Prompter source={counting} remote={false} /></div>);
    await wait(60);
    const before = reads.length;
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
    document.dispatchEvent(new Event("visibilitychange"));
    await wait(20);
    expect(reads.length).toBe(before + 1);
    delete (document as unknown as Record<string, unknown>).visibilityState;
  });
});

describe("the block buttons", () => {
  it("are on the reading screen and on the remote, and end at the first and last block", async () => {
    const server = new Server();
    const phone = open(server, "phone");
    await wait(60);
    const bar = within(phone.view.container).getByRole("toolbar", { name: "Speaking blocks" });
    expect((within(bar).getByRole("button", { name: "Previous block" }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(bar).getByRole("button", { name: "Repeat block 1 of 20" })).toBeTruthy();
    server.write({ action: "jump", block: 19 });
    await wait(60);
    expect((within(bar).getByRole("button", { name: "Next block" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getAllByRole("toolbar", { name: "Teleprompter controls" })).toHaveLength(1);
  });
});

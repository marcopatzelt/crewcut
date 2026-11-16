// Slate, the mascot (DESIGN.md rule 13): valid SVG for every prop and state, the state on each Crew row, the tick that
// starts again when a crew member reports a new step, and no raw colours in the app's SVG.
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { appIcon, avatar, CSS_PALETTE, mark, PROPS, smallIcon, standing, type SlateState } from "../slate/art";
import { Avatar, propOf } from "../slate/Slate";
import { episode, episodeRoutes, job, mockApi, resetApp, state } from "./helpers";

beforeEach(() => resetApp());

const STATES: SlateState[] = ["plain", "idle", "working", "waiting", "done", "wave"];

function parse(svg: string) {
  const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
  expect(doc.getElementsByTagName("parsererror").length).toBe(0);
  return doc.documentElement;
}

describe("Slate's geometry", () => {
  it("draws valid SVG for every prop and every state, with colours only from tokens", () => {
    for (const p of [...PROPS, null]) {
      for (const s of STATES) {
        const svg = avatar(CSS_PALETTE, p, s);
        const root = parse(svg);
        expect(root.getAttribute("viewBox")).toBe("0 0 128 128");
        expect(svg).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      }
    }
    for (const svg of [standing(CSS_PALETTE, "wave"), mark(CSS_PALETTE), appIcon(CSS_PALETTE), smallIcon(CSS_PALETTE)]) {
      parse(svg);
    }
  });

  it("shuts the bar when done and opens it otherwise", () => {
    expect(avatar(CSS_PALETTE, null, "done")).toContain('class="sl-bar" transform="rotate(0 8 47)"');
    expect(avatar(CSS_PALETTE, null, "working")).toContain('class="sl-bar" transform="rotate(-13.4 8 47)"');
  });

  it("finds the prop from the identity file, with a fallback by id", () => {
    expect(propOf({ id: "editor", avatar: "scissors" })).toBe("scissors");
    expect(propOf({ id: "critic" })).toBe("clipboard");
    expect(propOf({ id: "someone-new", avatar: "trumpet" })).toBeNull();
  });

  it("is decorative: hidden from screen readers, the name stands next to it", () => {
    const { container } = render(<Avatar who={{ id: "scout" }} state="working" />);
    const el = container.querySelector(".avatar");
    expect(el?.getAttribute("aria-hidden")).toBe("true");
    expect(el?.className).toContain("is-working");
  });
});

describe("Slate in the Crew column", () => {
  it("works, waits for you and dozes: one state per row", async () => {
    const ep = episode();
    const activity = [
      job(1, { identity: "editor", status: "running" }),
      job(2, { identity: "showrunner", status: "waiting", doing: "Waiting for your yes on the preview", progress: null }),
      job(3, { identity: "scout", status: "queued", doing: "", progress: null }),
    ];
    mockApi({ "GET /api/state": state({ episodes: [ep], activity }), ...episodeRoutes(ep, [], []) });
    render(<App />);
    const crew = await screen.findByRole("complementary", { name: "Working now" });
    const rows = await within(crew).findAllByRole("button", { name: /Open the (log|card)\./ });
    const states = rows.map((r) => r.querySelector(".avatar")?.className ?? "");
    expect(states.some((c) => c.includes("is-working"))).toBe(true);
    expect(states.some((c) => c.includes("is-waiting"))).toBe(true);
    expect(states.some((c) => c.includes("is-idle"))).toBe(true);
  });

  it("does not start the tick again while the crew member reports the same step", async () => {
    const ep = episode();
    mockApi({ "GET /api/state": state({ episodes: [ep], activity: [job(1)] }), ...episodeRoutes(ep, [], []) });
    const { rerender } = render(<App />);
    const crew = await screen.findByRole("complementary", { name: "Working now" });
    const before = (await within(crew).findByRole("button", { name: /Rendering scene 1/ })).querySelector(".avatar");
    rerender(<App />);
    const same = within(crew).getByRole("button", { name: /Rendering scene 1/ }).querySelector(".avatar");
    expect(same).toBe(before);
  });
});

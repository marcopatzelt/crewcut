// All episodes as cards: filter pills with counts, groups by time, a card opens its chat.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { getUi } from "../store/store";
import { footageTarget, isDone } from "../views/Home";
import { episode, episodeRoutes, mockApi, resetApp, state } from "./helpers";

beforeEach(() => {
  resetApp();
  window.location.hash = "#/episodes";
});

describe("the episode grid", () => {
  it("separates planned and parked work and permits explicit historical resume", async () => {
    const planned = episode({ id: "001-plan", title: "Future video", lifecycle: "planned", step: "record" });
    const parked = episode({ id: "002-park", title: "Later video", lifecycle: "parked", step: "record" });
    const resumed = episode({ id: "003-resume", title: "Review again", lifecycle: "active", historical_status: "published", step: "record" });
    mockApi({ "GET /api/state": state({ episodes: [planned, parked, resumed] }) });
    render(<App />);
    const pills = await screen.findByRole("group", { name: "Show" });
    expect(within(pills).getByRole("button", { name: /In work\s*1/ })).toBeTruthy();
    expect(screen.getByText("Planned, not started")).toBeTruthy();
    expect(screen.getByText("Parked until you resume")).toBeTruthy();
    expect(screen.getByText("Resumed for review")).toBeTruthy();
    expect(footageTarget([planned, parked, resumed])).toEqual(resumed);
    expect(isDone(resumed)).toBe(false);
  });
  it("shows historical publication without granting a new upload approval", async () => {
    const published = episode({ id: "001-history", title: "Earlier video", historical_status: "published" });
    const parked = episode({ id: "002-parked", title: "Later idea", historical_status: "parked", step: "record" });
    const active = episode({ id: "003-active", title: "Current video", step: "record" });
    mockApi({ "GET /api/state": state({ episodes: [published, parked, active] }) });
    render(<App />);
    const pills = await screen.findByRole("group", { name: "Show" });
    expect(within(pills).getByRole("button", { name: /In work\s*1/ })).toBeTruthy();
    expect(within(pills).getByRole("button", { name: /Published\s*1/ })).toBeTruthy();
    expect(screen.getByText("Published in earlier studio")).toBeTruthy();
    expect(screen.getByText("Paused in earlier studio")).toBeTruthy();
    expect(footageTarget([parked, active])).toEqual(active);
    expect(footageTarget([parked])).toBeUndefined();
  });

  it("filters with pills and opens an episode from its card", async () => {
    const long = episode({ id: "003-long", title: "A long video", open_cards: 1, cover: "covers/003.jpg" });
    const short = episode({ id: "005-short", title: "A clip", kind: "short", mode: "clip", source_episode: "003-long" });
    mockApi({
      "GET /api/state": state({ episodes: [long, short] }),
      ...episodeRoutes(long, [], []),
      ...episodeRoutes(short, [], []),
    });
    render(<App />);
    const pills = await screen.findByRole("group", { name: "Show" });
    expect(within(pills).getByRole("button", { name: /All\s*2/ }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("button", { name: /A long video\. Episode 003.*Needs your yes\./ })).toBeTruthy();
    await userEvent.click(within(pills).getByRole("button", { name: /Shorts\s*1/ }));
    expect(screen.queryByRole("button", { name: /A long video\./ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /A clip\. Short from 003/ }));
    expect(getUi().view).toEqual({ kind: "episode", id: "005-short" });
  });
});

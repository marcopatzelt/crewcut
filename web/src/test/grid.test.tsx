// All episodes as cards: filter pills with counts, groups by time, a card opens its chat.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { getUi } from "../store/store";
import { episode, episodeRoutes, mockApi, resetApp, state } from "./helpers";

beforeEach(() => {
  resetApp();
  window.location.hash = "#/episodes";
});

describe("the episode grid", () => {
  it("filters with pills and opens an episode from its card", async () => {
    const long = episode({ id: "003-long", title: "A long video", open_cards: 1, cover: "demo/cover-003.svg" });
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

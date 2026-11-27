// The format system: New episode with Long, Short or Auto and a format, the pick in the episode, idea cards and the
// scoreboard (docs/formats.md).
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import type { FormatLibrary, Idea, Scoreboard } from "../api/types";
import { episode, episodeRoutes, message, mockApi, resetApp, state } from "./helpers";

beforeEach(() => resetApp());

const library: FormatLibrary = {
  enabled: true,
  problems: [],
  formats: [
    { id: "tool-test", name: "Tool test", length: "long", when: "A tool to test.", topic_types: ["manufactured"], source: "neutral" },
    { id: "claim-check", name: "Claim check", length: "short", when: "A viral claim.", topic_types: ["trending"], source: "neutral" },
  ],
};

function idea(over: Partial<Idea> = {}): Idea {
  return {
    id: "scout-a",
    source: "scout",
    url: "https://example.com/tool",
    title: "A free tool replaces a paid app",
    summary: "It claims to replace a subscription.",
    topic_type: "trending",
    suggested_format: "tool-test",
    suggestion: "rule",
    status: "open",
    ...over,
  };
}

describe("New episode", () => {
  it("sends the input with the length and the chosen format", async () => {
    window.location.hash = "#/new";
    const created = episode({ id: "002-tool", title: "A free tool" });
    const calls = mockApi({
      "GET /api/state": state(),
      "GET /api/formats": library,
      "POST /api/episodes": created,
      ...episodeRoutes(created, [message({ author: "user", text: "A free tool" })], []),
    });
    render(<App />);
    const lengths = await screen.findByRole("group", { name: "Length" });
    expect(within(lengths).getByRole("button", { name: "Auto" }).getAttribute("aria-pressed")).toBe("true");
    const formats = await screen.findByRole("group", { name: "Format" });
    expect(within(formats).getByRole("button", { name: "Crewcut picks" }).getAttribute("aria-pressed")).toBe("true");
    expect(within(formats).getByRole("button", { name: /Claim check/ })).toBeTruthy();
    // Long hides the short formats
    await userEvent.click(within(lengths).getByRole("button", { name: "Long" }));
    expect(within(screen.getByRole("group", { name: "Format" })).queryByRole("button", { name: /Claim check/ })).toBeNull();
    await userEvent.click(within(screen.getByRole("group", { name: "Format" })).getByRole("button", { name: /Tool test/ }));
    expect(screen.getByText("Tool test: A tool to test.")).toBeTruthy();
    const box = screen.getByLabelText("Message") as HTMLTextAreaElement;
    expect(box.placeholder).toBe("Paste a tool, a link, a tweet or an idea");
    await userEvent.type(box, "A free tool{Enter}");
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({ text: "A free tool", length: "long", show_format: "tool-test" }),
    );
  });

  it("keeps the old body when the user leaves everything to Crewcut", async () => {
    window.location.hash = "#/new";
    const created = episode({ id: "003-idea", title: "An idea" });
    const calls = mockApi({
      "GET /api/state": state(),
      "GET /api/formats": library,
      "POST /api/episodes": created,
      ...episodeRoutes(created, [], []),
    });
    render(<App />);
    await screen.findByRole("group", { name: "Format" });
    await userEvent.type(screen.getByLabelText("Message"), "An idea{Enter}");
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual({ text: "An idea" }));
  });

  it("shows the Scout's pick and its reason in the episode", async () => {
    const ep = episode({
      show_format: { id: "tool-test", name: "Tool test", length: "long", topic_type: "manufactured", reason: "A measurable claim about money.", runner_up: "claim-check: shorter." },
    });
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], []) });
    window.location.hash = `#/e/${ep.id}`;
    render(<App />);
    const pick = await screen.findByRole("region", { name: "Format" });
    expect(within(pick).getByText("Format: Tool test")).toBeTruthy();
    expect(within(pick).getByText("A measurable claim about money.")).toBeTruthy();
    expect(within(pick).getByText(/made for the video/)).toBeTruthy();
    expect(within(pick).getByText("Runner-up: claim-check: shorter.")).toBeTruthy();
  });
});

describe("Ideas and the scoreboard on the home", () => {
  const board: Scoreboard = {
    channel: { median_views: 1000, median_avg_view_pct: 40, subs_per_1000: 5, episodes: 4 },
    formats: [
      { format: "tool-test", name: "Tool test", length: "long", episodes: 2, measured: 2, median_views: 2000, median_avg_view_pct: 45, subs_per_1000: 10, retention_drop_per_min: null, ctr: null, verdict: "more", verdict_text: "more of this" },
      { format: "claim-check", name: "Claim check", length: "short", episodes: 1, measured: 0, median_views: null, median_avg_view_pct: null, subs_per_1000: null, retention_drop_per_min: null, ctr: 0.051, verdict: "thin", verdict_text: "too little data" },
    ],
  };

  it("starts an episode from an idea and dismisses another", async () => {
    const started = episode({ id: "004-free-tool", title: "A free tool replaces a paid app", step: "idea" });
    const calls = mockApi({
      "GET /api/state": state({ episodes: [episode()] }),
      "GET /api/ideas": [idea(), idea({ id: "braindump-b", source: "braindump", title: "My agent deleted a folder", suggested_format: null, suggestion: null })],
      "GET /api/scoreboard": board,
      "POST /api/ideas/scout-a/start": { idea: idea({ status: "started", episode: started.id }), episode: started },
      "POST /api/ideas/braindump-b/dismiss": idea({ id: "braindump-b", status: "dismissed" }),
      ...episodeRoutes(started, [], []),
    });
    window.location.hash = "#/episodes";
    render(<App />);
    const section = await screen.findByRole("region", { name: "Ideas" });
    const cards = within(section).getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]!).getByText(/Suggested format: tool-test \(a guess from keywords/)).toBeTruthy();
    expect(within(cards[1]!).getByText(/Saved link/)).toBeTruthy();
    await userEvent.click(within(cards[1]!).getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(within(section).getAllByRole("listitem")).toHaveLength(1));
    await userEvent.click(within(section).getByRole("button", { name: "Start episode" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/api/ideas/scout-a/start")).toBe(true));
    expect(await screen.findByRole("heading", { level: 1, name: "A free tool replaces a paid app" })).toBeTruthy();
  });

  it("shows one row per format with its hint and a missing CTR", async () => {
    mockApi({ "GET /api/state": state({ episodes: [episode()] }), "GET /api/ideas": [], "GET /api/scoreboard": board });
    window.location.hash = "#/episodes";
    render(<App />);
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getByText("more of this")).toBeTruthy();
    expect(within(rows[1]!).getByText("2,000")).toBeTruthy();
    expect(within(rows[1]!).getByText("missing")).toBeTruthy();
    expect(within(rows[2]!).getByText("5.1 %")).toBeTruthy();
    expect(within(rows[2]!).getByText("0 of 1")).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Ideas" })).toBeNull();
  });
});

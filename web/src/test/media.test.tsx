// The media-first views: the episode's pictures from GET /api/episodes/{id}/media (thumbnails, the cut, 3D scenes,
// the rented GPU), their empty and error states, the thumbnail pick, the GPU card's Stop, and the Episodes home.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import type { EpisodeMedia } from "../api/types";
import { STOP_GPU, choiceFor, wavePath } from "../views/EpisodeMedia";
import { card, episode, episodeRoutes, job, message, mockApi, openAt, Reply, resetApp, state } from "./helpers";

beforeEach(() => resetApp());

const ep = episode({ id: "012-site", title: "A website, 100 rounds", step: "thumbnail", open_cards: 1, seconds: 274 });

const media: EpisodeMedia = {
  thumbnails: [
    { id: "A", label: "Face right", note: "Title left", url: "a.jpg", card: 31 },
    { id: "B", label: "Face centered", url: "b.jpg", recommended: true, card: 31 },
  ],
  cut: {
    version: "v5",
    seconds: 274,
    shots: 48,
    frames: Array.from({ length: 10 }, (_, i) => ({ t: 4 + i * 27, url: `f${i}.jpg` })),
    peaks: [0.2, 0.8, 0.4, 1],
    markers: [{ t: 72, level: "note", text: "A long pause before the result." }],
    facts: ["Keywords only", "8 cuts a minute"],
  },
  scenes: {
    title: "Intro, 4K",
    done: 1,
    total: 3,
    items: [
      { id: "s1", name: "Rhine front", status: "done", progress: 1, seconds: 4, url: "s1.jpg" },
      { id: "s2", name: "Facade", status: "rendering", progress: 0.62, seconds: 3, url: "s2.jpg" },
      { id: "s3", name: "Street", status: "queued", progress: null, seconds: 3, url: null },
    ],
  },
  gpu: {
    name: "RTX 4090",
    started: new Date().toISOString(),
    minutes_left: 3,
    so_far_usd: 0.31,
    cap_usd: 1.5,
    progress: 0.78,
    delete_note: "Deleted when done, frames come home",
    session: 7,
  },
};

const thumbCard = card({
  id: 31,
  episode: ep.id,
  kind: "thumbnail",
  step: "thumbnail",
  identity: "designer",
  title: "Pick a thumbnail",
  options: ["A · Face right", "B · Face centered"],
});

describe("the episode's media", () => {
  it("shows the thumbnails, the cut with its notes, the 3D scenes and the rented GPU", async () => {
    mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], [thumbCard]),
      [`GET /api/episodes/${ep.id}/media`]: media,
    });
    openAt(ep.id);
    render(<App />);
    const variants = await screen.findByRole("radiogroup", { name: "Thumbnail variants" });
    const radios = within(variants).getAllByRole("radio");
    expect(radios).toHaveLength(2);
    expect(radios[1]?.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText("B in your feed, at phone size")).toBeTruthy();
    await userEvent.click(radios[0] as HTMLElement);
    expect(radios[0]?.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByText("A in your feed, at phone size")).toBeTruthy();

    const frames = screen.getByRole("list", { name: "Frames of the cut" });
    expect(within(frames).getAllByRole("img")).toHaveLength(10);
    expect(within(frames).getByAltText("Frame at 1:25").closest("li")?.className).toContain("mark-note");
    expect(within(screen.getByRole("list", { name: "Notes from the Critic" })).getByText(/1:12: A long pause/)).toBeTruthy();
    expect(screen.getByText("Cut v5")).toBeTruthy();
    expect(screen.getByText("Keywords only")).toBeTruthy();

    const scenes = screen.getByRole("list", { name: "Scenes" });
    expect(within(scenes).getByText("Facade, 62 %")).toBeTruthy();
    expect(within(scenes).getByText("Street, queued")).toBeTruthy();
    expect(within(scenes).getAllByRole("img")).toHaveLength(2);

    const gpu = screen.getByRole("region", { name: "Rented RTX 4090" });
    expect(within(gpu).getByText("3 min")).toBeTruthy();
    expect(within(gpu).getByText("$0.31")).toBeTruthy();
    expect(within(gpu).getByText("$1.50")).toBeTruthy();
    expect(within(gpu).getByRole("progressbar").getAttribute("aria-valuenow")).toBe("78");
    expect(within(gpu).getByText("Deleted when done, frames come home")).toBeTruthy();
  });

  it("sends the pick of a thumbnail as the yes on its card", async () => {
    const calls = mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], [thumbCard]),
      [`GET /api/episodes/${ep.id}/media`]: media,
      "POST /api/cards/31/accept": (c: { body: unknown }) => ({
        ...thumbCard,
        status: "accepted",
        choice: (c.body as { choice: number }).choice,
      }),
    });
    openAt(ep.id);
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Use A" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toEqual({ method: "POST", path: "/api/cards/31/accept", body: { choice: 0 } }),
    );
    expect(await screen.findByText("Thumbnail approved · A · Face right")).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Use A" })).toBeNull());
  });

  it("asks the crew in the chat to stop the rented GPU", async () => {
    const calls = mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], []),
      [`GET /api/episodes/${ep.id}/media`]: { ...media, thumbnails: [] },
      [`POST /api/episodes/${ep.id}/messages`]: (c: { body: unknown }) =>
        message({ id: 60, author: "user", text: (c.body as { text: string }).text }),
    });
    openAt(ep.id);
    render(<App />);
    const gpu = await screen.findByRole("region", { name: "Rented RTX 4090" });
    await userEvent.click(within(gpu).getByRole("button", { name: "Stop" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toEqual({
        method: "POST",
        path: `/api/episodes/${ep.id}/messages`,
        body: { text: STOP_GPU },
      }),
    );
    expect(await within(gpu).findByText(/Asked the crew to stop it/)).toBeTruthy();
    expect(await screen.findByText(STOP_GPU)).toBeTruthy();
  });

  it("says so honestly when an episode has no pictures yet, also on a server without the media route", async () => {
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], []) });
    openAt(ep.id);
    render(<App />);
    expect(
      await screen.findByText("No pictures yet. Thumbnails, the cut and renders show here as the crew makes them."),
    ).toBeTruthy();
    expect(screen.queryByRole("radiogroup", { name: "Thumbnail variants" })).toBeNull();
    expect(within(screen.getByRole("main", { name: ep.title })).queryByRole("img")).toBeNull();
  });

  it("keeps the strip honest while the frames are made, and shows a media error with retry", async () => {
    let fail = true;
    mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], []),
      [`GET /api/episodes/${ep.id}/media`]: () => {
        if (fail) {
          fail = false;
          return new Reply(500, { detail: "The media folder is locked." });
        }
        return { thumbnails: [], scenes: null, gpu: null, cut: { ...media.cut, frames: [], peaks: [], pending: true } };
      },
    });
    openAt(ep.id);
    render(<App />);
    expect(await screen.findByText("Couldn't load the pictures of this episode. The media folder is locked.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Frames come as soon as the cut is read.")).toBeTruthy();
    expect(screen.getByText("The strip and the waveform are on their way.")).toBeTruthy();
  });

  it("matches a variant to its card option and draws the waveform from the peaks", () => {
    expect(choiceFor(thumbCard, media.thumbnails, media.thumbnails[1]!)).toBe(1);
    expect(choiceFor(undefined, media.thumbnails, media.thumbnails[0]!)).toBe(0);
    expect(wavePath([])).toBe("");
    expect(wavePath([0.5, 1]).match(/M/g)).toHaveLength(2);
  });
});

describe("the Episodes home", () => {
  const short = episode({
    id: "s9-clip",
    title: "Make it better, 100 times",
    kind: "short",
    mode: "clip",
    source_episode: ep.id,
    steps: ["idea", "title", "edit", "thumbnail", "upload", "results"].map((id, i) => ({
      id,
      n: i + 1,
      label: id,
      status: "done" as const,
    })),
    step: "results",
    cover: "s9.jpg",
  });
  const published = episode({
    id: "011-local",
    title: "Local AI is enough",
    step: "results",
    steps: episode().steps.map((s) => ({ ...s, status: "done" as const })),
    cover: "011.jpg",
    seconds: 262,
  });
  const inWork = episode({ id: "014-private", title: "Local AI, privately", step: "edit", cover: "014.jpg" });
  const needs = { ...ep, cover: "012.jpg", needs: { card: 31, kind: "thumbnail", title: "Pick a thumbnail", images: ["a.jpg", "b.jpg"] } };

  it("shows what needs you large, the long videos as thumbnails and the Shorts in 9:16", async () => {
    mockApi({
      "GET /api/state": state({
        episodes: [needs, inWork, published, short],
        activity: [job(1, { episode: inWork.id, identity: "editor", step: "edit" })],
      }),
    });
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Episodes" })).toBeTruthy();
    expect(screen.getByText("One needs your yes. Everything else is moving.")).toBeTruthy();
    const need = within(screen.getByRole("region", { name: "Needs you" })).getByRole("button", {
      name: /^A website, 100 rounds\. Episode 012.*Needs your yes\.$/,
    });
    expect(within(need).getByText("Pick a thumbnail")).toBeTruthy();
    expect(within(need).getByText("4:34")).toBeTruthy();
    const grid = screen.getByRole("region", { name: "In work and published" });
    expect(within(grid).getByText("Editor is cutting, 6 of 10")).toBeTruthy();
    expect(within(grid).getByText("4:22")).toBeTruthy();
    expect(within(grid).getByText(/^Published/)).toBeTruthy();
    expect(within(grid).getByText("In work, step 6 of 10")).toBeTruthy();
    const shorts = screen.getByRole("region", { name: "Shorts" });
    expect(within(shorts).getByText("Make it better, 100 times")).toBeTruthy();
    expect(screen.getByText("1 made from one episode")).toBeTruthy();
    // "Import footage" goes into the episode at the edit step
    expect(screen.getByRole("button", { name: "Import footage" })).toBeTruthy();
  });

  it("filters by the sidebar's Shorts and by the pills, and a card opens its episode", async () => {
    mockApi({
      "GET /api/state": state({ episodes: [needs, published, short] }),
      ...episodeRoutes(published, [], []),
    });
    render(<App />);
    const places = await screen.findByRole("navigation", { name: "Places" });
    await waitFor(() => expect(within(places).getByRole("button", { name: /Shorts\s*1/ })).toBeTruthy());
    await userEvent.click(within(places).getByRole("button", { name: /Shorts\s*1/ }));
    expect(window.location.hash).toBe("#/episodes/shorts");
    expect(screen.queryByRole("region", { name: "Needs you" })).toBeNull();
    expect(screen.getByRole("region", { name: "Shorts" })).toBeTruthy();
    const pills = screen.getByRole("group", { name: "Show" });
    await userEvent.click(within(pills).getByRole("button", { name: /Published\s*2/ }));
    await userEvent.click(screen.getByRole("button", { name: /^Local AI is enough\./ }));
    expect(await screen.findByRole("heading", { level: 1, name: "Local AI is enough" })).toBeTruthy();
    expect(window.location.hash).toBe("#/e/011-local");
  });

  it("starts empty with one line and the button for a new episode", async () => {
    mockApi({ "GET /api/state": state({ episodes: [] }) });
    window.history.replaceState(null, "", "/#/episodes");
    render(<App />);
    expect(await screen.findByText("No episodes yet. Start one with New episode.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "New episode" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "Needs you" })).toBeNull();
  });
});

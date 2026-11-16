// Shorts in the app: a portrait sign and the source episode in the list, only the steps a clip has, and the quiet
// second choice on a Short's publish card (the user's own standing approval).
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { acceptLabel } from "../components/CardView";
import { card, episode, episodeRoutes, mockApi, resetApp, state } from "./helpers";

beforeEach(() => resetApp());

const clipSteps = ["idea", "title", "edit", "thumbnail", "upload", "results"].map((id, i) => ({
  id,
  n: i + 1,
  label: id.charAt(0).toUpperCase() + id.slice(1),
  status: i < 2 ? ("done" as const) : i === 2 ? ("working" as const) : ("open" as const),
}));

describe("Shorts", () => {
  it("shows a clip with its source and only its six steps", async () => {
    const short = episode({
      id: "005-clip",
      title: "Five models, one laptop",
      step: "edit",
      steps: clipSteps,
      kind: "short",
      mode: "clip",
      source_episode: "003-local-llms",
    });
    mockApi({ "GET /api/state": state({ episodes: [short] }), ...episodeRoutes(short, [], []) });
    render(<App />);
    const list = await screen.findByRole("navigation", { name: "Episodes" });
    expect(within(list).getByText(/Short from 003/)).toBeTruthy();
    expect(await screen.findByText(/3 of 6 · Edit/)).toBeTruthy();
  });

  it("offers the standing approval only on a Short's publish card, and lets a card name its action", async () => {
    const short = episode({ id: "005-clip", title: "Clip", kind: "short", mode: "clip", source_episode: "003-x" });
    const publish = card({ id: 21, episode: short.id, kind: "publish", step: "upload", title: "Publish now",
      data: { standing_offer: true }, options: null });
    mockApi({ "GET /api/state": state({ episodes: [short] }), ...episodeRoutes(short, [], [publish]) });
    render(<App />);
    expect(await screen.findByRole("button", { name: "Publish this and all future Shorts without asking" })).toBeTruthy();
    expect(acceptLabel(card({ kind: "script", data: { button: "This really happened" } }))).toBe("This really happened");
    expect(acceptLabel(card({ kind: "spend", data: { button: "Free money" } }))).not.toBe("Free money");
  });
});

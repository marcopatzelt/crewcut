// "Make a Short" starts a Short in clip mode from this episode; the Scout's new job shows up in Working now.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { SHORT_STARTED } from "../components/TitleBar";
import { episode, episodeRoutes, job, mockApi, resetApp, state } from "./helpers";

beforeEach(() => resetApp());

describe("Make a Short", () => {
  it("starts the clip Short and its Scout job appears in Working now", async () => {
    const ep = episode({ id: "012-website", title: "Claude improves a website 100 times" });
    let started = false;
    const scout = job(41, { identity: "scout", episode: "017-short-website", step: "idea", doing: "Finding passages that stand on their own", progress: null });
    const calls = mockApi({
      "GET /api/state": () => state({ episodes: [ep], activity: started ? [scout] : [] }),
      ...episodeRoutes(ep, [], []),
      [`POST /api/episodes/${ep.id}/shorts`]: () => {
        started = true;
        return { episode: "017-short-website", job: 41 };
      },
    });
    window.location.hash = `#/e/${ep.id}`;
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "Make a Short" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === `/api/episodes/${ep.id}/shorts`)).toBe(true));
    expect(await screen.findByText(SHORT_STARTED)).toBeTruthy();
    // the new job belongs to the new Short: in this episode's crew column it is the line for other episodes
    expect(await screen.findByText(/One more job on other episodes/, {}, { timeout: 3000 })).toBeTruthy();
    // and in the home's Working now it is a full row with what it does
    window.location.hash = "#/episodes";
    expect(await screen.findByText(/Finding passages that stand on their own/, {}, { timeout: 3000 })).toBeTruthy();
  });
});

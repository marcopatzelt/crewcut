// States from DESIGN.md rule 11 (empty, loading, error, long content), the card accept call and the composer.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { card, episode, episodeRoutes, job, message, mockApi, NEVER, Reply, resetApp, state } from "./helpers";

beforeEach(() => {
  resetApp();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("loading", () => {
  it("keeps the three places and shows the spinner only after 300 ms", async () => {
    mockApi({ "GET /api/state": NEVER });
    render(<App />);
    expect(screen.getByRole("complementary", { name: "Episodes" })).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "Working now" })).toBeTruthy();
    expect(screen.getByLabelText("Message")).toBeTruthy();
    const loading = screen.getByTestId("loading");
    expect(loading.querySelector("svg")).toBeNull();
    await waitFor(() => expect(screen.getByTestId("loading").querySelector("svg")).not.toBeNull(), { timeout: 1000 });
  });
});

describe("empty", () => {
  it("says there are no episodes and nobody is working", async () => {
    mockApi({ "GET /api/state": state() });
    render(<App />);
    expect(await screen.findByText("No episodes yet.")).toBeTruthy();
    expect(screen.getByText("No episodes yet. Say an idea below.")).toBeTruthy();
    const crew = screen.getByRole("complementary", { name: "Working now" });
    expect(within(crew).getByText("Nobody is working. Nothing is running, nothing costs money.")).toBeTruthy();
    expect(within(crew).getByText("$0.00 of $20")).toBeTruthy();
  });

  it("asks for links when the user is not onboarded, and sends them to the onboarding chat", async () => {
    const calls = mockApi({
      "GET /api/state": state({ app: { ...state().app, onboarded: false } }),
      "GET /api/episodes/_onboarding/messages": [],
      "GET /api/cards": [],
      "POST /api/episodes/_onboarding/messages": (c: { body: unknown }) =>
        message({ id: 9, author: "user", text: (c.body as { text: string }).text }),
    });
    render(<App />);
    expect(await screen.findByText("Paste your links.")).toBeTruthy();
    const box = screen.getByLabelText("Message") as HTMLTextAreaElement;
    expect(box.placeholder).toBe("Paste your links.");
    await userEvent.type(box, "https://example.com and https://youtube.com/@example{Enter}");
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toEqual({
        method: "POST",
        path: "/api/episodes/_onboarding/messages",
        body: { text: "https://example.com and https://youtube.com/@example" },
      }),
    );
    expect(await screen.findByText("https://example.com and https://youtube.com/@example")).toBeTruthy();
  });
});

describe("error", () => {
  it("shows the error inline and loads again on retry", async () => {
    const ep = episode();
    let first = true;
    mockApi({
      "GET /api/state": () => {
        if (first) {
          first = false;
          return new Reply(500, { detail: "The database is locked." });
        }
        return state({ episodes: [ep] });
      },
      ...episodeRoutes(ep, [message({ text: "Script version 1 is ready." })], []),
    });
    render(<App />);
    expect(await screen.findByText("Couldn't load Crewcut. The database is locked.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Script version 1 is ready.")).toBeTruthy();
  });

  it("shows a chat error with retry when the messages fail", async () => {
    const ep = episode();
    let fail = true;
    mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], []),
      [`GET /api/episodes/${ep.id}/messages`]: () => {
        if (fail) {
          fail = false;
          return new Reply(503, { detail: "The conductor is restarting." });
        }
        return [message({ text: "Back again." })];
      },
    });
    render(<App />);
    expect(await screen.findByText("Couldn't load the chat. The conductor is restarting.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Back again.")).toBeTruthy();
  });

  it("falls back to demo data when no API answers", async () => {
    mockApi({ "GET /api/state": new TypeError("Failed to fetch") });
    render(<App />);
    expect(await screen.findByText("Demo data. Crewcut is not running at this address.")).toBeTruthy();
    expect((await screen.findAllByText("I ran five local AI models on a $900 laptop")).length).toBeGreaterThan(0);
  });

  it("says when the engine is not logged in", async () => {
    mockApi({ "GET /api/state": state({ app: { ...state().app, engine_ok: false } }) });
    render(<App />);
    const crew = screen.getByRole("complementary", { name: "Working now" });
    expect(await within(crew).findByText(/Claude Code is not logged in\. Run claude setup-token/)).toBeTruthy();
  });
});

describe("long content", () => {
  it("truncates a 90-character title and keeps the full text in the title attribute", async () => {
    const title = "A".repeat(40) + " " + "B".repeat(49);
    expect(title.length).toBe(90);
    const ep = episode({ title });
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], []) });
    render(<App />);
    const heading = await screen.findByRole("heading", { level: 1, name: title });
    expect(heading.getAttribute("title")).toBe(title);
    expect(heading.className).toContain("one-line");
    const row = screen.getByRole("button", { name: new RegExp(`^${title}`) });
    expect(row.getAttribute("title")).toBe(title);
  });

  it("renders a 4,000-word script message", async () => {
    const ep = episode();
    const words = Array.from({ length: 4000 }, (_, i) => (i % 120 === 119 ? "word.\n\n" : "word")).join(" ");
    mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [message({ author: "showrunner", text: words })], []),
    });
    render(<App />);
    const chat = await screen.findByRole("log", { name: "Chat" });
    const count = () =>
      Array.from(chat.querySelectorAll(".txt p"))
        .map((p) => (p.textContent ?? "").split(/\s+/).filter((w) => w.startsWith("word")).length)
        .reduce((a, b) => a + b, 0);
    await waitFor(() => expect(count()).toBe(4000));
    expect(chat.querySelectorAll("p").length).toBeGreaterThan(30);
  });

  it("lists a crew of 30 jobs, each with its own row", async () => {
    const ep = episode();
    const activity = Array.from({ length: 30 }, (_, i) => job(i + 1));
    mockApi({ "GET /api/state": state({ episodes: [ep], activity }), ...episodeRoutes(ep, [], []) });
    render(<App />);
    const crew = await screen.findByRole("complementary", { name: "Working now" });
    await waitFor(() => expect(within(crew).getAllByRole("button", { name: /Open the log/ }).length).toBe(30));
    expect(within(crew).getByText("One of the crew is on this episode.")).toBeTruthy();
  });
});

describe("cards", () => {
  it("accepts the chosen option and folds the card", async () => {
    const ep = episode({ open_cards: 1 });
    const open = card();
    const calls = mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [message({ author: "scout", text: "Three titles below." })], [open]),
      "POST /api/cards/4/accept": (c: { body: unknown }) => ({
        ...open,
        status: "accepted",
        choice: (c.body as { choice: number }).choice,
      }),
    });
    render(<App />);
    const group = await screen.findByRole("group", { name: "Pick a title" });
    await userEvent.click(within(group).getByRole("radio", { name: /Second title/ }));
    await userEvent.click(within(group).getByRole("button", { name: "Use this title" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toEqual({
        method: "POST",
        path: "/api/cards/4/accept",
        body: { choice: 1 },
      }),
    );
    expect(await screen.findByText("Title approved · Second title")).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Pick a title" })).toBeNull();
  });

  it("accepts the open card in view with Ctrl+Enter", async () => {
    const ep = episode({ open_cards: 1 });
    const open = card({ options: null, kind: "script", title: "Approve the script", file: "brief/SCRIPT-v002.md" });
    const calls = mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], [open]),
      "POST /api/cards/4/accept": { ...open, status: "accepted" },
    });
    render(<App />);
    await screen.findByRole("group", { name: "Approve the script" });
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    await waitFor(() => expect(calls.some((c) => c.path === "/api/cards/4/accept")).toBe(true));
    expect(await screen.findByText("Script approved · version 2")).toBeTruthy();
  });

  it("shows both ways and the referral note on a spend card", async () => {
    const ep = episode({ open_cards: 1 });
    const spend = card({
      kind: "spend",
      step: "edit",
      identity: "editor",
      title: "Render the 3D scenes on a rented GPU?",
      options: null,
      amount_usd: 0.6,
      data: {
        local_seconds: 11_400,
        rented_seconds: 720,
        rented_usd: 0.6,
        cap_usd: 1.5,
        gpus: 1,
        gpu_name: "RTX 4090",
        referral: { url: "https://cloud.vast.ai/?ref_id=test", note: "Referral link: test note." },
      },
    });
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], [spend]) });
    render(<App />);
    const group = await screen.findByRole("group", { name: "Render the 3D scenes on a rented GPU?" });
    expect(within(group).getByText("On this machine")).toBeTruthy();
    expect(within(group).getByText("About 3 h 10 min")).toBeTruthy();
    expect(within(group).getByText("About 12 min")).toBeTruthy();
    expect(within(group).getByRole("button", { name: "Rent a GPU for $0.60" })).toBeTruthy();
    expect(within(group).getByText(/Referral link: test note\./)).toBeTruthy();
  });

  it("shows an inline error with retry when the yes cannot be sent", async () => {
    const ep = episode({ open_cards: 1 });
    mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], [card()]),
      "POST /api/cards/4/accept": new Reply(409, { detail: "The card was already decided." }),
    });
    render(<App />);
    const group = await screen.findByRole("group", { name: "Pick a title" });
    await userEvent.click(within(group).getByRole("button", { name: "Use this title" }));
    expect(await within(group).findByText("Couldn't send your yes. The card was already decided.")).toBeTruthy();
    expect(within(group).getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});

describe("composer", () => {
  it("sends with Enter and keeps Shift+Enter as a new line", async () => {
    const ep = episode();
    const calls = mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], []),
      [`POST /api/episodes/${ep.id}/messages`]: (c: { body: unknown }) =>
        message({ id: 50, author: "user", text: (c.body as { text: string }).text }),
    });
    render(<App />);
    await screen.findByRole("log", { name: "Chat" });
    const box = screen.getByLabelText("Message") as HTMLTextAreaElement;
    await userEvent.type(box, "Shorter intro{Shift>}{Enter}{/Shift}please");
    expect(box.value).toBe("Shorter intro\nplease");
    expect(calls.some((c) => c.method === "POST")).toBe(false);
    await userEvent.keyboard("{Enter}");
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toEqual({
        method: "POST",
        path: `/api/episodes/${ep.id}/messages`,
        body: { text: "Shorter intro\nplease" },
      }),
    );
    await waitFor(() => expect(box.value).toBe(""));
    expect(screen.getByText(/Shorter intro/)).toBeTruthy();
  });

  it("starts a new episode when none is selected", async () => {
    const created = episode({ id: "002-new", title: "Local models on a phone" });
    const calls = mockApi({
      "GET /api/state": state(),
      "POST /api/episodes": created,
      ...episodeRoutes(created, [message({ author: "user", text: "Local models on a phone" })], []),
    });
    render(<App />);
    await screen.findByText("No episodes yet. Say an idea below.");
    await userEvent.type(screen.getByLabelText("Message"), "Local models on a phone{Enter}");
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toEqual({
        method: "POST",
        path: "/api/episodes",
        body: { text: "Local models on a phone" },
      }),
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Local models on a phone" })).toBeTruthy();
  });

  it("keeps the text and says so when sending fails", async () => {
    const ep = episode();
    mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], []),
      [`POST /api/episodes/${ep.id}/messages`]: new Reply(500, { detail: "The server is busy." }),
    });
    render(<App />);
    await screen.findByRole("log", { name: "Chat" });
    const box = screen.getByLabelText("Message") as HTMLTextAreaElement;
    await userEvent.type(box, "Hello{Enter}");
    expect(await screen.findByText("Couldn't send. The server is busy.")).toBeTruthy();
    expect(box.value).toBe("Hello");
  });

  it("hides the microphone when the browser has no speech input", async () => {
    mockApi({ "GET /api/state": state() });
    render(<App />);
    await screen.findByText("No episodes yet.");
    expect(screen.queryByRole("button", { name: "Speak" })).toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeTruthy();
  });
});

describe("live updates", () => {
  it("applies a card event to the episode row", async () => {
    const ep = episode();
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], []) });
    const { applyEvent } = await import("../store/actions");
    render(<App />);
    await screen.findByRole("log", { name: "Chat" });
    act(() => applyEvent("card", card()));
    expect(await screen.findByRole("group", { name: "Pick a title" })).toBeTruthy();
    expect(screen.getByText(", needs your yes")).toBeTruthy();
  });
});

// States from DESIGN.md rule 11 (empty, loading, error, long content), the card accept call and the composer.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from "vitest";
import { App } from "../App";
import { navigate, START_WAIT_MS } from "../store/actions";
import { getUi } from "../store/store";
import { card, episode, episodeRoutes, job, message, mockApi, NEVER, openAt, Reply, resetApp, state } from "./helpers";

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
    expect(screen.getByRole("navigation", { name: "Places" })).toBeTruthy();
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
    window.location.hash = "#/new";
    render(<App />);
    expect(await screen.findByText("No episodes yet. Say an idea below.")).toBeTruthy();
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
    openAt(ep.id);
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
    openAt(ep.id);
    render(<App />);
    expect(await screen.findByText("Couldn't load the chat. The conductor is restarting.")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Back again.")).toBeTruthy();
  });

  it("says Crewcut is starting while no API answers, then that it can't reach the engine, and never makes up content", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const calls = mockApi({ "GET /api/state": new TypeError("Failed to fetch") });
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Crewcut is starting…" })).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "Places" })).toBeNull();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(calls.filter((c) => c.path === "/api/state").length).toBeGreaterThan(3); // it keeps asking
    await vi.advanceTimersByTimeAsync(START_WAIT_MS);
    expect(await screen.findByRole("heading", { level: 1, name: "Can't reach the Crewcut engine" })).toBeTruthy();
    expect(screen.getByText(/Check that Docker is running and Crewcut is started/)).toBeTruthy();
    expect(screen.queryByText(/Claude improves a website/)).toBeNull();
    expect(screen.queryByText(/demo/i)).toBeNull();
    // the engine is up again: one press loads the real state
    mockApi({ "GET /api/state": state(), "GET /api/profile": {} });
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(getUi().boot).toBe("ready"));
    vi.useRealTimers();
  });

  it("a page that is not Crewcut, or a proxy without the server, counts as not answering", async () => {
    mockApi({ "GET /api/state": new Reply(502, "<h1>Bad gateway</h1>", "text/html") });
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Crewcut is starting…" })).toBeTruthy();
  });

  it("says when Claude is not connected, and Connect Claude leads to the sign-in", async () => {
    mockApi({ "GET /api/state": state({ app: { ...state().app, engine_ok: false } }) });
    render(<App />);
    const crew = screen.getByRole("complementary", { name: "Working now" });
    expect(await within(crew).findByText(/Claude is not connected\./)).toBeTruthy();
    await userEvent.click(within(crew).getByRole("button", { name: "Connect Claude" }));
    await waitFor(() => expect(window.location.hash).toBe("#/onboarding"));
    expect(await screen.findByRole("group", { name: "Connect Claude" })).toBeTruthy();
  });
});

describe("Connect Claude", () => {
  const notConnected = () => state({ app: { ...state().app, engine_ok: false, onboarded: false } });

  it("opens Claude's sign-in in a new tab, takes the code in one field and says who is connected", async () => {
    const tab = { opener: {}, location: { href: "" }, close: vi.fn() };
    vi.stubGlobal("open", vi.fn(() => tab));
    let connected = false;
    const calls = mockApi({
      "GET /api/state": () => state({ app: { ...state().app, engine_ok: connected, onboarded: false } }),
      "GET /api/episodes/_onboarding/messages": [],
      "GET /api/cards": [],
      "POST /api/engine/claude/connect": { url: "https://claude.ai/oauth/authorize?code=true&state=s" },
      "POST /api/engine/claude/code": (c: { body: unknown }) => {
        if ((c.body as { code: string }).code !== "abcdefgh#s") return new Reply(400, { detail: "That does not look like the code." });
        connected = true;
        return { connected: true, account: { email: "me@example.org" } };
      },
    });
    window.history.replaceState(null, "", "/#/onboarding");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Connect Claude first." })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Connect Claude" }));
    const field = await screen.findByRole("textbox", { name: "Code from Claude's page" });
    expect(tab.location.href).toBe("https://claude.ai/oauth/authorize?code=true&state=s");
    expect(tab.opener).toBeNull();
    await userEvent.type(field, "wrong-code{Enter}");
    expect(await screen.findByText("That does not look like the code.")).toBeTruthy();
    await userEvent.clear(field);
    await userEvent.type(field, "abcdefgh#s");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText("Claude is connected as me@example.org. Paste your links below.")).toBeTruthy();
    expect(calls.filter((c) => c.path === "/api/engine/claude/code")).toHaveLength(2);
  });

  it("in the desktop app: the field comes with the link, the app keeps the token, a refused code says so", async () => {
    let tries = 0;
    const claudeBegin = vi.fn(async () => ({ url: "https://claude.ai/oauth/authorize?code=true&state=s" }));
    const claudeCode = vi.fn(async (code: string) => {
      tries += 1;
      return tries === 1
        ? { connected: false, text: "Claude did not accept the code. Claude Code says: OAuth error: Invalid code" }
        : { connected: code === "abcdefgh#s", account: { email: "me@example.org" } };
    });
    const cancelSignIn = vi.fn(async () => undefined);
    Object.assign(window, {
      crewcutDesktop: { platform: "linux", connect: vi.fn(), openSettings: vi.fn(), setTheme: vi.fn(), claudeBegin, claudeCode,
        cancelSignIn },
    });
    onTestFinished(() => {
      delete (window as Window & { crewcutDesktop?: unknown }).crewcutDesktop;
    });
    vi.stubGlobal("open", vi.fn());
    const calls = mockApi({
      "GET /api/state": notConnected(),
      "GET /api/episodes/_onboarding/messages": [],
      "GET /api/cards": [],
    });
    window.history.replaceState(null, "", "/#/onboarding");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Connect Claude first." })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Connect Claude" }));
    let field = await screen.findByRole("textbox", { name: "Code from Claude's page" });
    expect(window.open).not.toHaveBeenCalled(); // the app opened Claude's page in the browser itself
    await userEvent.type(field, "wrongcode#s{Enter}");
    expect(await screen.findByText(/Claude did not accept the code\. Claude Code says: OAuth error: Invalid code/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Start again" }));
    expect(cancelSignIn).toHaveBeenCalledTimes(2); // each start ends an older sign-in first
    field = await screen.findByRole("textbox", { name: "Code from Claude's page" });
    await userEvent.type(field, "  abcdefgh#s \n");
    await userEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(await screen.findByText(/Claude is connected as me@example.org/)).toBeTruthy();
    expect(claudeCode).toHaveBeenLastCalledWith("abcdefgh#s");
    expect(calls.some((c) => c.path.startsWith("/api/engine/"))).toBe(false);
  });

  it("Codex (beta): the device link and code, then connected", async () => {
    let done = false;
    mockApi({
      "GET /api/state": notConnected(),
      "GET /api/episodes/_onboarding/messages": [],
      "GET /api/cards": [],
      "POST /api/engine/codex/connect": { status: "waiting", url: "https://auth.openai.com/codex/device", code: "ABCD-1234" },
      "GET /api/engine/login": () => ({
        claude: { installed: true, connected: false, source: null, signing_in: false },
        codex: { installed: true, connected: done },
        chosen: "claude",
      }),
    });
    window.history.replaceState(null, "", "/#/onboarding");
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Connect Claude first." })).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Sign in to Codex" }));
    expect(await screen.findByText("ABCD-1234")).toBeTruthy();
    done = true; // the page asks every 3 s
    expect(await screen.findByText("Codex is connected.", {}, { timeout: 5000 })).toBeTruthy();
  });
});

describe("long content", () => {
  it("truncates a 90-character title and keeps the full text in the title attribute", async () => {
    const title = "A".repeat(40) + " " + "B".repeat(49);
    expect(title.length).toBe(90);
    const ep = episode({ title });
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], []) });
    openAt(ep.id);
    render(<App />);
    const heading = await screen.findByRole("heading", { level: 1, name: title });
    expect(heading.getAttribute("title")).toBe(title);
    expect(heading.className).toContain("one-line");
    // On the home its card names it in full, and the clamped title keeps the full text too.
    act(() => navigate({ kind: "episodes" }));
    const cardButton = await screen.findByRole("button", { name: new RegExp(`^${title}`) });
    expect(cardButton.querySelector(".ep-card-title")?.getAttribute("title")).toBe(title);
  });

  it("renders a 4,000-word script message", async () => {
    const ep = episode();
    const words = Array.from({ length: 4000 }, (_, i) => (i % 120 === 119 ? "word.\n\n" : "word")).join(" ");
    mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [message({ author: "showrunner", text: words })], []),
    });
    openAt(ep.id);
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
    openAt(ep.id);
    render(<App />);
    const crew = await screen.findByRole("region", { name: "Crew chat" });
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
    openAt(ep.id);
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
    openAt(ep.id);
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
    openAt(ep.id);
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
    openAt(ep.id);
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
    openAt(ep.id);
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

  it("starts a new episode only from New", async () => {
    window.location.hash = "#/new";
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
    openAt(ep.id);
    render(<App />);
    await screen.findByRole("log", { name: "Chat" });
    const box = screen.getByLabelText("Message") as HTMLTextAreaElement;
    await userEvent.type(box, "Hello{Enter}");
    expect(await screen.findByText("Couldn't send. The server is busy.")).toBeTruthy();
    expect(box.value).toBe("Hello");
  });

  it("hides the microphone when the browser has no speech input", async () => {
    mockApi({ "GET /api/state": state() });
    window.location.hash = "#/new";
    render(<App />);
    await screen.findByText("No episodes yet. Say an idea below.");
    expect(screen.queryByRole("button", { name: "Speak" })).toBeNull();
    expect(screen.getByRole("button", { name: "Send" })).toBeTruthy();
  });
});

describe("live updates", () => {
  it("applies a card event to the chat and to the episode's count", async () => {
    const ep = episode();
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], []) });
    const { applyEvent } = await import("../store/actions");
    openAt(ep.id);
    render(<App />);
    await screen.findByRole("log", { name: "Chat" });
    act(() => applyEvent("card", card()));
    expect(await screen.findByRole("group", { name: "Pick a title" })).toBeTruthy();
    expect(getUi().state?.episodes[0]?.open_cards).toBe(1);
  });
});

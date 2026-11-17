// The states of the floating layout (DESIGN.md rule 11 and the empty, loading and error lines), the step dots,
// the spend card's two ways, the command palette and shortcuts (rule 15), and the scripted demo for the README.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { foldedText, suggestedWay } from "../components/CardView";
import { matches } from "../components/Palette";
import { keyLabels } from "../lib/platform";
import { getUi, setUi } from "../store/store";
import { engineWords } from "../views/ReadOnlyViews";
import { card, episode, episodeRoutes, job, message, mockApi, openAt, resetApp, state } from "./helpers";

beforeEach(() => {
  resetApp();
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
  delete window.__crewcutPlayDone;
});

const spendCard = (local: number) =>
  card({
    id: 9,
    kind: "spend",
    step: "edit",
    identity: "editor",
    title: "Render the 3D scenes on a rented GPU?",
    options: null,
    file: "edit/plan-v001.json",
    amount_usd: 0.6,
    data: { local_seconds: local, rented_seconds: 720, rented_usd: 0.6, cap_usd: 1.5, gpus: 1, gpu_name: "RTX 4090" },
  });

describe("empty and error states", () => {
  it("first start: the mark, one sentence and the composer, no toolbar", async () => {
    mockApi({
      "GET /api/state": state({ app: { ...state().app, onboarded: false } }),
      "GET /api/episodes/_onboarding/messages": [],
      "GET /api/cards": [],
    });
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Paste your links." })).toBeTruthy();
    expect(screen.getByText("Website, YouTube channel, socials. The crew reads the rest.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Search episodes/ })).toBeNull();
    expect(document.querySelector(".dock")?.className).toContain("centered");
  });

  it("an episode without messages shows its large title and one sentence", async () => {
    const ep = episode({ title: "Local models on a phone" });
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], []) });
    openAt(ep.id);
    render(<App />);
    expect(await screen.findByRole("heading", { level: 1, name: "Local models on a phone" })).toBeTruthy();
    expect(await screen.findByText("Say an idea below, or ask the Scout for three.")).toBeTruthy();
  });

  it("says that nothing runs and nothing costs money, with the money in quiet ink", async () => {
    mockApi({ "GET /api/state": state() });
    render(<App />);
    const crew = await screen.findByRole("complementary", { name: "Working now" });
    expect(await within(crew).findByText("Nobody is working. Nothing is running, nothing costs money.")).toBeTruthy();
    expect(within(crew).getByTestId("money").className).toContain("zero");
  });

  it("shows the engine line in the Crew column with a warn dot", async () => {
    mockApi({ "GET /api/state": state({ app: { ...state().app, engine_ok: false } }) });
    render(<App />);
    const crew = await screen.findByRole("complementary", { name: "Working now" });
    const line = await within(crew).findByRole("alert");
    expect(line.textContent).toContain("Claude Code is not logged in.");
    expect(line.querySelector(".dot.warn")).not.toBeNull();
  });

  it("says when the connection to the container is lost", async () => {
    mockApi({ "GET /api/state": state() });
    render(<App />);
    await screen.findByText("No episodes yet. Say an idea below.");
    act(() => setUi({ live: "retrying" }));
    expect(screen.getByRole("status", { name: "" }).textContent).toContain(
      "Lost the connection to the container. Retrying…",
    );
  });

  it("a preview keeps its place while it loads and shows the shimmer only after 300 ms", async () => {
    const ep = episode();
    mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [message({ author: "editor", text: "Frame below.", preview: "review/frame.png" })], []),
    });
    openAt(ep.id);
    render(<App />);
    const box = await screen.findByTestId("media");
    expect(box.getAttribute("data-state")).toBe("waiting");
    await waitFor(() => expect(box.getAttribute("data-state")).toBe("loading"), { timeout: 1000 });
    fireEvent.load(box.querySelector("img") as HTMLImageElement);
    expect(box.getAttribute("data-state")).toBe("ready");
  });

  it("a broken preview says where the file is and can try again", async () => {
    const ep = episode();
    mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [message({ author: "editor", text: "Frame below.", preview: "review/frame.png" })], []),
    });
    openAt(ep.id);
    render(<App />);
    const box = await screen.findByTestId("media");
    fireEvent.error(box.querySelector("img") as HTMLImageElement);
    expect(
      await screen.findByText("Couldn't load the preview. The file is at episodes/001-test/review/frame.png."),
    ).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("media")).toBeTruthy();
  });
});

describe("the steps and the shortcuts", () => {
  it("lists ten steps, marks the current one and names done steps with their approval", async () => {
    const ep = episode({ open_cards: 0 });
    const decided = card({ status: "accepted", choice: 0, decided_at: new Date(Date.now() - 2 * 86_400_000).toISOString() });
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [], [decided]) });
    openAt(ep.id);
    render(<App />);
    const steps = await screen.findByRole("list", { name: "Steps" });
    const items = within(steps).getAllByRole("listitem");
    expect(items).toHaveLength(10);
    expect(items[3]?.getAttribute("aria-current")).toBe("step");
    expect(screen.getByText("4 of 10 · Script")).toBeTruthy();
    const title = within(steps).getByRole("button", { name: /^2 Title, done/ });
    expect(title.getAttribute("data-tip")).toBe("Title · approved 2 days ago");
  });

  it("folds the sidebar and the crew column with Ctrl+B and Ctrl+Alt+B", async () => {
    mockApi({ "GET /api/state": state() });
    const { container } = render(<App />);
    await screen.findByText("No episodes yet. Say an idea below.");
    const app = container.querySelector(".app") as HTMLElement;
    fireEvent.keyDown(window, { key: "b", code: "KeyB", ctrlKey: true });
    expect(app.className).toContain("side-hidden");
    fireEvent.keyDown(window, { key: "b", code: "KeyB", ctrlKey: true, altKey: true });
    expect(app.className).toContain("crew-hidden");
    fireEvent.keyDown(window, { key: "b", code: "KeyB", metaKey: true });
    expect(app.className).not.toContain("side-hidden");
  });

  it("opens an episode with Ctrl+2 and focuses the composer with /", async () => {
    const one = episode({ id: "001-one", title: "First episode" });
    const two = episode({ id: "002-two", title: "Second episode" });
    mockApi({
      "GET /api/state": state({ episodes: [one, two] }),
      ...episodeRoutes(one, [], []),
      ...episodeRoutes(two, [], []),
    });
    openAt(one.id);
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: "First episode" });
    fireEvent.keyDown(window, { key: "2", ctrlKey: true });
    expect(await screen.findByRole("heading", { level: 1, name: "Second episode" })).toBeTruthy();
    fireEvent.keyDown(document.body, { key: "/" });
    expect(document.activeElement).toBe(screen.getByLabelText("Message"));
  });
});

describe("the spend card", () => {
  it("chooses this machine first when renting saves little, and that way never accepts", async () => {
    const ep = episode({ open_cards: 1 });
    const spend = spendCard(1500);
    expect(suggestedWay(spend)).toBe("local");
    const calls = mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], [spend]),
      "POST /api/cards/9/decline": { ...spend, status: "declined" },
    });
    openAt(ep.id);
    render(<App />);
    const group = await screen.findByRole("group", { name: "Render the 3D scenes on a rented GPU?" });
    expect(within(group).getByRole("radio", { name: /On this machine/ }).getAttribute("aria-checked")).toBe("true");
    await userEvent.click(within(group).getByRole("button", { name: "Render on this machine" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")).toEqual({
        method: "POST",
        path: "/api/cards/9/decline",
        body: { reason: "Local is fine. Render on this machine." },
      }),
    );
    expect(calls.some((c) => c.path.includes("/accept"))).toBe(false);
    expect(await screen.findByText("GPU rental not taken · this machine renders")).toBeTruthy();
  });

  it("switches the button text with the choice and rents only on the rented way", async () => {
    const ep = episode({ open_cards: 1 });
    const spend = spendCard(1500);
    const calls = mockApi({
      "GET /api/state": state({ episodes: [ep] }),
      ...episodeRoutes(ep, [], [spend]),
      "POST /api/cards/9/accept": { ...spend, status: "accepted" },
    });
    openAt(ep.id);
    render(<App />);
    const group = await screen.findByRole("group", { name: "Render the 3D scenes on a rented GPU?" });
    await userEvent.click(within(group).getByRole("radio", { name: /Rented GPU/ }));
    await userEvent.click(within(group).getByRole("button", { name: "Rent a GPU for $0.60" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/cards/9/accept")).toBe(true));
    expect(await screen.findByText("GPU rental approved · about 12 min for about $0.60")).toBeTruthy();
  });

  it("chooses the rented GPU first when it saves at least an hour", () => {
    expect(suggestedWay(spendCard(11_400))).toBe("rented");
    expect(foldedText({ ...spendCard(11_400), status: "accepted" })).toBe("GPU rental approved · about 12 min for about $0.60");
  });

  it("a waiting row in the crew chat jumps to the open card", async () => {
    const ep = episode({ open_cards: 1 });
    const waiting = job(11, { identity: "showrunner", status: "waiting", doing: "Waiting for your yes on the GPU", progress: null });
    mockApi({
      "GET /api/state": state({ episodes: [ep], activity: [waiting] }),
      ...episodeRoutes(ep, [], [spendCard(11_400)]),
    });
    openAt(ep.id);
    render(<App />);
    const crew = await screen.findByRole("region", { name: "Crew chat" });
    await screen.findByRole("group", { name: "Render the 3D scenes on a rented GPU?" });
    const row = await within(crew).findByRole("button", { name: /Waiting for your yes on the GPU.*Open the card\./ });
    await userEvent.click(row);
    expect(getUi().view).toEqual({ kind: "episode", id: ep.id });
  });
});

describe("the command palette", () => {
  it("opens with Ctrl+K, filters as you type and opens the chosen episode", async () => {
    const one = episode({ id: "001-one", title: "First episode" });
    const two = episode({ id: "002-two", title: "Does a subscription build a website?" });
    mockApi({
      "GET /api/state": state({ episodes: [one, two] }),
      ...episodeRoutes(one, [], []),
      ...episodeRoutes(two, [], []),
    });
    openAt(one.id);
    render(<App />);
    await screen.findByRole("heading", { level: 1, name: "First episode" });
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: "Command palette" });
    const field = within(dialog).getByRole("combobox");
    expect(document.activeElement).toBe(field);
    await userEvent.type(field, "subscription web");
    const options = within(dialog).getAllByRole("option");
    expect(options).toHaveLength(1);
    expect(options[0]?.getAttribute("aria-selected")).toBe("true");
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { level: 1, name: "Does a subscription build a website?" })).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull());
  });

  it("switches the theme and closes with Escape", async () => {
    mockApi({ "GET /api/state": state() });
    render(<App />);
    await screen.findByText("No episodes yet. Say an idea below.");
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const dialog = await screen.findByRole("dialog", { name: "Command palette" });
    await userEvent.type(within(dialog).getByRole("combobox"), "dark theme");
    await userEvent.keyboard("{Enter}");
    expect(document.documentElement.dataset.theme).toBe("dark");
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const again = await screen.findByRole("dialog", { name: "Command palette" });
    fireEvent.keyDown(within(again).getByRole("combobox"), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull());
  });

  it("matches every word, in any order", () => {
    const c = { id: "x", group: "Actions" as const, label: "Open teleprompter", run: () => undefined };
    expect(matches(c, "tele open")).toBe(true);
    expect(matches(c, "profile")).toBe(false);
    expect(keyLabels(["mod", "K"])).toEqual(["Ctrl", "K"]);
  });
});

describe("crew talk", () => {
  it("shows a finished exchange as one collapsed line that opens to the messages", async () => {
    const ep = episode();
    const exchange = message({
      id: 7,
      text: "Critic and Editor · fix about review/cut-check-v001.json · 2 messages",
      exchange: {
        topic: "t",
        result: "Done.",
        messages: [
          { id: 1, sender: "critic", recipient: "editor", kind: "fix", about: "review/cut-check-v001.json", text: "Trim 0.8 s at 2:31." },
          { id: 2, sender: "editor", recipient: "critic", kind: "fix", about: "review/cut-check-v001.json", text: "Trimmed." },
        ],
      },
    });
    mockApi({ "GET /api/state": state({ episodes: [ep] }), ...episodeRoutes(ep, [exchange], []) });
    openAt(ep.id);
    render(<App />);
    const line = await screen.findByRole("button", { name: /Critic and Editor · fix about review\/cut-check-v001\.json · 2 messages/ });
    expect(line.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Trim 0.8 s at 2:31.")).toBeNull();
    await userEvent.click(line);
    expect(line.getAttribute("aria-expanded")).toBe("true");
    const list = screen.getByRole("list", { name: "Messages between the crew" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("Trim 0.8 s at 2:31.")).toBeTruthy();
    expect(within(list).getAllByText("review/cut-check-v001.json")[0]?.tagName).toBe("CODE");
    await userEvent.click(line);
    expect(screen.queryByRole("list", { name: "Messages between the crew" })).toBeNull();
  });
});

describe("job details", () => {
  it("names the engine, the model and the effort when the job reports them", () => {
    expect(engineWords({ engine: "claude", engine_version: "2.1.325", model: "sonnet", effort: "high" })).toBe(
      "Runs on Claude Code 2.1.325 · model sonnet · effort high",
    );
    expect(engineWords({})).toBe("");
  });
});

describe("the scripted demo for the README", () => {
  it("plays the card, the switch to the rented GPU, the fold and the new row, then says it is done", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<App demo play />);
    await vi.advanceTimersByTimeAsync(500);
    expect(screen.queryByRole("group", { name: "Render 3D scene 5 on a rented GPU?" })).toBeNull();
    await vi.advanceTimersByTimeAsync(800);
    const group = screen.getByRole("group", { name: "Render 3D scene 5 on a rented GPU?" });
    expect(within(group).getByRole("button", { name: "Render on this machine" })).toBeTruthy();
    await vi.advanceTimersByTimeAsync(1500);
    expect(within(group).getByRole("button", { name: "Rent a GPU for $0.60" })).toBeTruthy();
    await vi.advanceTimersByTimeAsync(1800);
    expect(screen.queryByRole("group", { name: "Render 3D scene 5 on a rented GPU?" })).toBeNull();
    expect(screen.getByText("GPU rental approved · about 12 min for about $0.60")).toBeTruthy();
    await vi.advanceTimersByTimeAsync(800);
    const chat = screen.getByRole("region", { name: "Crew chat" });
    expect(within(chat).getByText("3D scene 5 of 5 on a rented GPU")).toBeTruthy();
    // the rented GPU shows up among the media of the episode
    expect(await screen.findByRole("region", { name: "Rented RTX 4090" })).toBeTruthy();
    expect(window.__crewcutPlayDone).toBeUndefined();
    await vi.advanceTimersByTimeAsync(3000);
    expect(window.__crewcutPlayDone).toBe(true);
  });

  it("without play the demo is the still scene of the README images: the home, then episode 012", async () => {
    render(<App demo />);
    expect(await screen.findByRole("heading", { level: 1, name: "Episodes" })).toBeTruthy();
    const needs = screen.getByRole("region", { name: "Needs you" });
    expect(within(needs).getAllByRole("button", { name: /Needs your yes\./ })).toHaveLength(2);
    const rail = screen.getByRole("complementary", { name: "Working now" });
    expect(within(rail).getByText("$4.10 of $20")).toBeTruthy();
    expect(screen.getByText("Demo data. Nothing here is real.")).toBeTruthy();
    await userEvent.click(within(needs).getByRole("button", { name: /^Claude improves a website 100 times\./ }));
    expect(await screen.findByRole("heading", { level: 1, name: "Claude improves a website 100 times" })).toBeTruthy();
    expect(screen.getByText("7 of 10 · Thumbnail")).toBeTruthy();
    const variants = await screen.findByRole("radiogroup", { name: "Thumbnail variants" });
    expect(within(variants).getByRole("radio", { name: /^B: Face centered, the Designer's pick/ }).getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("region", { name: "Rented RTX 4090" })).toBeTruthy();
    expect(await screen.findByRole("group", { name: "Pick a thumbnail" })).toBeTruthy();
    expect(window.__crewcutPlayDone).toBeUndefined();
  });
});

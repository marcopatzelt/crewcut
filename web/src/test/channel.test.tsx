import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { api } from "../api/client";
import { CHANNEL, ONBOARDING, type Message } from "../api/types";
import { Composer } from "../components/Composer";
import { applyEvent, composerTarget, hashToView, loadThread, navigate, send, viewToHash } from "../store/actions";
import { getUi, setUi, type View } from "../store/store";
import { episode, message, mockApi, resetApp, state } from "./helpers";

beforeEach(() => { resetApp(); vi.restoreAllMocks(); });

function ready() {
  setUi({ boot: "ready", state: state({ episodes: [episode()] }), threads: {
    [CHANNEL]: { status: "ready", error: null, messages: [] },
    "001-test": { status: "ready", error: null, messages: [] },
  } });
}

describe("Channel", () => {
  it("opens by default without creating an episode or loading a fake episode", async () => {
    const calls = mockApi({ "GET /api/state": state(), "GET /api/channel/messages": [] });
    render(<App />);
    await screen.findByRole("log");
    expect(screen.getByRole("heading", { level: 1, name: "Showrunner" })).toBeTruthy();
    expect(getUi().view).toEqual({ kind: "channel" });
    expect(calls.some((call) => call.method === "POST" || call.path.includes("/episodes/"))).toBe(false);
    expect(viewToHash({ kind: "channel" })).toBe("#/channel");
    expect(hashToView("#/channel")).toEqual({ kind: "channel" });
    expect(screen.getByRole("button", { name: "Channel" }).getAttribute("aria-current")).toBe("page");
  });

  it.each(["profile", "crew", "renders", "episodes", "job"])("routes %s to Channel, never the previous episode", async (kind) => {
    ready();
    const say = vi.spyOn(api, "say").mockResolvedValue(message({ author: "user" }));
    const create = vi.spyOn(api, "createEpisode");
    navigate({ kind: "episode", id: "001-test" });
    navigate(kind === "job" ? { kind, id: 1 } : { kind } as View);
    expect(composerTarget()).toBe(CHANNEL);
    await send("What is ready?");
    expect(say).toHaveBeenCalledWith(CHANNEL, "What is ready?");
    expect(create).not.toHaveBeenCalled();
    expect(getUi().view).toEqual({ kind: "channel" });
  });

  it("keeps Channel, episode and new drafts separate across navigation", async () => {
    ready();
    render(<Composer />);
    await userEvent.type(screen.getByLabelText("Message"), "Channel draft");
    act(() => navigate({ kind: "episode", id: "001-test" }));
    expect(screen.getByText("Episode: A test episode")).toBeTruthy();
    await userEvent.type(screen.getByLabelText("Message"), "Episode draft");
    act(() => navigate({ kind: "new" }));
    await userEvent.type(screen.getByLabelText("Message"), "New draft");
    act(() => navigate({ kind: "channel" }));
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Channel draft");
    act(() => navigate({ kind: "episode", id: "001-test" }));
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Episode draft");
    expect(getUi().drafts._new).toBe("New draft");
  });

  it("keeps delayed replies and send errors in their original conversation", async () => {
    ready();
    let resolve!: (value: Message) => void;
    vi.spyOn(api, "say").mockImplementation(() => new Promise((done) => { resolve = done; }));
    render(<Composer />);
    await userEvent.type(screen.getByLabelText("Message"), "Channel question{Enter}");
    act(() => navigate({ kind: "episode", id: "001-test" }));
    await userEvent.type(screen.getByLabelText("Message"), "Keep this draft");
    await act(async () => resolve(message({ id: 30, text: "Channel question", author: "user" })));
    expect(getUi().view).toEqual({ kind: "episode", id: "001-test" });
    expect(getUi().threads[CHANNEL]?.messages[0]?.id).toBe(30);
    expect(getUi().threads["001-test"]?.messages).toEqual([]);
    expect((screen.getByLabelText("Message") as HTMLTextAreaElement).value).toBe("Keep this draft");
    act(() => applyEvent("message", message({ id: 31, episode: CHANNEL, text: "Channel answer" })));
    expect(getUi().threads[CHANNEL]?.messages).toHaveLength(2);
    vi.spyOn(api, "say").mockRejectedValue(new Error("Try later"));
    act(() => navigate({ kind: "channel" }));
    await userEvent.type(screen.getByLabelText("Message"), "Retry me{Enter}");
    await screen.findByRole("alert");
    act(() => navigate({ kind: "episode", id: "001-test" }));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(getUi().drafts[CHANNEL]).toBe("Retry me");
  });

  it("merges live messages arriving while history loads", async () => {
    ready();
    let resolve!: (value: Message[]) => void;
    vi.spyOn(api, "messages").mockImplementation(() => new Promise((done) => { resolve = done; }));
    const pending = loadThread(CHANNEL, true);
    applyEvent("message", message({ id: 20, episode: CHANNEL }));
    resolve([message({ id: 10 })]);
    await pending;
    expect(getUi().threads[CHANNEL]?.messages.map((item) => item.id)).toEqual([10, 20]);
  });

  it("uses dedicated channel URLs and retains episode and onboarding URLs", async () => {
    const calls = mockApi({ "GET /api/channel/messages": [], "POST /api/channel/messages": message(),
      "GET /api/episodes/001-test/messages": [], "POST /api/episodes/_onboarding/messages": message() });
    await api.messages(CHANNEL, 12);
    await api.say(CHANNEL, "Hello");
    expect(await api.cards(CHANNEL)).toEqual([]);
    await api.messages("001-test");
    await api.say(ONBOARDING, "Setup");
    expect(calls.map((call) => call.path)).toEqual(["/api/channel/messages?after=12", "/api/channel/messages",
      "/api/episodes/001-test/messages", "/api/episodes/_onboarding/messages"]);
  });

  it("links episode facts only to episodes in current state", async () => {
    const known = episode();
    mockApi({ "GET /api/state": state({ episodes: [known] }), "GET /api/channel/messages": [
      message({ text: "The crew has a result.", facts: [
        { label: "episode", value: known.id },
        { label: "episode", value: "unknown-episode" },
        { label: "episode", value: "https://example.org/untrusted" },
      ] }),
    ] });
    render(<App />);
    const link = await screen.findByRole("link", { name: known.title });
    expect(link.getAttribute("href")).toBe("#/e/001-test");
    expect(screen.queryByRole("link", { name: "unknown-episode" })).toBeNull();
    expect(screen.queryByRole("link", { name: "https://example.org/untrusted" })).toBeNull();
  });

  it("opens Channel through the keyboard palette", async () => {
    mockApi({ "GET /api/state": state(), "GET /api/channel/messages": [] });
    render(<App />);
    await screen.findByRole("log");
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    await userEvent.type(await screen.findByRole("combobox"), "Show Channel{Enter}");
    await waitFor(() => expect(getUi().paletteOpen).toBe(false));
    expect(getUi().view.kind).toBe("channel");
  });
});

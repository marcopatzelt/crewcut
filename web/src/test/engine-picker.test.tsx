import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, it, expect, vi } from "vitest";
import { EnginePicker } from "../components/EnginePicker";
import { Composer } from "../components/Composer";
import { setUi } from "../store/store";
import { CHANNEL } from "../api/types";
import { mockApi, resetApp, state, Reply } from "./helpers";

afterEach(() => { resetApp(); vi.unstubAllGlobals(); });

it("adds Codex even when Claude is connected", async () => {
  mockApi({ "GET /api/engine/login": {
    chosen: "claude", claude: { installed: true, connected: true }, codex: { installed: false, connected: false },
  } });
  render(<EnginePicker />);
  fireEvent.click(screen.getByRole("button", { name: /Chat AI:/ }));
  expect(await screen.findByRole("button", { name: "Connect Codex" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Using Claude Code" }).hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Connect Codex" }));
  expect(await screen.findByRole("button", { name: "Sign in to Codex" })).toBeTruthy();
});

it("switches through the server without an agent job", async () => {
  const login = { chosen: "claude", claude: { installed: true, connected: true }, codex: { installed: true, connected: true } };
  const calls = mockApi({
    "GET /api/engine/login": login,
    "POST /api/engine/codex/use": { ...login, chosen: "codex" },
    "GET /api/state": state(),
  });
  render(<EnginePicker />);
  fireEvent.click(screen.getByRole("button", { name: /Chat AI:/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Use Codex" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Using Codex" }).hasAttribute("disabled")).toBe(true));
  expect(calls.filter((call) => call.method === "POST").map((call) => call.path)).toEqual(["/api/engine/codex/use"]);
});

it("keeps the selected AI after a failed switch and closes with Escape", async () => {
  mockApi({
    "GET /api/engine/login": { chosen: "claude", claude: { connected: true }, codex: { connected: true } },
    "POST /api/engine/codex/use": new Reply(409, { detail: "Connect Codex before switching." }),
  });
  render(<EnginePicker />);
  const trigger = screen.getByRole("button", { name: /Chat AI:/ });
  fireEvent.click(trigger);
  fireEvent.click(await screen.findByRole("button", { name: "Use Codex" }));
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Using Claude Code" }).hasAttribute("disabled")).toBe(true);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("region", { name: "Choose chat AI" })).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

it("shows the chooser beside the channel draft and preserves the draft when switching", async () => {
  const initial = state();
  const login = { chosen: "claude", claude: { connected: true }, codex: { connected: true } };
  setUi({ boot: "ready", state: initial, view: { kind: "channel" }, drafts: { [CHANNEL]: "Keep my draft" } });
  mockApi({
    "GET /api/engine/login": login,
    "POST /api/engine/codex/use": { ...login, chosen: "codex" },
    "GET /api/state": { ...initial, app: { ...initial.app, engine: "codex" } },
  });
  render(<Composer />);
  fireEvent.click(screen.getByRole("button", { name: "Chat AI: Claude Code. Change AI" }));
  fireEvent.click(await screen.findByRole("button", { name: "Use Codex" }));
  expect(await screen.findByRole("button", { name: "Chat AI: Codex. Change AI" })).toBeTruthy();
  expect((screen.getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement).value).toBe("Keep my draft");
  expect(screen.getByText("Channel")).toBeTruthy();
});

const auth = (mode: "subscription" | "api_key", present: boolean, source: "stored" | "environment" | null = present ? "stored" : null) => ({
  mode, subscription: { connected: true, source: "stored" }, api_key: { present, source },
});

it("saves an API key once, switches to it and never shows the key again", async () => {
  const login = { chosen: "claude", claude: { installed: true, connected: true }, codex: { connected: false },
    claude_auth: auth("subscription", false) };
  const calls = mockApi({
    "GET /api/engine/login": login,
    "POST /api/engine/claude/api-key": auth("api_key", true),
    "POST /api/engine/claude/auth": auth("subscription", true),
    "DELETE /api/engine/claude/api-key": auth("subscription", false),
    "GET /api/state": state(),
  });
  render(<EnginePicker />);
  fireEvent.click(screen.getByRole("button", { name: /Chat AI:/ }));
  const sub = await screen.findByRole("button", { name: "Subscription" });
  expect(sub.getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByRole("button", { name: "API key" }).hasAttribute("disabled")).toBe(true);
  expect(screen.getByText(/billed per token/)).toBeTruthy();
  const field = screen.getByLabelText("Anthropic API key") as HTMLInputElement;
  expect(field.type).toBe("password");
  fireEvent.change(field, { target: { value: "sk-ant-test-0000000000000000000000000000000000" } });
  fireEvent.click(screen.getByRole("button", { name: "Save key" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "API key" }).getAttribute("aria-pressed")).toBe("true"));
  expect(screen.queryByLabelText("Anthropic API key")).toBeNull();
  expect(screen.getByText("API key saved.")).toBeTruthy();
  expect(document.body.textContent).not.toContain("sk-ant-test");
  expect(calls.find((c) => c.path === "/api/engine/claude/api-key")?.body).toEqual({
    key: "sk-ant-test-0000000000000000000000000000000000", use: true });
  fireEvent.click(screen.getByRole("button", { name: "Subscription" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Subscription" }).getAttribute("aria-pressed")).toBe("true"));
  expect(calls.find((c) => c.path === "/api/engine/claude/auth")?.body).toEqual({ mode: "subscription" });
  fireEvent.click(screen.getByRole("button", { name: "Remove key" }));
  expect(await screen.findByLabelText("Anthropic API key")).toBeTruthy();
  expect(calls.some((c) => c.method === "DELETE")).toBe(true);
});

it("shows a key from the environment without a remove button and reports a refused switch", async () => {
  mockApi({
    "GET /api/engine/login": { chosen: "claude", claude: { connected: true }, codex: { connected: false },
      claude_auth: auth("subscription", true, "environment") },
    "POST /api/engine/claude/auth": new Reply(409, { detail: "Save an Anthropic API key first." }),
  });
  render(<EnginePicker />);
  fireEvent.click(screen.getByRole("button", { name: /Chat AI:/ }));
  expect(await screen.findByText("API key from the environment (.env).")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Remove key" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "API key" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Save an Anthropic API key first.");
  expect(screen.getByRole("button", { name: "Subscription" }).getAttribute("aria-pressed")).toBe("true");
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, it, expect, vi } from "vitest";
import { EnginePicker } from "../components/EnginePicker";
import { mockApi, resetApp, state } from "./helpers";

afterEach(() => { resetApp(); vi.unstubAllGlobals(); });

it("adds Codex even when Claude is connected", async () => {
  mockApi({ "GET /api/engine/login": {
    chosen: "claude", claude: { installed: true, connected: true }, codex: { installed: false, connected: false },
  } });
  render(<EnginePicker />);
  expect(await screen.findByRole("button", { name: "Connect Codex (beta) instead" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Using Claude Code" }).hasAttribute("disabled")).toBe(true);
});

it("switches through the server without an agent job", async () => {
  const login = { chosen: "claude", claude: { installed: true, connected: true }, codex: { installed: true, connected: true } };
  const calls = mockApi({
    "GET /api/engine/login": login,
    "POST /api/engine/codex/use": { ...login, chosen: "codex" },
    "GET /api/state": state(),
  });
  render(<EnginePicker />);
  fireEvent.click(await screen.findByRole("button", { name: "Use Codex" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Using Codex" }).hasAttribute("disabled")).toBe(true));
  expect(calls.filter((call) => call.method === "POST").map((call) => call.path)).toEqual(["/api/engine/codex/use"]);
});

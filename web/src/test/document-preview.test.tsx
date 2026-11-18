import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DocumentPreview } from "../components/DocumentPreview";
import { CardItem } from "../components/CardView";
import { card, resetApp } from "./helpers";

beforeEach(() => {
  resetApp();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } });
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("opens a proof card file inside the app and leaves the card undecided", async () => {
  const fetchFile = vi.fn().mockResolvedValue(new Response("Verified evidence"));
  vi.stubGlobal("fetch", fetchFile);
  render(<CardItem card={card({ kind: "proof", file: "brief/evidence.md", episode: "test" })} team={[]} steps={[]} />);
  fireEvent.click(screen.getByRole("link", { name: "brief/evidence.md" }));
  expect(await screen.findByText("Verified evidence")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(screen.getByRole("button", { name: "Use these facts" })).toBeTruthy();
  expect(fetchFile).toHaveBeenCalledTimes(1);
});

it("reads text safely without approving and keeps approval shortcuts outside", async () => {
  const fetchFile = vi.fn().mockResolvedValue(new Response("# Script\n<script>unsafe()</script>"));
  vi.stubGlobal("fetch", fetchFile);
  const close = vi.fn();
  const shortcut = vi.fn();
  window.addEventListener("keydown", shortcut);
  render(<DocumentPreview episode="test" file="brief/script.md" onClose={close} />);
  expect(await screen.findByText(/unsafe/)).toBeTruthy();
  expect(document.querySelector("dialog script")).toBeNull();
  fireEvent.keyDown(screen.getByRole("button", { name: "Close" }), { key: "Enter", ctrlKey: true });
  expect(shortcut).not.toHaveBeenCalled();
  expect(fetchFile).toHaveBeenCalledTimes(1);
  expect(fetchFile.mock.calls[0]![0]).toBe("/api/files/test/brief/script.md");
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(close).toHaveBeenCalledOnce();
  window.removeEventListener("keydown", shortcut);
});

it("shows missing files instead of an empty preview", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 404 })));
  render(<DocumentPreview episode="test" file="brief/missing.md" onClose={() => {}} />);
  expect((await screen.findByRole("alert")).textContent).toBe("This file could not be found.");
});

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { documentTarget } from "../components/DocumentLink";
import { FormattedText } from "../components/FormattedText";
import { resetApp } from "./helpers";

beforeEach(() => {
  resetApp();
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute("open", ""); } });
  Object.defineProperty(HTMLDialogElement.prototype, "close", { configurable: true, value: function (this: HTMLDialogElement) { this.removeAttribute("open"); } });
});
afterEach(() => vi.unstubAllGlobals());

it.each([
  'Read brief/SCRIPT-v001.md first.',
  'Read `brief/SCRIPT-v001.md` first.',
  '[Read script](brief/SCRIPT-v001.md)',
  '[Read script](/api/files/test/brief/SCRIPT-v001.md)',
])("opens a chat reference without navigation or approval: %s", async text => {
  const request = vi.fn().mockResolvedValue(new Response('# My script\n\nFull spoken text.'));
  vi.stubGlobal("fetch", request);
  render(<FormattedText episode="test" text={text} />);
  fireEvent.click(screen.getByRole("link"));
  expect(await screen.findByRole("heading", { name: "My script" })).toBeTruthy();
  expect(request).toHaveBeenCalledTimes(1);
  expect(request.mock.calls[0]![0]).toBe('/api/files/test/brief/SCRIPT-v001.md');
});

it("does not guess an episode for channel references", () => {
  expect(documentTarget('brief/script.md', '_channel')).toBeNull();
  expect(documentTarget('/api/files/test/brief/script.md', '_channel')).toEqual({ episode: 'test', file: 'brief/script.md' });
});

it.each(['../secret.md', 'brief/%2e%2e/secret.md', 'file:///tmp/script.md', 'https://example.org/script.md', '/etc/script.md', 'brief\\script.md', '/api/files/test/../secret.md', 'brief/script.md?download=1', 'brief/%00.md', 'brief/script.html'])("rejects unsafe or unsupported paths: %s", path => {
  expect(documentTarget(path, 'test')).toBeNull();
});

it("keeps code blocks literal", () => {
  render(<FormattedText episode="test" text={'```text\nbrief/SCRIPT-v001.md\n```'} />);
  expect(screen.queryByRole("link")).toBeNull();
});

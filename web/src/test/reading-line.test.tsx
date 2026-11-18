import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { guidePercent, ReadingLine } from "../prompter/ReadingLine";

afterEach(() => vi.unstubAllGlobals());

it("moves with keys without changing playback or speed", () => {
  const change = vi.fn();
  const outer = vi.fn();
  render(<div onKeyDown={outer}><ReadingLine value={33} onChange={change} /></div>);
  const guide = screen.getByRole("slider", { name: "Reading line" });
  fireEvent.keyDown(guide, { key: "ArrowDown" });
  expect(change).toHaveBeenLastCalledWith(34);
  expect(outer).not.toHaveBeenCalled();
  fireEvent.keyDown(guide, { key: "Home" });
  expect(change).toHaveBeenLastCalledWith(10);
  fireEvent.keyDown(guide, { key: "End" });
  expect(change).toHaveBeenLastCalledWith(85);
});

it("drags smoothly and saves only on release", () => {
  class TestPointerEvent extends MouseEvent {
    pointerId: number;
    constructor(type: string, options: PointerEventInit = {}) { super(type, options); this.pointerId = options.pointerId ?? 1; }
  }
  vi.stubGlobal("PointerEvent", TestPointerEvent);
  vi.stubGlobal("innerHeight", 1000);
  const change = vi.fn();
  render(<ReadingLine value={33} onChange={change} />);
  const guide = screen.getByRole("slider");
  guide.setPointerCapture = vi.fn();
  guide.releasePointerCapture = vi.fn();
  fireEvent.pointerDown(guide, { pointerId: 7, button: 0, clientY: 330 });
  fireEvent.pointerMove(guide, { pointerId: 7, clientY: 570 });
  expect(guide.getAttribute("aria-valuenow")).toBe("57");
  expect(change).not.toHaveBeenCalled();
  fireEvent.pointerUp(guide, { pointerId: 7, clientY: 570 });
  expect(change).toHaveBeenCalledTimes(1);
  expect(change).toHaveBeenCalledWith(57);
});

it("keeps the line in reach and handles old saved controls", () => {
  expect(guidePercent(undefined)).toBe(33);
  expect(guidePercent(NaN)).toBe(33);
  expect(guidePercent(-20)).toBe(10);
  expect(guidePercent(200)).toBe(85);
});

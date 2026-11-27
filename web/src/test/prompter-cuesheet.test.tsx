// A cue sheet on the teleprompter: pages instead of paragraphs, fixed lines and bullets, take counts on the remote, and
// Previous, Repeat and Next by page (synthetic sheet only).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PrompterControl, PrompterScript } from "../api/types";
import { withNumbers } from "../prompter/CueSheet";
import { DEFAULT_CONTROL, Prompter, type PrompterSource } from "../prompter/Prompter";
import { normalizeBlocks, normalizePages, pageAt, pageStep } from "../prompter/timeline";

const sheet: PrompterScript = {
  title: "Synthetic cue sheet",
  mode: "full",
  format: "cuesheet",
  pages: [
    { page: "opening", label: "Opening", first: 0, short: false },
    { page: "unit 1", label: "Unit 1", first: 2, short: true },
    { page: "close", label: "Close", first: 6, short: false },
  ],
  blocks: [
    { text: "The cheapest setting built my best clip.", points: [], kind: "fixed", role: "line1", page: "opening",
      unit: null, picture: "ranking", big: true, section: 1 },
    { text: "I tested 4 settings on 8 clips.", points: [], kind: "fixed", role: "proof", page: "opening", unit: null,
      section: 1 },
    { text: "My best clip took 40 minutes.", points: [], kind: "fixed", role: "hook", page: "unit 1", unit: 1, big: true,
      section: 2 },
    { text: "40 minutes against 90 · same prompt", points: ["40 minutes against 90", "same prompt"], kind: "bullet",
      role: "proof", page: "unit 1", unit: 1, picture: "both clocks", question: "Why so fast?",
      groups: ["40 minutes against 90", "same prompt"], section: 2 },
    { text: "Helpers beat thinking time.", points: [], kind: "fixed", role: "punch", page: "unit 1", unit: 1, big: true,
      section: 2 },
    { text: "So where did the time go?", points: [], kind: "fixed", role: "bridge", page: "unit 1", unit: 1, section: 2 },
    { text: "I keep the cheap setting.", points: [], kind: "fixed", role: "verdict", page: "close", unit: null, section: 3 },
    { text: "The link is in the description.", points: [], kind: "fixed", role: "link", page: "close", unit: null,
      section: 3 },
  ],
};

function source(over: Partial<PrompterSource> = {}): PrompterSource {
  let control: PrompterControl = { ...DEFAULT_CONTROL };
  return {
    shared: false,
    script: async () => sheet,
    getControl: async () => control,
    setControl: async (c) => {
      control = { ...control, ...c };
    },
    ...over,
  };
}

const marked = (container: HTMLElement) => container.querySelector("[aria-current='true']")?.getAttribute("data-index");

describe("cue sheet pages", () => {
  it("finds the page of a block and the page starts Previous, Next and Repeat go to (the same rule as the server)", () => {
    const blocks = normalizeBlocks(sheet.blocks);
    const pages = normalizePages(sheet.pages, blocks);
    expect(pages.map((p) => [p.page, p.first, p.unit])).toEqual([["opening", 0, null], ["unit 1", 2, 1], ["close", 6, null]]);
    expect([0, 1, 2, 5, 6, 7].map((b) => pageAt(pages, b))).toEqual([0, 0, 1, 1, 2, 2]);
    expect(pageStep(pages, 3, "next")).toBe(6);
    expect(pageStep(pages, 3, "prev")).toBe(0);
    expect(pageStep(pages, 5, "repeat")).toBe(2);
    expect(pageStep(pages, 7, "next")).toBeNull();
    expect(pageStep(pages, 1, "prev")).toBeNull();
    // without the server's list the pages come from the blocks
    expect(normalizePages(undefined, blocks).map((p) => p.first)).toEqual([0, 2, 6]);
    expect(pageAt([], 3)).toBe(-1);
  });

  it("puts every run of digits in bold", () => {
    const { container } = render(<p>{withNumbers("600 times 30 seconds, 1,5 hours at 12:30")}</p>);
    expect([...container.querySelectorAll("strong")].map((s) => s.textContent)).toEqual(["600", "30", "1,5", "12:30"]);
    expect(container.textContent).toBe("600 times 30 seconds, 1,5 hours at 12:30");
  });

  it("shows pages with fixed lines and bullets, and no switch to key points", async () => {
    const { container } = render(<Prompter source={source()} remote={false} />);
    await screen.findByText("Helpers beat thinking time.");
    expect([...container.querySelectorAll(".pr-page > span:first-child")].map((s) => s.textContent))
      .toEqual(["Opening", "Unit 1", "Close"]);
    expect(container.querySelectorAll(".pr-page.break")).toHaveLength(2);
    expect(container.querySelector(".pr-page.break .pr-pic")?.textContent).toBe("Short");
    // hook, punch line and the first line are full size; the bridge is medium; the bullet small and dimmed
    expect([...container.querySelectorAll(".pr-block.cue.big")].map((b) => b.getAttribute("data-index"))).toEqual(["0", "2", "4"]);
    expect(container.querySelector("[data-index='5']")?.className).toContain("role-bridge");
    const bullet = container.querySelector(".pr-block.cue.bullet")!;
    expect(bullet.getAttribute("data-index")).toBe("3");
    expect(bullet.querySelector(".pr-role")?.textContent).toBe("proof");
    expect(bullet.querySelector(".pr-pic")?.textContent).toBe("both clocks");
    expect(bullet.querySelector(".pr-question")?.textContent).toBe("Why so fast?");
    expect([...bullet.querySelectorAll(".pr-group")].map((g) => g.textContent)).toEqual(["40 minutes against 90", "same prompt"]);
    expect([...bullet.querySelectorAll("strong")].map((s) => s.textContent)).toEqual(["40", "90"]);
    expect(container.querySelector("[data-index='0'] .pr-pic")?.textContent).toBe("ranking");
    // the speaking blocks are still direct children of the text column, so the timeline can measure them
    expect(container.querySelectorAll(".pr-copy > [data-index]")).toHaveLength(8);
    expect(screen.queryByRole("button", { name: "Show key points" })).toBeNull();
    expect(screen.getByRole("toolbar", { name: "Pages" })).toBeTruthy();
    expect(screen.queryByRole("toolbar", { name: "Speaking blocks" })).toBeNull();
  });

  it("moves by page with Page Down, Page Up and R, and P changes nothing", async () => {
    const { container } = render(<Prompter source={source()} remote={false} />);
    await screen.findByText("Helpers beat thinking time.");
    expect(screen.getByRole("button", { name: "Previous page" })).toHaveProperty("disabled", true);
    fireEvent.keyDown(window, { key: "PageDown" });
    await waitFor(() => expect(marked(container)).toBe("2"));
    expect(screen.getByRole("button", { name: "Repeat Unit 1, take 1" }).textContent).toBe("Repeat 1");
    fireEvent.keyDown(window, { key: "PageDown" });
    await waitFor(() => expect(marked(container)).toBe("6"));
    expect(screen.getByRole("button", { name: "Next page" })).toHaveProperty("disabled", true);
    fireEvent.keyDown(window, { key: "PageUp" });
    await waitFor(() => expect(marked(container)).toBe("2"));
    fireEvent.click(container.querySelector("[data-index='4']")!); // a tap on a block jumps exactly there
    await waitFor(() => expect(marked(container)).toBe("4"));
    fireEvent.keyDown(window, { key: "r" });
    await waitFor(() => expect(marked(container)).toBe("2"));
    fireEvent.keyDown(window, { key: "p" });
    expect(container.querySelector(".pr-block.cue.bullet .pr-group")).not.toBeNull();
  });

  it("lists one row per page with its take count on the remote and steps by page", async () => {
    const theirs: PrompterControl = { ...DEFAULT_CONTROL, block: 3, offset: 0, at: 0, seq: 5, takes: { "unit 1": 2 } };
    const posted = vi.fn().mockResolvedValue(undefined);
    render(<Prompter source={source({ shared: true, getControl: async () => theirs, setControl: posted })} remote />);
    const row = await screen.findByRole("button", { name: "Unit 1, 2 takes" });
    await waitFor(() => expect(row.getAttribute("aria-current")).toBe("true"));
    expect(row.textContent).toContain("Unit 1 · Short");
    expect(row.textContent).toContain("My best clip took 40 minutes.");
    expect(screen.getByRole("button", { name: "Opening, No take yet" })).toBeTruthy();
    expect(screen.getByRole("list", { name: "Pages" }).children).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Repeat Unit 1, take 3" }));
    expect(posted).toHaveBeenLastCalledWith(expect.objectContaining({ action: "repeat", block: 2 }));
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(posted).toHaveBeenLastCalledWith(expect.objectContaining({ action: "next", block: 6 }));
    fireEvent.click(screen.getByRole("button", { name: "Opening, No take yet" }));
    expect(posted).toHaveBeenLastCalledWith(expect.objectContaining({ action: "jump", block: 0 }));
  });
});

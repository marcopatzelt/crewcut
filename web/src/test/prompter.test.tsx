// The teleprompter: token from the path, play and pause, modes, and following the shared control.
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PrompterControl, PrompterScript } from "../api/types";
import { DEFAULT_CONTROL, httpSource, Prompter, tokenFromLocation, type PrompterSource } from "../prompter/Prompter";

const script: PrompterScript = {
  title: "Test script",
  mode: "full",
  blocks: [
    { text: "The first sentence of the script.", points: ["First point"] },
    { text: "The second sentence.", points: ["Second point"] },
  ],
};

function source(over: Partial<PrompterSource> = {}): PrompterSource {
  let control: PrompterControl = { ...DEFAULT_CONTROL };
  return {
    shared: false,
    script: async () => script,
    getControl: async () => control,
    setControl: async (c) => {
      control = { ...control, ...c };
    },
    ...over,
  };
}

describe("teleprompter", () => {
  it("keeps rapid commands in order on a slow connection", async () => {
    let finish!: (value: Response) => void;
    const fetcher = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; }))
      .mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetcher);
    try {
      const src = httpSource("synthetic");
      const first = src.setControl({ guide: 35 });
      const second = src.setControl({ guide: 37 });
      await Promise.resolve();
      expect(fetcher).toHaveBeenCalledTimes(1);
      finish(new Response("{}"));
      await Promise.all([first, second]);
      expect(fetcher.mock.calls.map(call => JSON.parse(call[1].body))).toEqual([{ guide: 35 }, { guide: 37 }]);
    } finally { vi.unstubAllGlobals(); }
  });

  it("ignores an older read that arrives after a phone command", async () => {
    let finish!: (value: PrompterControl) => void;
    const getControl = vi.fn().mockImplementation(() => new Promise<PrompterControl>(resolve => { finish = resolve; }));
    const posted = vi.fn().mockResolvedValue(undefined);
    render(<Prompter source={source({ shared: true, getControl, setControl: posted })} remote />);
    await screen.findByRole("button", { name: "Move reading line down" });
    fireEvent.click(screen.getByRole("button", { name: "Move reading line down" }));
    fireEvent.click(screen.getByRole("button", { name: "Move reading line down" }));
    await act(async () => { finish({ ...DEFAULT_CONTROL, guide: 33 }); });
    expect(screen.getByLabelText("Reading line percent").textContent).toBe("37 %");
    expect(posted).toHaveBeenLastCalledWith(expect.objectContaining({ guide: 37 }));
  });
  it("moves the reading line from the phone without starting playback", async () => {
    const posted = vi.fn().mockResolvedValue(undefined);
    render(<Prompter source={source({ shared: true, setControl: posted })} remote />);
    fireEvent.click(await screen.findByRole("button", { name: "Move reading line down" }));
    expect(posted).toHaveBeenLastCalledWith(expect.objectContaining({ guide: 35 }));
    expect(posted.mock.calls[0]?.[0]).not.toHaveProperty("playing");
    fireEvent.click(screen.getByRole("button", { name: "Move reading line up" }));
    expect(posted).toHaveBeenLastCalledWith(expect.objectContaining({ guide: 33 }));
    fireEvent.click(screen.getByRole("button", { name: "Reset line" }));
    expect(screen.getByLabelText("Reading line percent").textContent).toBe("33 %");
  });
  it.each([false, true])("shows partial-script warnings (remote=%s)", async (remote) => {
    const note = "Partial script. The remaining sections are not ready.";
    render(<Prompter source={source({ script: async () => ({ ...script, note }) })} remote={remote} />);
    expect((await screen.findByRole("note")).textContent).toBe(note);
  });
  it("reads the token from the path or the query", () => {
    expect(tokenFromLocation({ pathname: "/p/abc123", search: "" })).toBe("abc123");
    expect(tokenFromLocation({ pathname: "/p/abc123/", search: "" })).toBe("abc123");
    expect(tokenFromLocation({ pathname: "/prompter.html", search: "?token=x9" })).toBe("x9");
    expect(tokenFromLocation({ pathname: "/prompter.html", search: "" })).toBeNull();
  });

  it("says what to do without a link", () => {
    render(<Prompter source={null} remote={false} />);
    expect(screen.getByRole("alert").textContent).toContain("This page needs the link from Crewcut");
  });

  it("shows the full text, plays and pauses with Space, and switches to key points", async () => {
    render(<Prompter source={source()} remote={false} />);
    expect(await screen.findByText("The first sentence of the script.")).toBeTruthy();
    fireEvent.keyDown(window, { key: " " });
    expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();
    fireEvent.keyDown(window, { key: " " });
    expect(screen.getByRole("button", { name: "Play" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show key points" }));
    expect(screen.getByText("First point")).toBeTruthy();
    expect(screen.queryByText("The first sentence of the script.")).toBeNull();
  });

  it("follows the shared control and posts its own changes", async () => {
    const posted: Partial<PrompterControl>[] = [];
    const theirs: PrompterControl = { ...DEFAULT_CONTROL, mirror: true, speed: 1.5 };
    const src = source({
      shared: true,
      getControl: vi.fn(async () => theirs),
      setControl: vi.fn(async (c: Partial<PrompterControl>) => {
        posted.push(c);
      }),
    });
    const { container } = render(<Prompter source={src} remote={false} />);
    await screen.findByText("The first sentence of the script.");
    await waitFor(() => expect(container.querySelector(".pr-text.mirror")).not.toBeNull());
    expect(screen.getByText("1.5×")).toBeTruthy();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Faster" }));
    });
    expect(posted[posted.length - 1]?.speed).toBe(1.6);
  });

  it("shows the blocks as a list to tap and the controls in remote mode, not the reading view", async () => {
    const { container } = render(<Prompter source={source()} remote />);
    expect(await screen.findByRole("toolbar", { name: "Teleprompter controls" })).toBeTruthy();
    expect(screen.getByRole("toolbar", { name: "Speaking blocks" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Block 2: The second sentence." })).toBeTruthy();
    expect(container.querySelector(".pr-scroll")).toBeNull();
  });

  it("numbers the blocks and keeps section breaks visible", async () => {
    const sections: PrompterScript = { ...script, blocks: [
      { text: "Intro one.", points: [], n: 1, section: 1 },
      { text: "Intro two.", points: [], n: 2, section: 1 },
      { text: "Part two starts.", points: [], n: 3, section: 2 },
    ] };
    const { container } = render(<Prompter source={source({ script: async () => sections })} remote={false} />);
    await screen.findByText("Part two starts.");
    expect([...container.querySelectorAll(".pr-num")].map((n) => n.textContent)).toEqual(["1", "2", "3"]);
    const breaks = container.querySelectorAll(".pr-break");
    expect(breaks).toHaveLength(1);
    expect(breaks[0]?.nextElementSibling?.textContent).toContain("Part two starts.");
  });

  it("jumps with Page Down, Page Up and R on a screen without a server", async () => {
    const { container } = render(<Prompter source={source()} remote={false} />);
    await screen.findByText("The second sentence.");
    fireEvent.keyDown(window, { key: "PageDown" });
    await waitFor(() => expect(container.querySelector("[aria-current='true']")?.getAttribute("data-index")).toBe("1"));
    expect(screen.getByRole("button", { name: "Repeat block 2 of 2" })).toBeTruthy();
    fireEvent.keyDown(window, { key: "PageUp" });
    await waitFor(() => expect(container.querySelector("[aria-current='true']")?.getAttribute("data-index")).toBe("0"));
  });
});

// The Humanizer note on a script card: one line, collapsed; opened, the changes as before and after.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Humanized, humanizerLine } from "../components/Humanized";
import { card } from "./helpers";

const note = {
  version: "v4.0.0",
  mode: "embedded" as const,
  voice: ["brand/voice/a.md"],
  count: 2,
  changes: [
    { before: "It is not a tool, it is a team.", after: "It is a team." },
    { before: "And that changes everything.", after: "" },
  ],
};

describe("the Humanizer note", () => {
  it("says what happened in one line", () => {
    expect(humanizerLine(note)).toBe("Humanized · 2 changes · Humanizer v4.0.0 · with your voice");
    expect(humanizerLine({ skipped: "switched off in this studio" })).toBe("Not humanized: switched off in this studio");
  });

  it("is collapsed and opens to before and after", async () => {
    render(<Humanized card={card({ kind: "script", data: { humanizer: note } })} folding={false} />);
    const line = screen.getByRole("button", { name: /Humanized · 2 changes/ });
    expect(line.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("It is a team.")).toBeNull();
    await userEvent.click(line);
    expect(screen.getByText("It is a team.")).toBeTruthy();
    expect(screen.getByText("(removed)")).toBeTruthy();
  });

  it("shows nothing on cards without a pass", () => {
    const { container } = render(<Humanized card={card({ kind: "title" })} folding={false} />);
    expect(container.textContent).toBe("");
  });
});

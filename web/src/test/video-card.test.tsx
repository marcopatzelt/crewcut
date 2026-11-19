import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { OpenCard } from "../components/CardView";
import { card } from "./helpers";

it("plays a file-only preview card without requiring a separate preview field", () => {
  render(<OpenCard card={card({ kind: "preview", title: "Review cut", episode: "001-test",
    file: "export/cut-v015.mp4", preview: null })} team={[]} steps={[]} />);
  const player = screen.getByLabelText("Preview: Review cut");
  expect(player.tagName).toBe("VIDEO");
  expect(player.hasAttribute("controls")).toBe(true);
  expect(player.getAttribute("src")).toContain("export/cut-v015.mp4");
  expect(screen.getByRole("button", { name: "Go on with this cut" }).hasAttribute("disabled")).toBe(false);
});

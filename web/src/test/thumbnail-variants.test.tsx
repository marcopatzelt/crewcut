// A thumbnail test card shows every variant with its format name under the image.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ThumbnailVariants, thumbnailVariantsOf } from "../components/CardView";
import { card } from "./helpers";

const variants = [
  { label: "A", format: "house-face-result", format_name: "Face points at the result", kind: "house", image: "graphics/thumbnail/v2/A/a.png" },
  { label: "B", format: "pro-leaning-back", format_name: "Leaning back, it is over", kind: "pro", image: "graphics/thumbnail/v2/B/b.png" },
  { label: "C", format: "pro-old-vs-new", format_name: "Old against new", kind: "pro", image: null },
];

describe("thumbnail variants on the card", () => {
  it("reads the variants only from thumbnail cards", () => {
    expect(thumbnailVariantsOf(card({ kind: "thumbnail", data: { variants } }))).toHaveLength(3);
    expect(thumbnailVariantsOf(card({ kind: "title", data: { variants } }))).toHaveLength(0);
    expect(thumbnailVariantsOf(card({ kind: "thumbnail", data: { variants: "no" } }))).toHaveLength(0);
  });

  it("puts the format name under each variant", () => {
    const c = card({ kind: "thumbnail", episode: "019-x", data: { variants } });
    const { container } = render(<ThumbnailVariants card={c} variants={thumbnailVariantsOf(c)} />);
    const captions = [...container.querySelectorAll("figcaption")].map((f) => f.textContent);
    expect(captions).toEqual([
      "AFace points at the resulthouse style",
      "BLeaning back, it is overpro format",
      "COld against newpro format",
    ]);
    expect(screen.getAllByRole("figure")).toHaveLength(3);
  });
});

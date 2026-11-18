import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { FormattedText } from "../components/FormattedText";

it("renders headings, emphasis, nested lists, quotes and code", () => {
  const { container } = render(<FormattedText text={'# Result\n\n**Important** and *useful*.\n\n1. First\n2. Second\n   - Detail\n\n> Evidence\n\n`file.md`\n\n```js\nconst result = 1;\n```'} />);
  expect(screen.getByRole("heading", { name: "Result", level: 1 })).toBeTruthy();
  expect(container.querySelector("strong")?.textContent).toBe("Important");
  expect(container.querySelector("em")?.textContent).toBe("useful");
  expect(container.querySelector("ol ul li")?.textContent).toBe("Detail");
  expect(container.querySelector("blockquote")?.textContent).toContain("Evidence");
  expect(container.querySelector("pre code")?.textContent).toContain("const result = 1;");
});

it("renders tables and read-only tasks without adding forms", () => {
  const { container } = render(<FormattedText text={'| Model | Cost |\n| --- | --- |\n| Example | $1 |\n\n- [x] Checked\n- [ ] Pending'} />);
  expect(screen.getByRole("columnheader", { name: "Model" })).toBeTruthy();
  expect(screen.getByRole("region", { name: "Table" }).tabIndex).toBe(0);
  expect(screen.getByLabelText("Done")).toBeTruthy();
  expect(screen.getByLabelText("Not done")).toBeTruthy();
  expect(container.querySelector("input")).toBeNull();
});

it("blocks active markup, unsafe links and remote image requests", () => {
  const { container } = render(<FormattedText text={'<script>alert(1)</script>\n\n[Unsafe](javascript:alert) [Local](file:///tmp/file) [Site](https://example.org)\n\n![External image](https://example.org/tracker.png)'} />);
  expect(container.querySelector("script, img, iframe")).toBeNull();
  expect(screen.getAllByRole("link")).toHaveLength(1);
  expect(screen.getByRole("link", { name: "Site" }).getAttribute("rel")).toContain("noopener");
  expect(screen.getByText("External image")).toBeTruthy();
});

import { describe, expect, it } from "vitest";
import { renderMathHoverHtml } from "./renderMathHoverHtml";

describe("renderMathHoverHtml", () => {
  it("renders dark theme with katex markup", () => {
    const html = renderMathHoverHtml("E=mc^2", false, "dark");
    expect(html).toContain("pd-math-hover dark");
    expect(html).toContain("katex");
    expect(html).toContain("E");
  });

  it("renders light theme", () => {
    const html = renderMathHoverHtml("x^2", true, "light");
    expect(html).toContain("pd-math-hover light");
    expect(html).toContain("katex");
  });

  it("shows error-tolerant output on incomplete latex", () => {
    const html = renderMathHoverHtml("\\frac{a", false, "dark");
    expect(html).toContain("pd-math-hover");
  });
});

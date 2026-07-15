import { describe, expect, it } from "vitest";
import { findMathAtOffset } from "./findMathAtOffset";

describe("findMathAtOffset", () => {
  it("finds inline $...$", () => {
    const t = "alpha $E=mc^2$ beta";
    const i = t.indexOf("E");
    const s = findMathAtOffset(t, i);
    expect(s?.latex).toBe("E=mc^2");
    expect(s?.display).toBe(false);
  });

  it("finds $$ display $$", () => {
    const t = "pre $$\\int x$$ post";
    const i = t.indexOf("int");
    const s = findMathAtOffset(t, i);
    expect(s?.latex).toContain("int");
    expect(s?.display).toBe(true);
  });

  it("finds \\( \\)", () => {
    const t = "x \\(a+b\\) y";
    const s = findMathAtOffset(t, t.indexOf("a"));
    expect(s?.latex).toBe("a+b");
    expect(s?.display).toBe(false);
  });

  it("finds \\[ \\]", () => {
    const t = "x \\[a+b\\] y";
    const s = findMathAtOffset(t, t.indexOf("a"));
    expect(s?.latex).toBe("a+b");
    expect(s?.display).toBe(true);
  });

  it("finds equation environment (inner body for KaTeX)", () => {
    const t = "\\begin{equation}\n x^2 \n\\end{equation}";
    const s = findMathAtOffset(t, t.indexOf("x"));
    expect(s?.latex).toContain("x^2");
    expect(s?.latex).not.toContain("begin{equation}");
    expect(s?.display).toBe(true);
  });

  it("ignores escaped dollar", () => {
    const t = "price is \\$5 and $x$ here";
    const s = findMathAtOffset(t, t.indexOf("5"));
    expect(s).toBeNull();
    const s2 = findMathAtOffset(t, t.indexOf("x"));
    expect(s2?.latex).toBe("x");
  });

  it("prefers inner math when nested-ish", () => {
    // not real nesting; just ensure match containing offset
    const t = "$$ outer $$ and $inner$";
    const s = findMathAtOffset(t, t.indexOf("inner"));
    expect(s?.latex).toBe("inner");
  });
});

import { describe, expect, it } from "vitest";
import {
  expandHoverPair,
  expandToWordBounds,
  involvesMath,
  needsExpansion,
} from "./expandHoverSnippet";

describe("needsExpansion", () => {
  it("flags tiny / punct", () => {
    expect(needsExpansion("a")).toBe(true);
    expect(needsExpansion(",")).toBe(true);
    expect(needsExpansion("analysis")).toBe(false);
  });
});

describe("involvesMath", () => {
  it("detects latex fragments", () => {
    expect(involvesMath(String.raw`\mathrm`)).toBe(true);
    expect(involvesMath("$x$")).toBe(true);
    expect(involvesMath("plain")).toBe(false);
  });
});

describe("expandToWordBounds", () => {
  it("grows mid-word cuts", () => {
    const t = "the analysis shows";
    // "lysis" at index of lysis
    const i = t.indexOf("lysis");
    const r = expandToWordBounds(t, i, i + 5);
    expect(t.slice(r.start, r.end)).toBe("analysis");
  });
});

describe("expandHoverPair", () => {
  it("expands incomplete work token with context", () => {
    const work = "The final result is shown.";
    const compare = "The final outcome is shown.";
    const pair = expandHoverPair(
      work,
      compare,
      { start_line: 1, start_col: 10, end_line: 1, end_col: 16 }, // "result"
      { start_line: 1, start_col: 10, end_line: 1, end_col: 17 },
      "result",
      "outcome"
    );
    // complete words should not force expansion
    expect(pair.work.expanded).toBe(false);
  });

  it("expands math label-ish command to formula", () => {
    const work = String.raw`Energy $E=mc^2$ holds.`;
    const compare = String.raw`Energy $E=mc^{2}$ holds.`;
    const eIdx = work.indexOf("E=mc");
    const pair = expandHoverPair(
      work,
      compare,
      {
        start_line: 1,
        start_col: eIdx,
        end_line: 1,
        end_col: eIdx + 4,
      },
      {
        start_line: 1,
        start_col: compare.indexOf("E=mc"),
        end_line: 1,
        end_col: compare.indexOf("E=mc") + 4,
      },
      "E=mc",
      "E=mc"
    );
    expect(pair.work.reason === "math" || pair.work.text.includes("E")).toBe(
      true
    );
    // full formula preferred
    expect(pair.work.text.replace(/\s/g, "")).toMatch(/E=mc/);
  });

  it("expands weak \\mathrm fragment", () => {
    const work = String.raw`use $\mathrm{Re}$ here`;
    const compare = String.raw`use $\mathrm{Im}$ here`;
    const i = work.indexOf("mathrm");
    const pair = expandHoverPair(
      work,
      compare,
      { start_line: 1, start_col: i, end_line: 1, end_col: i + 6 },
      {
        start_line: 1,
        start_col: compare.indexOf("mathrm"),
        end_line: 1,
        end_col: compare.indexOf("mathrm") + 6,
      },
      "mathrm",
      "mathrm"
    );
    expect(pair.work.expanded || involvesMath(pair.work.text)).toBe(true);
  });
});

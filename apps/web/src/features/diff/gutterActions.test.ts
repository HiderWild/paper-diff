import { describe, expect, it } from "vitest";
import { gutterActionsFromUnits } from "./gutterActions";
import type { DiffUnit } from "./sentenceMapper";

describe("gutterActionsFromUnits", () => {
  it("single-line hunk yields hunk+line", () => {
    const u: DiffUnit = {
      id: "h1",
      granularity: "hunk",
      left: { start_line: 3, start_col: 0, end_line: 3, end_col: 5 },
      right: { start_line: 3, start_col: 0, end_line: 3, end_col: 8 },
      leftText: "foo",
      rightText: "foobar",
    };
    const acts = gutterActionsFromUnits([u]);
    expect(acts.some((a) => a.kind === "hunk")).toBe(true);
    expect(acts.some((a) => a.kind === "line")).toBe(true);
  });

  it("multi-line contiguous yields block", () => {
    const u: DiffUnit = {
      id: "h2",
      granularity: "hunk",
      left: { start_line: 1, start_col: 0, end_line: 3, end_col: 1 },
      right: { start_line: 1, start_col: 0, end_line: 3, end_col: 1 },
      leftText: "a\nb\nc",
      rightText: "A\nB\nC",
    };
    const acts = gutterActionsFromUnits([u]);
    expect(acts.some((a) => a.kind === "block")).toBe(true);
    expect(acts.filter((a) => a.kind === "line").length).toBeGreaterThanOrEqual(3);
  });

  it("line units carry real left/right text from parent hunk", () => {
    const u: DiffUnit = {
      id: "h3",
      granularity: "hunk",
      left: { start_line: 1, start_col: 0, end_line: 3, end_col: 1 },
      right: { start_line: 1, start_col: 0, end_line: 3, end_col: 1 },
      leftText: "a\nb\nc",
      rightText: "A\nB\nC",
    };
    const acts = gutterActionsFromUnits([u]);
    const lines = acts.filter((a) => a.kind === "line" && a.unit.parentId === "h3");
    expect(lines.length).toBe(3);
    expect(lines[0].unit.rightText).toBe("A");
    expect(lines[1].unit.rightText).toBe("B");
    expect(lines[2].unit.rightText).toBe("C");
    expect(lines[0].unit.leftText).toBe("a");
  });
});

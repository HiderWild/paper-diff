import { describe, expect, it } from "vitest";
import {
  applyRangeReplace,
  applyUnitToWorkText,
  lineRangePayloadForUnit,
  resolveUnitReplacement,
} from "./applySnippet";
import type { DiffUnit } from "./sentenceMapper";
import { lineColToOffset, sliceRange } from "./sentenceMapper";

describe("applyRangeReplace", () => {
  it("replaces mid-line range (0-based cols)", () => {
    // "Hello world" — cols 6..11 = "world"
    const full = "Hello world\n";
    const out = applyRangeReplace(
      full,
      { start_line: 1, start_col: 6, end_line: 1, end_col: 11 },
      "cosmos"
    );
    expect(out).toBe("Hello cosmos\n");
  });

  it("replaces multi-line span", () => {
    const full = "a\nb\nc\n";
    // line1 col0 through line2 col1 ("a\nb")
    const out = applyRangeReplace(
      full,
      { start_line: 1, start_col: 0, end_line: 2, end_col: 1 },
      "XY"
    );
    expect(out).toBe("XY\nc\n");
  });

  it("inserts when start equals end (empty range)", () => {
    const full = "ab\n";
    const out = applyRangeReplace(
      full,
      { start_line: 1, start_col: 1, end_line: 1, end_col: 1 },
      "X"
    );
    expect(out).toBe("aXb\n");
  });

  it("replaces entire single line content", () => {
    const full = "old line\nnext\n";
    const out = applyRangeReplace(
      full,
      { start_line: 1, start_col: 0, end_line: 1, end_col: 8 },
      "new line"
    );
    expect(out).toBe("new line\nnext\n");
  });

  it("handles end past EOF by clamping", () => {
    const full = "hi";
    const out = applyRangeReplace(
      full,
      { start_line: 1, start_col: 0, end_line: 5, end_col: 99 },
      "bye"
    );
    expect(out).toBe("bye");
  });

  it("handles empty full text insert", () => {
    const out = applyRangeReplace(
      "",
      { start_line: 1, start_col: 0, end_line: 1, end_col: 0 },
      "new"
    );
    expect(out).toBe("new");
  });

  it("matches lineColToOffset / sliceRange round-trip", () => {
    const full = "alpha\nbeta\ngamma";
    const range = { start_line: 2, start_col: 0, end_line: 2, end_col: 4 };
    expect(sliceRange(full, range)).toBe("beta");
    const out = applyRangeReplace(full, range, "BETA");
    expect(out).toBe("alpha\nBETA\ngamma");
    const a = lineColToOffset(full, 2, 0);
    const b = lineColToOffset(full, 2, 4);
    expect(full.slice(a, b)).toBe("beta");
  });

  it("replaces whole file", () => {
    const full = "one\ntwo";
    const endCol = full.split("\n")[1]!.length;
    const out = applyRangeReplace(
      full,
      { start_line: 1, start_col: 0, end_line: 2, end_col: endCol },
      "ALL"
    );
    expect(out).toBe("ALL");
  });
});

describe("resolveUnitReplacement / applyUnitToWorkText", () => {
  const baseUnit = (partial: Partial<DiffUnit>): DiffUnit => ({
    id: "u1",
    granularity: "hunk",
    left: { start_line: 1, start_col: 0, end_line: 1, end_col: 3 },
    right: { start_line: 1, start_col: 0, end_line: 1, end_col: 5 },
    leftText: "foo",
    rightText: "foooo",
    ...partial,
  });

  it("uses unit.rightText when present (not swapped)", () => {
    const u = baseUnit({});
    const { workRange, replacement } = resolveUnitReplacement(u, {
      leftTextFull: "foo\n",
      rightTextFull: "foooo\n",
    });
    expect(workRange).toEqual(u.left);
    expect(replacement).toBe("foooo");
  });

  it("slices from rightTextFull when rightText empty", () => {
    const u = baseUnit({ rightText: "", leftText: "" });
    const rightFull = "HELLO\n";
    const { replacement } = resolveUnitReplacement(u, {
      leftTextFull: "foo\n",
      rightTextFull: rightFull,
    });
    expect(replacement).toBe("HELLO");
  });

  it("when sides swapped, work range is unit.right and text from unit.leftText", () => {
    const u = baseUnit({
      leftText: "from-compare",
      rightText: "from-work",
      left: { start_line: 1, start_col: 0, end_line: 1, end_col: 12 },
      right: { start_line: 1, start_col: 0, end_line: 1, end_col: 9 },
    });
    const { workRange, replacement } = resolveUnitReplacement(u, {
      leftTextFull: "from-work\n",
      rightTextFull: "from-compare\n",
      sidesSwapped: true,
    });
    expect(workRange).toEqual(u.right);
    expect(replacement).toBe("from-compare");
  });

  it("applyUnitToWorkText rewrites work buffer", () => {
    const left = "Hello world\n";
    const right = "Hello cosmos\n";
    const u = baseUnit({
      left: { start_line: 1, start_col: 6, end_line: 1, end_col: 11 },
      right: { start_line: 1, start_col: 6, end_line: 1, end_col: 12 },
      leftText: "world",
      rightText: "cosmos",
    });
    const out = applyUnitToWorkText(left, u, { rightTextFull: right });
    expect(out).toBe("Hello cosmos\n");
  });
});

describe("lineRangePayloadForUnit", () => {
  it("returns null for mid-line (partial col) ranges", () => {
    const left = "Hello world\n";
    const right = "Hello cosmos\n";
    const u: DiffUnit = {
      id: "u1",
      granularity: "hunk",
      left: { start_line: 1, start_col: 6, end_line: 1, end_col: 11 },
      right: { start_line: 1, start_col: 6, end_line: 1, end_col: 12 },
      leftText: "world",
      rightText: "cosmos",
    };
    expect(
      lineRangePayloadForUnit(left, u, { rightTextFull: right })
    ).toBeNull();
  });

  it("maps full-line hunk to start/end lines + replacement", () => {
    const left = "L1\nOLD\nL3\n";
    const right = "L1\nNEWLINE\nL3\n";
    const u: DiffUnit = {
      id: "u1",
      granularity: "hunk",
      left: { start_line: 2, start_col: 0, end_line: 2, end_col: 3 },
      right: { start_line: 2, start_col: 0, end_line: 2, end_col: 7 },
      leftText: "OLD",
      rightText: "NEWLINE",
    };
    expect(lineRangePayloadForUnit(left, u, { rightTextFull: right })).toEqual({
      start_line: 2,
      end_line: 2,
      content: "NEWLINE",
    });
  });

  it("maps multi-line full span", () => {
    const left = "a\nb\nc\nd\n";
    const right = "a\nXY\nd\n";
    const u: DiffUnit = {
      id: "u1",
      granularity: "hunk",
      left: { start_line: 2, start_col: 0, end_line: 3, end_col: 1 },
      right: { start_line: 2, start_col: 0, end_line: 2, end_col: 2 },
      leftText: "b\nc",
      rightText: "XY",
    };
    expect(lineRangePayloadForUnit(left, u, { rightTextFull: right })).toEqual({
      start_line: 2,
      end_line: 3,
      content: "XY",
    });
  });
});

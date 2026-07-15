import { describe, expect, it } from "vitest";
import type { DiffUnit } from "./sentenceMapper";
import {
  hitTestWordUnit,
  rangeContains,
  trueSideForVisualEditor,
  unitCardModel,
  unitToMonacoRange,
  wordUnitsOf,
} from "./wordHover";

function word(
  partial: Partial<DiffUnit> & Pick<DiffUnit, "id" | "left" | "right">
): DiffUnit {
  return {
    granularity: "word",
    leftText: partial.leftText ?? "L",
    rightText: partial.rightText ?? "R",
    ...partial,
  };
}

describe("rangeContains", () => {
  it("matches mid-line exclusive end", () => {
    const r = {
      start_line: 1,
      start_col: 4,
      end_line: 1,
      end_col: 12,
    };
    expect(rangeContains(r, 1, 4)).toBe(true);
    expect(rangeContains(r, 1, 11)).toBe(true);
    expect(rangeContains(r, 1, 12)).toBe(false);
    expect(rangeContains(r, 1, 3)).toBe(false);
  });

  it("matches empty point range at caret", () => {
    const r = {
      start_line: 2,
      start_col: 5,
      end_line: 2,
      end_col: 5,
    };
    expect(rangeContains(r, 2, 5)).toBe(true);
    expect(rangeContains(r, 2, 6)).toBe(false);
  });
});

describe("hitTestWordUnit", () => {
  const units: DiffUnit[] = [
    word({
      id: "w-outer",
      left: { start_line: 1, start_col: 0, end_line: 1, end_col: 20 },
      right: { start_line: 1, start_col: 0, end_line: 1, end_col: 18 },
      leftText: "The analysis shows",
      rightText: "Analysis shows",
    }),
    word({
      id: "w-inner",
      left: { start_line: 1, start_col: 4, end_line: 1, end_col: 12 },
      right: { start_line: 1, start_col: 0, end_line: 1, end_col: 8 },
      leftText: "analysis",
      rightText: "Analysis",
    }),
    {
      id: "h1",
      granularity: "hunk",
      left: { start_line: 1, start_col: 0, end_line: 1, end_col: 20 },
      right: { start_line: 1, start_col: 0, end_line: 1, end_col: 18 },
      leftText: "x",
      rightText: "y",
    },
  ];

  it("prefers smallest containing word unit", () => {
    const hit = hitTestWordUnit(units, "work", 1, 6, false);
    expect(hit?.id).toBe("w-inner");
  });

  it("returns null off range", () => {
    expect(hitTestWordUnit(units, "work", 1, 50, false)).toBeNull();
    expect(hitTestWordUnit(units, "work", 9, 0, false)).toBeNull();
  });

  it("ignores non-word units", () => {
    expect(wordUnitsOf(units)).toHaveLength(2);
  });

  it("maps work to modified editor when sidesSwapped", () => {
    const hit = hitTestWordUnit(units, "work", 1, 6, true);
    // when swapped, work ranges are unit.right — col 6 not in right of w-inner (0..8 includes 6)
    expect(hit?.id).toBe("w-inner");
  });
});

describe("unitCardModel", () => {
  it("labels true work/compare without swap", () => {
    const u = word({
      id: "a",
      left: { start_line: 1, start_col: 0, end_line: 1, end_col: 3 },
      right: { start_line: 1, start_col: 0, end_line: 1, end_col: 3 },
      leftText: "foo",
      rightText: "bar",
    });
    const m = unitCardModel(u, false);
    expect(m.workText).toBe("foo");
    expect(m.compareText).toBe("bar");
  });

  it("flips texts when sidesSwapped", () => {
    const u = word({
      id: "a",
      left: { start_line: 1, start_col: 0, end_line: 1, end_col: 3 },
      right: { start_line: 1, start_col: 0, end_line: 1, end_col: 3 },
      leftText: "dispL",
      rightText: "dispR",
    });
    const m = unitCardModel(u, true);
    expect(m.workText).toBe("dispR");
    expect(m.compareText).toBe("dispL");
  });
});

describe("unitToMonacoRange", () => {
  it("converts 0-based exclusive cols to 1-based Monaco", () => {
    const r = unitToMonacoRange({
      start_line: 2,
      start_col: 0,
      end_line: 2,
      end_col: 5,
    });
    expect(r).toEqual({
      startLineNumber: 2,
      startColumn: 1,
      endLineNumber: 2,
      endColumn: 6,
    });
  });

  it("expands empty ranges by one column", () => {
    const r = unitToMonacoRange({
      start_line: 1,
      start_col: 3,
      end_line: 1,
      end_col: 3,
    });
    expect(r.endColumn).toBe(r.startColumn + 1);
  });
});

describe("trueSideForVisualEditor", () => {
  it("maps editors under swap", () => {
    expect(trueSideForVisualEditor("original", false)).toBe("work");
    expect(trueSideForVisualEditor("modified", false)).toBe("compare");
    expect(trueSideForVisualEditor("original", true)).toBe("compare");
    expect(trueSideForVisualEditor("modified", true)).toBe("work");
  });
});

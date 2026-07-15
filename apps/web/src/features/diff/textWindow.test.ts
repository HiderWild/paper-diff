import { describe, expect, it } from "vitest";
import {
  buildPrefetchPlan,
  clampInterval,
  mergeIntervals,
} from "./textWindow";

describe("clampInterval", () => {
  it("returns null for empty file", () => {
    expect(clampInterval(1, 10, 0)).toBeNull();
  });

  it("clamps to file bounds", () => {
    expect(clampInterval(-5, 3, 10)).toEqual({ start: 1, end: 3 });
    expect(clampInterval(8, 50, 10)).toEqual({ start: 8, end: 10 });
    expect(clampInterval(1, 10, 10)).toEqual({ start: 1, end: 10 });
  });

  it("returns null when entirely past EOF or before start", () => {
    expect(clampInterval(11, 20, 10)).toBeNull();
    expect(clampInterval(-10, -1, 10)).toBeNull();
  });
});

describe("mergeIntervals", () => {
  it("merges overlapping and adjacent", () => {
    expect(
      mergeIntervals([
        { start: 1, end: 3 },
        { start: 3, end: 5 },
        { start: 7, end: 8 },
        { start: 9, end: 10 },
      ])
    ).toEqual([
      { start: 1, end: 5 },
      { start: 7, end: 10 },
    ]);
  });

  it("handles empty / unsorted", () => {
    expect(mergeIntervals([])).toEqual([]);
    expect(
      mergeIntervals([
        { start: 5, end: 6 },
        { start: 1, end: 2 },
      ])
    ).toEqual([
      { start: 1, end: 2 },
      { start: 5, end: 6 },
    ]);
  });
});

describe("buildPrefetchPlan", () => {
  it("returns view then after then before for middle viewport", () => {
    // v0=11, v1=20 → H=10; after 21-30; before 1-10; lineCount=40
    const plan = buildPrefetchPlan(11, 20, 40);
    expect(plan).toEqual([
      { start: 11, end: 20 },
      { start: 21, end: 30 },
      { start: 1, end: 10 },
    ]);
  });

  it("clamps near start (no before)", () => {
    // v0=1, v1=5 → H=5; after 6-10; before empty
    const plan = buildPrefetchPlan(1, 5, 20);
    expect(plan).toEqual([
      { start: 1, end: 5 },
      { start: 6, end: 10 },
    ]);
  });

  it("clamps near end (no after)", () => {
    // v0=16, v1=20 → H=5; after none; before 11-15
    const plan = buildPrefetchPlan(16, 20, 20);
    expect(plan).toEqual([
      { start: 16, end: 20 },
      { start: 11, end: 15 },
    ]);
  });

  it("returns empty for zero lineCount", () => {
    expect(buildPrefetchPlan(1, 10, 0)).toEqual([]);
  });

  it("single-line viewport", () => {
    // v0=v1=5, H=1 → view 5; after 6; before 4
    expect(buildPrefetchPlan(5, 5, 10)).toEqual([
      { start: 5, end: 5 },
      { start: 6, end: 6 },
      { start: 4, end: 4 },
    ]);
  });
});

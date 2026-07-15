import { describe, expect, it } from "vitest";
import {
  countLines,
  DEFAULT_MAX_UNITS,
  diffOptionsForTier,
  estimatePairTier,
  estimateTier,
  TIER_M_MAX_BYTES,
  TIER_M_MAX_LINES,
  TIER_S_MAX_BYTES,
  TIER_S_MAX_LINES,
} from "./largeFileTier";

describe("countLines", () => {
  it("returns 0 for empty", () => {
    expect(countLines("")).toBe(0);
  });

  it("counts single line without newline", () => {
    expect(countLines("hello")).toBe(1);
  });

  it("counts newlines including trailing empty line", () => {
    expect(countLines("a\nb")).toBe(2);
    expect(countLines("a\nb\n")).toBe(3);
  });
});

describe("estimateTier", () => {
  it("classifies small content as S", () => {
    expect(estimateTier(1000)).toBe("S");
    expect(estimateTier(1000, 100)).toBe("S");
    expect(estimateTier(TIER_S_MAX_BYTES - 1, TIER_S_MAX_LINES - 1)).toBe("S");
  });

  it("promotes to M on byte or line threshold", () => {
    expect(estimateTier(TIER_S_MAX_BYTES)).toBe("M");
    expect(estimateTier(100, TIER_S_MAX_LINES)).toBe("M");
    expect(estimateTier(TIER_M_MAX_BYTES, 1)).toBe("M");
    expect(estimateTier(1, TIER_M_MAX_LINES)).toBe("M");
  });

  it("promotes to L above hard ceilings", () => {
    expect(estimateTier(TIER_M_MAX_BYTES + 1)).toBe("L");
    expect(estimateTier(100, TIER_M_MAX_LINES + 1)).toBe("L");
  });

  it("ignores lines when lineCount omitted", () => {
    // Only bytes matter — huge line counts cannot apply without the arg.
    expect(estimateTier(100)).toBe("S");
    expect(estimateTier(TIER_S_MAX_BYTES)).toBe("M");
    expect(estimateTier(TIER_M_MAX_BYTES + 1)).toBe("L");
  });
});

describe("estimatePairTier", () => {
  it("uses the heavier side", () => {
    const small = "a\n";
    const med = "x".repeat(TIER_S_MAX_BYTES);
    expect(estimatePairTier(small, med)).toBe("M");
    expect(estimatePairTier(small, small)).toBe("S");
  });
});

describe("diffOptionsForTier", () => {
  it("keeps S on advanced with full units", () => {
    const o = diffOptionsForTier("S");
    expect(o.diffAlgorithm).toBe("advanced");
    expect(o.maxUnits).toBeNull();
    expect(o.viewportArrowsOnly).toBe(false);
    expect(o.wordUnits).toBe(true);
  });

  it("uses legacy and caps for M/L", () => {
    for (const tier of ["M", "L"] as const) {
      const o = diffOptionsForTier(tier);
      expect(o.diffAlgorithm).toBe("legacy");
      expect(o.maxUnits).toBe(DEFAULT_MAX_UNITS);
      expect(o.viewportArrowsOnly).toBe(true);
      expect(o.wordUnits).toBe(false);
    }
  });
});

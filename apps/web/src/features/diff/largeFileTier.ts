/**
 * Large-file tier thresholds and Monaco/diff L0 options.
 * Pure helpers — unit tested without Monaco.
 *
 * S: small (full advanced path)
 * M: medium (legacy diff, capped units)
 * L: large (legacy + idle unit build; later hunks/window)
 */

export type FileTier = "S" | "M" | "L";

export type DiffOptionsForTier = {
  /** Monaco DiffEditor algorithm */
  diffAlgorithm: "advanced" | "legacy";
  /** Max line-change hunks fed into buildDiffUnits; null = no cap */
  maxUnits: number | null;
  /** Prefer viewport-near gutter arrows only */
  viewportArrowsOnly: boolean;
  /** Build word/sentence units under hunks */
  wordUnits: boolean;
};

/** 256 KiB */
export const TIER_S_MAX_BYTES = 256 * 1024;
/** 2 MiB */
export const TIER_M_MAX_BYTES = 2 * 1024 * 1024;
/** 3k lines */
export const TIER_S_MAX_LINES = 3000;
/** 20k lines */
export const TIER_M_MAX_LINES = 20_000;

/** Default max hunks for M/L unit build (L0). */
export const DEFAULT_MAX_UNITS = 200;

/**
 * Classify content by size/line count.
 * - L: > 2 MiB or > 20k lines
 * - M: ≥ 256 KiB or ≥ 3k lines (and not L)
 * - S: below both M thresholds
 *
 * When `lineCount` is omitted, only byte thresholds apply.
 */
export function estimateTier(
  byteLength: number,
  lineCount?: number
): FileTier {
  const bytes = Math.max(0, byteLength);
  if (
    bytes > TIER_M_MAX_BYTES ||
    (lineCount !== undefined && lineCount > TIER_M_MAX_LINES)
  ) {
    return "L";
  }
  if (
    bytes >= TIER_S_MAX_BYTES ||
    (lineCount !== undefined && lineCount >= TIER_S_MAX_LINES)
  ) {
    return "M";
  }
  return "S";
}

/**
 * Count lines like Monaco: each `\n` starts a new line; empty string → 0.
 * Trailing newline counts as an extra empty line.
 */
export function countLines(text: string): number {
  if (!text) return 0;
  let n = 1;
  for (let i = 0; i < text.length; i++) {
    if (text.charCodeAt(i) === 10 /* \n */) n++;
  }
  return n;
}

/** Derive tier from a left/right pair (heavier side drives thresholds). */
export function estimatePairTier(left: string, right: string): FileTier {
  return estimateTier(
    Math.max(left.length, right.length),
    Math.max(countLines(left), countLines(right))
  );
}

export function diffOptionsForTier(tier: FileTier): DiffOptionsForTier {
  switch (tier) {
    case "S":
      return {
        diffAlgorithm: "advanced",
        maxUnits: null,
        viewportArrowsOnly: false,
        wordUnits: true,
      };
    case "M":
      return {
        diffAlgorithm: "legacy",
        maxUnits: DEFAULT_MAX_UNITS,
        viewportArrowsOnly: true,
        wordUnits: false,
      };
    case "L":
      return {
        diffAlgorithm: "legacy",
        maxUnits: DEFAULT_MAX_UNITS,
        viewportArrowsOnly: true,
        wordUnits: false,
      };
  }
}

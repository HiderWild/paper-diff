/**
 * Word/phrase hover-accept: pure hit-test and card model.
 * Ranges use DiffUnit conventions: lines 1-based, cols 0-based, end exclusive.
 */
import type { DiffUnit, LineColRange } from "./sentenceMapper";

export type TrueSide = "work" | "compare";

export type WordCardModel = {
  unit: DiffUnit;
  workText: string;
  compareText: string;
  /** True if work span is empty (insert into work) */
  isInsert: boolean;
  /** True if compare span is empty (delete from work) */
  isDelete: boolean;
  /** word | sentence | other */
  kind: "word" | "sentence" | "other";
};

/** Word-level units only. */
export function wordUnitsOf(units: DiffUnit[]): DiffUnit[] {
  return units.filter((u) => u.granularity === "word");
}

/** Sentence-level units (aggregated phrases). */
export function sentenceUnitsOf(units: DiffUnit[]): DiffUnit[] {
  return units.filter((u) => u.granularity === "sentence");
}

/**
 * Hit-test word first (smallest), else sentence if includeSentence.
 */
export function hitTestHoverUnit(
  units: DiffUnit[],
  trueSide: TrueSide,
  line: number,
  col0: number,
  sidesSwapped = false,
  includeSentence = true
): DiffUnit | null {
  const word = hitTestWordUnit(units, trueSide, line, col0, sidesSwapped);
  if (word) return word;
  if (!includeSentence) return null;
  const sentences = sentenceUnitsOf(units);
  let best: DiffUnit | null = null;
  let bestSpan = Number.POSITIVE_INFINITY;
  for (const u of sentences) {
    const r = unitRangeForTrueSide(u, trueSide, sidesSwapped);
    if (!rangeContains(r, line, col0)) continue;
    const span = rangeSpanChars(r);
    if (span < bestSpan) {
      bestSpan = span;
      best = u;
    }
  }
  return best;
}

/**
 * Whether (line, col0) lies in range [start, end) in document order.
 * Empty ranges (start == end) match a caret hit within 1 char at start
 * (same line, col0 === start_col or col0 === start_col - 0 only).
 */
export function rangeContains(
  r: LineColRange,
  line: number,
  col0: number
): boolean {
  const sl = r.start_line;
  const el = r.end_line;
  const sc = Math.max(0, r.start_col);
  const ec = Math.max(0, r.end_col);
  if (line < sl || line > el) return false;

  // Empty range: match point on that line at start_col (insert caret)
  if (sl === el && sc === ec) {
    return line === sl && col0 === sc;
  }

  if (sl === el) {
    return col0 >= sc && col0 < ec;
  }
  if (line === sl) return col0 >= sc;
  if (line === el) return col0 < ec;
  return true; // strictly between start and end lines
}

function rangeSpanChars(r: LineColRange): number {
  if (r.start_line === r.end_line) {
    return Math.max(0, r.end_col - r.start_col);
  }
  // Multi-line: coarse span for "smallest" preference
  return (
    Math.max(0, 1000 - r.start_col) +
    Math.max(0, r.end_line - r.start_line - 1) * 80 +
    Math.max(0, r.end_col)
  );
}

/**
 * Map true side (work/compare) to unit.left vs unit.right given display swap.
 * When sidesSwapped, Monaco original shows compare and modified shows work.
 */
export function unitRangeForTrueSide(
  unit: DiffUnit,
  trueSide: TrueSide,
  sidesSwapped: boolean
): LineColRange {
  if (!sidesSwapped) {
    return trueSide === "work" ? unit.left : unit.right;
  }
  return trueSide === "work" ? unit.right : unit.left;
}

/**
 * Hit-test: prefer the **smallest** containing word unit on the given true side.
 */
export function hitTestWordUnit(
  units: DiffUnit[],
  trueSide: TrueSide,
  line: number,
  col0: number,
  sidesSwapped = false
): DiffUnit | null {
  const words = wordUnitsOf(units);
  let best: DiffUnit | null = null;
  let bestSpan = Number.POSITIVE_INFINITY;
  for (const u of words) {
    const r = unitRangeForTrueSide(u, trueSide, sidesSwapped);
    if (!rangeContains(r, line, col0)) continue;
    const span = rangeSpanChars(r);
    if (span < bestSpan) {
      bestSpan = span;
      best = u;
    }
  }
  return best;
}

/**
 * Card model always labels true buffers (work / compare), not visual L/R.
 * Unit texts are relative to Monaco props (display order); swap flips mapping.
 */
export function unitCardModel(
  unit: DiffUnit,
  sidesSwapped = false
): WordCardModel {
  const workText = sidesSwapped ? unit.rightText ?? "" : unit.leftText ?? "";
  const compareText = sidesSwapped ? unit.leftText ?? "" : unit.rightText ?? "";
  const workRange = sidesSwapped ? unit.right : unit.left;
  const compareRange = sidesSwapped ? unit.left : unit.right;
  const isInsert =
    workRange.start_line === workRange.end_line &&
    workRange.start_col === workRange.end_col;
  const isDelete =
    compareRange.start_line === compareRange.end_line &&
    compareRange.start_col === compareRange.end_col;
  const kind =
    unit.granularity === "word"
      ? "word"
      : unit.granularity === "sentence"
        ? "sentence"
        : "other";
  return { unit, workText, compareText, isInsert, isDelete, kind };
}

/** Cap decorations for performance. */
export const MAX_WORD_DECORATIONS = 500;

/**
 * Monaco Range helpers: DiffUnit cols are 0-based exclusive end;
 * Monaco IRange is 1-based, end exclusive for decoration purposes.
 */
export function unitToMonacoRange(r: LineColRange): {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
} {
  const startLineNumber = Math.max(1, r.start_line);
  const endLineNumber = Math.max(startLineNumber, r.end_line);
  let startColumn = Math.max(0, r.start_col) + 1;
  let endColumn = Math.max(0, r.end_col) + 1;
  // Empty range: expand by 1 so decoration is visible / hoverable
  if (
    startLineNumber === endLineNumber &&
    startColumn === endColumn
  ) {
    endColumn = startColumn + 1;
  }
  return { startLineNumber, startColumn, endLineNumber, endColumn };
}

/** Which visual editor shows true work when swapped. */
export function visualEditorForTrueSide(
  trueSide: TrueSide,
  sidesSwapped: boolean
): "original" | "modified" {
  if (!sidesSwapped) {
    return trueSide === "work" ? "original" : "modified";
  }
  return trueSide === "work" ? "modified" : "original";
}

export function trueSideForVisualEditor(
  visual: "original" | "modified",
  sidesSwapped: boolean
): TrueSide {
  if (!sidesSwapped) {
    return visual === "original" ? "work" : "compare";
  }
  return visual === "original" ? "compare" : "work";
}

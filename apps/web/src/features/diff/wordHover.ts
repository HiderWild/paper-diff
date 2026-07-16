/**
 * Word/phrase hover-accept: pure hit-test and card model.
 * Ranges use DiffUnit conventions: lines 1-based, cols 0-based, end exclusive.
 */
import type { DiffUnit, LineColRange } from "./sentenceMapper";
import { expandHoverPair } from "./expandHoverSnippet";

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
  /** Display grew past raw unit slice (math / word / phrase context) */
  displayExpanded?: boolean;
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
 * @param padCols column slack for thin insert/delete ranges
 */
export function hitTestHoverUnit(
  units: DiffUnit[],
  trueSide: TrueSide,
  line: number,
  col0: number,
  sidesSwapped = false,
  includeSentence = true,
  padCols = 0
): DiffUnit | null {
  const word = hitTestWordUnit(
    units,
    trueSide,
    line,
    col0,
    sidesSwapped,
    padCols
  );
  if (word) return word;
  if (!includeSentence) return null;
  const sentences = sentenceUnitsOf(units);
  let best: DiffUnit | null = null;
  let bestScore = Number.POSITIVE_INFINITY;
  for (const u of sentences) {
    const r = unitRangeForTrueSide(u, trueSide, sidesSwapped);
    const pad = padForRange(r, padCols);
    if (!rangeContains(r, line, col0, pad)) continue;
    const span = rangeSpanChars(r);
    const onCoreLine = line >= r.start_line && line <= r.end_line;
    const score = (onCoreLine ? 0 : 1_000_000) + span;
    if (score < bestScore) {
      bestScore = score;
      best = u;
    }
  }
  return best;
}

/** More pad for empty/short ranges (insert/delete UX). */
export function padForRange(r: LineColRange, basePad: number): number {
  if (basePad <= 0) return 0;
  if (isEmptyRange(r)) return Math.max(basePad, 3);
  if (r.start_line === r.end_line && r.end_col - r.start_col <= 2) {
    return Math.max(basePad, 2);
  }
  return basePad;
}

/** True when range is a zero-width caret (pure insert/delete edge). */
export function isEmptyRange(r: LineColRange): boolean {
  return (
    r.start_line === r.end_line &&
    Math.max(0, r.start_col) === Math.max(0, r.end_col)
  );
}

/**
 * Whether (line, col0) lies in range [start, end) in document order.
 * Empty ranges (start == end) match a caret hit at start_col.
 * @param padCols expand hit box by this many 0-based columns on the same line
 *   (and allow ±1 line for empty/short ranges when padCols > 0) — for thin
 *   insert/delete decorations so a shaky pointer still hits.
 */
export function rangeContains(
  r: LineColRange,
  line: number,
  col0: number,
  padCols = 0
): boolean {
  const sl = r.start_line;
  const el = r.end_line;
  const sc = Math.max(0, r.start_col);
  const ec = Math.max(0, r.end_col);
  const pad = Math.max(0, padCols);

  // Empty range: caret with optional column + line padding
  if (sl === el && sc === ec) {
    if (Math.abs(line - sl) > (pad > 0 ? 1 : 0)) return false;
    return col0 >= sc - pad && col0 <= sc + pad;
  }

  // Short single-line span (e.g. 1–2 char delete underline): pad columns only
  if (sl === el) {
    const lo = sc - pad;
    const hi = ec + pad; // end is exclusive; pad expands hi
    if (line === sl) return col0 >= lo && col0 < hi;
    // with pad, allow one adjacent line over the same col band (thin line dexterity)
    if (pad > 0 && Math.abs(line - sl) === 1) {
      return col0 >= lo && col0 < hi;
    }
    return false;
  }

  // Multi-line: only pad start/end columns on edge lines
  if (line < sl - (pad > 0 ? 1 : 0) || line > el + (pad > 0 ? 1 : 0)) {
    return false;
  }
  if (line === sl) return col0 >= sc - pad;
  if (line === el) return col0 < ec + pad;
  if (line > sl && line < el) return true;
  // adjacent padded lines treat as full line hit when pad
  return pad > 0;
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
  sidesSwapped = false,
  padCols = 0
): DiffUnit | null {
  const words = wordUnitsOf(units);
  let best: DiffUnit | null = null;
  let bestScore = Number.POSITIVE_INFINITY;
  for (const u of words) {
    const r = unitRangeForTrueSide(u, trueSide, sidesSwapped);
    const pad = padForRange(r, padCols);
    if (!rangeContains(r, line, col0, pad)) continue;
    const span = rangeSpanChars(r);
    // Prefer non-empty smaller spans; empty ranges use large "virtual" span
    // so a real word under the caret still wins when both match.
    const rankSpan = isEmptyRange(r) ? span + 50 : span;
    // Strongly prefer ranges whose real line band includes the cursor line
    // (not only adjacent-line pad). Avoids latching onto a unit above.
    const onCoreLine = line >= r.start_line && line <= r.end_line;
    const score = (onCoreLine ? 0 : 1_000_000) + rankSpan;
    if (score < bestScore) {
      bestScore = score;
      best = u;
    }
  }
  return best;
}

/**
 * Card model always labels true buffers (work / compare), not visual L/R.
 * Unit texts are relative to Monaco props (display order); swap flips mapping.
 *
 * @param fullLeft Monaco props.left buffer (original pane)
 * @param fullRight Monaco props.right buffer (modified pane)
 * When provided, may expand display snippets for math / incomplete tokens.
 */
export function unitCardModel(
  unit: DiffUnit,
  sidesSwapped = false,
  fullLeft?: string,
  fullRight?: string
): WordCardModel {
  let workText = sidesSwapped ? unit.rightText ?? "" : unit.leftText ?? "";
  let compareText = sidesSwapped ? unit.leftText ?? "" : unit.rightText ?? "";
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

  let displayExpanded = false;
  if (fullLeft != null && fullRight != null && !isInsert && !isDelete) {
    // Map true-side full texts
    const workFull = sidesSwapped ? fullRight : fullLeft;
    const compareFull = sidesSwapped ? fullLeft : fullRight;
    const expanded = expandHoverPair(
      workFull,
      compareFull,
      workRange,
      compareRange,
      workText,
      compareText
    );
    workText = expanded.work.text;
    compareText = expanded.compare.text;
    displayExpanded = expanded.work.expanded || expanded.compare.expanded;
  }

  return {
    unit,
    workText,
    compareText,
    isInsert,
    isDelete,
    kind,
    displayExpanded,
  };
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

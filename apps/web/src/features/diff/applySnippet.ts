/**
 * Client-side true-source apply: replace a line/col range in work text
 * with the visible compare-side snippet.
 *
 * Cols are 0-based (same as DiffUnit / sentenceMapper.lineColToOffset).
 * Lines are 1-based.
 */
import {
  lineColToOffset,
  sliceRange,
  type DiffUnit,
  type LineColRange,
} from "./sentenceMapper";

export type ApplyRange = {
  start_line: number;
  start_col: number;
  end_line: number;
  end_col: number;
};

/**
 * Replace [start, end) described by line/col in fullText with replacement.
 * Offsets are clamped to [0, fullText.length].
 */
export function applyRangeReplace(
  fullText: string,
  range: ApplyRange,
  replacement: string
): string {
  const startLine = Math.max(1, range.start_line || 1);
  const endLine = Math.max(1, range.end_line || startLine);
  const startCol = Math.max(0, range.start_col || 0);
  const endCol = Math.max(0, range.end_col || 0);

  let a = lineColToOffset(fullText, startLine, startCol);
  let b = lineColToOffset(fullText, endLine, endCol);
  if (a < 0) a = 0;
  if (b < 0) b = 0;
  if (a > fullText.length) a = fullText.length;
  if (b > fullText.length) b = fullText.length;
  if (b < a) b = a;
  return fullText.slice(0, a) + replacement + fullText.slice(b);
}

/**
 * Resolve the compare-side replacement text for a unit given full buffers.
 * When sides are swapped, Monaco unit.left is the compare side.
 */
export function resolveUnitReplacement(
  unit: DiffUnit,
  opts: {
    rightTextFull: string;
    leftTextFull: string;
    sidesSwapped?: boolean;
  }
): { workRange: LineColRange; replacement: string } {
  const swapped = !!opts.sidesSwapped;
  const workRange = (swapped ? unit.right : unit.left) as LineColRange;
  const compareRange = (swapped ? unit.left : unit.right) as LineColRange;
  // Missing text on unit → slice from full compare buffer.
  // Empty string is still "present"; only nullish falls back.
  // Callers that only have empty strings should omit via slice path by
  // setting text to a sentinel: we treat both nullish AND intentional
  // empty after checking hasOwn: use empty → delete when length known
  // from range; if unit text is empty AND range has positive span on
  // compare side, prefer slice (covers gutter units that left "" wrongly).
  let replacement: string | null | undefined = swapped
    ? unit.leftText
    : unit.rightText;
  if (replacement == null) {
    replacement = sliceRange(opts.rightTextFull, compareRange);
  } else if (replacement === "") {
    const sliced = sliceRange(opts.rightTextFull, compareRange);
    // If slice also empty, keep delete; if slice non-empty, unit lied → use slice
    if (sliced !== "") replacement = sliced;
  }
  return { workRange, replacement };
}

/**
 * Pure: apply a DiffUnit onto work full text using compare buffers.
 */
export function applyUnitToWorkText(
  leftTextFull: string,
  unit: DiffUnit,
  opts: {
    rightTextFull: string;
    sidesSwapped?: boolean;
  }
): string {
  const { workRange, replacement } = resolveUnitReplacement(unit, {
    leftTextFull,
    rightTextFull: opts.rightTextFull,
    sidesSwapped: opts.sidesSwapped,
  });
  return applyRangeReplace(leftTextFull, workRange, replacement);
}

/**
 * When unit replace spans full lines on the work side (start_col=0 and end at
 * line end / past end), map to backend file-range line splice payload.
 * Partial mid-line ranges return null → caller should full putWorkFile.
 *
 * Backend splice_text_lines replaces whole lines [start_line, end_line]
 * with content.splitlines(); content may be multi-line (no need trailing \n
 * except when intentional empty-line preservation is desired).
 */
export function lineRangePayloadForUnit(
  leftTextFull: string,
  unit: DiffUnit,
  opts: {
    rightTextFull: string;
    sidesSwapped?: boolean;
  }
): { start_line: number; end_line: number; content: string } | null {
  const { workRange, replacement } = resolveUnitReplacement(unit, {
    leftTextFull,
    rightTextFull: opts.rightTextFull,
    sidesSwapped: opts.sidesSwapped,
  });
  const startLine = Math.max(1, workRange.start_line || 1);
  const endLine = Math.max(startLine, workRange.end_line || startLine);
  const startCol = Math.max(0, workRange.start_col || 0);
  if (startCol !== 0) return null;

  const lines = leftTextFull.split("\n");
  // Pure insert at start of a line (empty span, col 0..0) → treat as replace that line?
  // Backend needs inclusive range. For empty point insert at (L,0)-(L,0) we cannot
  // use line-range safely without shifting content mid-line context; fall back.
  const endCol = Math.max(0, workRange.end_col || 0);
  if (startLine === endLine && startCol === endCol) return null;

  const lastLineIdx = endLine - 1;
  if (lastLineIdx < 0 || lastLineIdx >= lines.length) {
    // end past last content line: allow only if covering through EOF start
    if (endLine > lines.length && startLine <= lines.length && startCol === 0) {
      // replace from startLine through end of file
      return {
        start_line: startLine,
        end_line: Math.max(startLine, lines.length || startLine),
        content: replacement,
      };
    }
    return null;
  }
  const endLineLen = lines[lastLineIdx]?.length ?? 0;
  // Full line: end_col at or past line length. Empty line: end_col===0===length.
  if (endCol < endLineLen) return null;

  return {
    start_line: startLine,
    end_line: endLine,
    content: replacement,
  };
}

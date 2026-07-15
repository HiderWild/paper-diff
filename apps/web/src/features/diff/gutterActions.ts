/**
 * Collapse Monaco line changes into gutter arrow actions:
 * - line: single changed line
 * - block: consecutive non-blank-separated changed lines
 * - hunk: full Monaco line-change span (already a "chunk")
 */
import {
  sliceRange,
  type DiffUnit,
  type LineChange,
  type LineColRange,
} from "./sentenceMapper";

export type GutterAction = {
  id: string;
  kind: "line" | "block" | "hunk";
  /** 1-based line on the left (work) editor for vertical placement */
  leftLine: number;
  /** Corresponding unit to feed accept API when available */
  unit: DiffUnit;
  labelKey: "gutter.pullLine" | "gutter.pullBlock" | "gutter.pullHunk";
};

/** Slice a single line from a hunk's text using the line index within the hunk. */
function lineSliceFromHunkText(
  hunkText: string,
  lineIndex: number
): string {
  const lines = hunkText.split("\n");
  if (lines.length === 0) return "";
  const idx = Math.max(0, Math.min(lineIndex, lines.length - 1));
  return lines[idx] ?? "";
}

function singleLineRange(
  line: number,
  textOnLine: string,
  fallbackEndCol: number
): LineColRange {
  return {
    start_line: line,
    start_col: 0,
    end_line: line,
    end_col: textOnLine.length > 0 ? textOnLine.length : Math.max(0, fallbackEndCol),
  };
}

export function gutterActionsFromUnits(units: DiffUnit[]): GutterAction[] {
  const hunks = units.filter((u) => u.granularity === "hunk");
  const out: GutterAction[] = [];

  for (const h of hunks) {
    const leftStart = h.left.start_line;
    const leftEnd = Math.max(h.left.end_line, h.left.start_line);
    const lines = leftEnd - leftStart + 1;

    // Always offer full hunk at start of range
    out.push({
      id: `hunk-${h.id}`,
      kind: "hunk",
      leftLine: leftStart || 1,
      unit: h,
      labelKey: "gutter.pullHunk",
    });

    if (lines <= 1) {
      // Single-line: also as line arrow (same unit)
      out.push({
        id: `line-${h.id}`,
        kind: "line",
        leftLine: leftStart || 1,
        unit: h,
        labelKey: "gutter.pullLine",
      });
      continue;
    }

    // Multi-line: offer per-line pseudo units with real text slices from parent hunk
    for (let ln = leftStart; ln <= leftEnd; ln++) {
      if (ln <= 0) continue;
      const idx = ln - leftStart;
      const leftLineText = lineSliceFromHunkText(h.leftText, idx);
      // Map proportionally into right lines when counts differ
      const rightLineCount = Math.max(1, h.rightText.split("\n").length);
      const rightIdx = Math.min(
        idx,
        rightLineCount - 1,
        Math.max(0, h.right.end_line - h.right.start_line)
      );
      const rightLineText = lineSliceFromHunkText(h.rightText, rightIdx);
      const rightLine = Math.min(
        h.right.end_line,
        Math.max(h.right.start_line, h.right.start_line + rightIdx)
      );
      const lineUnit: DiffUnit = {
        id: `${h.id}-L${ln}`,
        granularity: "hunk",
        left: singleLineRange(ln, leftLineText, h.left.end_col),
        right: singleLineRange(rightLine, rightLineText, h.right.end_col),
        leftText: leftLineText,
        rightText: rightLineText,
        parentId: h.id,
      };
      out.push({
        id: `line-${h.id}-${ln}`,
        kind: "line",
        leftLine: ln,
        unit: lineUnit,
        labelKey: "gutter.pullLine",
      });
    }

    // Block: treat entire multi-line contiguous hunk as block (no blank lines inside slice)
    const hasInternalBlank =
      /\n\s*\n/.test(h.leftText) || /\n\s*\n/.test(h.rightText);
    if (!hasInternalBlank && lines > 1) {
      out.push({
        id: `block-${h.id}`,
        kind: "block",
        leftLine: leftStart || 1,
        unit: h,
        labelKey: "gutter.pullBlock",
      });
    }
  }

  // Dedupe: prefer one action per (kind,leftLine) keeping first
  const seen = new Set<string>();
  return out.filter((a) => {
    const k = `${a.kind}:${a.leftLine}:${a.unit.id}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

export function lineChangesToRoughUnits(
  leftText: string,
  rightText: string,
  changes: LineChange[]
): DiffUnit[] {
  return changes.map((lc, i) => {
    const leftStart = lc.originalStartLineNumber || 1;
    const leftEnd = lc.originalEndLineNumber || leftStart;
    const rightStart = lc.modifiedStartLineNumber || 1;
    const rightEnd = lc.modifiedEndLineNumber || rightStart;
    const leftLines = leftText.split("\n");
    const rightLines = rightText.split("\n");
    const leftEndCol =
      leftEnd >= leftStart ? (leftLines[leftEnd - 1]?.length ?? 0) : 0;
    const rightEndCol =
      rightEnd >= rightStart ? (rightLines[rightEnd - 1]?.length ?? 0) : 0;
    const left: LineColRange = {
      start_line: leftStart,
      start_col: 0,
      end_line: Math.max(leftEnd, leftStart),
      end_col: leftEndCol,
    };
    const right: LineColRange = {
      start_line: rightStart,
      start_col: 0,
      end_line: Math.max(rightEnd, rightStart),
      end_col: rightEndCol,
    };
    return {
      id: `lc-${i}`,
      granularity: "hunk" as const,
      left,
      right,
      leftText: sliceRange(leftText, left),
      rightText: sliceRange(rightText, right),
    };
  });
}

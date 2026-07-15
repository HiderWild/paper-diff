/**
 * Collapse Monaco line changes into gutter arrow actions:
 * - line: single changed line
 * - block: consecutive non-blank-separated changed lines
 * - hunk: full Monaco line-change span (already a "chunk")
 */
import type { DiffUnit, LineChange } from "./sentenceMapper";

export type GutterAction = {
  id: string;
  kind: "line" | "block" | "hunk";
  /** 1-based line on the left (work) editor for vertical placement */
  leftLine: number;
  /** Corresponding unit to feed accept API when available */
  unit: DiffUnit;
  labelKey: "gutter.pullLine" | "gutter.pullBlock" | "gutter.pullHunk";
};

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

    // Multi-line: offer per-line pseudo units (range = single line both sides)
    for (let ln = leftStart; ln <= leftEnd; ln++) {
      if (ln <= 0) continue;
      const lineUnit: DiffUnit = {
        id: `${h.id}-L${ln}`,
        granularity: "hunk",
        left: {
          start_line: ln,
          start_col: 0,
          end_line: ln,
          end_col: h.left.end_col,
        },
        right: {
          start_line: Math.min(
            h.right.end_line,
            h.right.start_line + (ln - leftStart)
          ),
          start_col: 0,
          end_line: Math.min(
            h.right.end_line,
            h.right.start_line + (ln - leftStart)
          ),
          end_col: h.right.end_col,
        },
        leftText: "",
        rightText: "",
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
    const hasInternalBlank = /\n\s*\n/.test(h.leftText) || /\n\s*\n/.test(h.rightText);
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
  // thin wrapper — reuse hierarchy from buildDiffUnits when available at call site
  void leftText;
  void rightText;
  return changes.map((lc, i) => ({
    id: `lc-${i}`,
    granularity: "hunk" as const,
    left: {
      start_line: lc.originalStartLineNumber || 1,
      start_col: 0,
      end_line: lc.originalEndLineNumber || lc.originalStartLineNumber || 1,
      end_col: 0,
    },
    right: {
      start_line: lc.modifiedStartLineNumber || 1,
      start_col: 0,
      end_line: lc.modifiedEndLineNumber || lc.modifiedStartLineNumber || 1,
      end_col: 0,
    },
    leftText: "",
    rightText: "",
  }));
}

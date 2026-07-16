/**
 * Expand tiny/fragment word-hover snippets with surrounding context so the
 * card stays readable. Apply still uses the original DiffUnit range.
 *
 * Rules (priority):
 * 1. Math involvement → expand each side to enclosing $...$ / \(...\) / \[...\] / env.
 * 2. Incomplete token (mid-word, dangling \, pure punctuation) → expand to word bounds.
 * 3. Still weak (no letters, very short) → widen to a short phrase window (±N chars
 *    or nearest punctuation).
 */

import type { LineColRange } from "./sentenceMapper";
import { findMathAtOffset } from "../viewer/findMathAtOffset";

const WORD_CHAR = /[\p{L}\p{N}_@]/u;
/** Tokens that alone are almost never meaningful replacements */
const WEAK_ONLY = /^[\s\p{P}\p{S}\\{}[\]()]+$/u;

export type ExpandedSide = {
  text: string;
  /** True when we grew beyond the raw unit slice */
  expanded: boolean;
  reason?: "math" | "word" | "phrase";
};

export type ExpandedPair = {
  work: ExpandedSide;
  compare: ExpandedSide;
};

export function lineColToOffset(
  text: string,
  line: number,
  col0: number
): number {
  const lines = text.split("\n");
  let off = 0;
  const maxL = Math.min(lines.length, Math.max(1, line));
  for (let i = 1; i < maxL; i++) {
    off += (lines[i - 1]?.length ?? 0) + 1;
  }
  const lineText = lines[maxL - 1] ?? "";
  return off + Math.min(Math.max(0, col0), lineText.length);
}

export function offsetToLineCol(
  text: string,
  offset: number
): { line: number; col0: number } {
  const o = Math.max(0, Math.min(offset, text.length));
  const before = text.slice(0, o);
  const parts = before.split("\n");
  return {
    line: parts.length,
    col0: parts[parts.length - 1]?.length ?? 0,
  };
}

export function sliceOffsets(text: string, start: number, end: number): string {
  return text.slice(
    Math.max(0, Math.min(start, text.length)),
    Math.max(0, Math.min(end, text.length))
  );
}

export function needsExpansion(snippet: string): boolean {
  const s = snippet ?? "";
  if (!s) return true;
  if (s.length <= 2) return true;
  if (WEAK_ONLY.test(s)) return true;
  // dangling backslash / incomplete command
  if (/\\$/.test(s) || /^[a-zA-Z@]+$/.test(s) && s.length <= 3) {
    // short identifier-like ok if word-looking; expand if purely command tail
  }
  if (/\\[a-zA-Z@]*$/.test(s) && !/\\[a-zA-Z@]+(\{|\[|$)/.test(s)) {
    // ends mid-command name without {
    if (!s.includes("{") && s.includes("\\")) return true;
  }
  // unbalanced $
  const dollars = (s.match(/(?<!\\)\$/g) || []).length;
  if (dollars % 2 === 1) return true;
  return false;
}

export function involvesMath(snippet: string): boolean {
  if (!snippet) return false;
  if (/(?<!\\)\$|\\\(|\\\[|\\begin\s*\{/.test(snippet)) return true;
  // common math-only fragments
  if (/\\(frac|sum|int|mathrm|mathbf|mathbb|left|right)\b/.test(snippet))
    return true;
  return false;
}

/** Grow [start,end) to word boundaries when range cuts mid-token. */
export function expandToWordBounds(
  text: string,
  start: number,
  end: number
): { start: number; end: number } {
  let s = Math.max(0, Math.min(start, text.length));
  let e = Math.max(s, Math.min(end, text.length));
  while (s > 0 && WORD_CHAR.test(text[s - 1]!)) s--;
  while (e < text.length && WORD_CHAR.test(text[e]!)) e++;
  // also swallow a trailing \command prefix: if start sits after '\'
  if (s > 0 && text[s - 1] === "\\") {
    let j = s - 1;
    // include full \name
    s = j;
    j = s + 1;
    while (j < e && /[a-zA-Z@*]/.test(text[j]!)) j++;
    // include one optional braced group
    if (text[j] === "{") {
      let depth = 0;
      for (; j < text.length; j++) {
        if (text[j] === "{") depth++;
        else if (text[j] === "}") {
          depth--;
          if (depth === 0) {
            j++;
            break;
          }
        }
      }
      e = Math.max(e, j);
    }
  }
  return { start: s, end: e };
}

/** Small phrase window for otherwise meaningless snippets. */
export function expandToPhrase(
  text: string,
  start: number,
  end: number,
  maxExtra = 28
): { start: number; end: number } {
  let s = Math.max(0, start - maxExtra);
  let e = Math.min(text.length, end + maxExtra);
  // snap to nearby whitespace / punctuation for cleaner edges
  while (s > 0 && !/[\s,;:。，；]/.test(text[s - 1]!) && start - s < maxExtra)
    s--;
  while (
    e < text.length &&
    !/[\s,;:。，；]/.test(text[e]!) &&
    e - end < maxExtra
  )
    e++;
  return { start: s, end: e };
}

function expandSide(
  full: string,
  range: LineColRange,
  rawSnippet: string,
  peerSnippet: string
): ExpandedSide {
  const start = lineColToOffset(full, range.start_line, range.start_col);
  const end = lineColToOffset(full, range.end_line, range.end_col);
  const base = {
    start: Math.min(start, end),
    end: Math.max(start, end),
  };

  const mathish =
    involvesMath(rawSnippet) ||
    involvesMath(peerSnippet) ||
    needsMathGlue(full, base.start, base.end);

  if (mathish) {
    const mid = Math.floor((base.start + base.end) / 2);
    const snip = findMathAtOffset(full, mid);
    if (
      snip &&
      snip.startOffset <= base.start &&
      snip.endOffset >= base.end
    ) {
      // whole formula contains the change
      return {
        text: snip.latex,
        expanded: snip.startOffset < base.start || snip.endOffset > base.end,
        reason: "math",
      };
    }
    // try nearby offsets if mid miss
    for (const o of [base.start, Math.max(0, base.start - 1), base.end]) {
      const s2 = findMathAtOffset(full, o);
      if (s2) {
        return {
          text: s2.latex,
          expanded: true,
          reason: "math",
        };
      }
    }
  }

  if (needsExpansion(rawSnippet) || cutsMidWord(full, base.start, base.end)) {
    const w = expandToWordBounds(full, base.start, base.end);
    let s = w.start;
    let e = w.end;
    let reason: ExpandedSide["reason"] = "word";
    const grown = sliceOffsets(full, s, e);
    if (needsExpansion(grown) || grown.length <= (rawSnippet?.length ?? 0)) {
      const p = expandToPhrase(full, s, e);
      s = p.start;
      e = p.end;
      reason = "phrase";
    }
    const text = sliceOffsets(full, s, e);
    return {
      text,
      expanded: s < base.start || e > base.end,
      reason,
    };
  }

  return { text: rawSnippet, expanded: false };
}

function cutsMidWord(text: string, start: number, end: number): boolean {
  if (start > 0 && WORD_CHAR.test(text[start - 1]!) && WORD_CHAR.test(text[start] ?? " "))
    return true;
  if (
    end < text.length &&
    WORD_CHAR.test(text[end - 1] ?? " ") &&
    WORD_CHAR.test(text[end]!)
  )
    return true;
  return false;
}

function needsMathGlue(full: string, start: number, end: number): boolean {
  // range sits inside a math region
  const mid = Math.floor((start + end) / 2);
  const snip = findMathAtOffset(full, mid);
  if (!snip) return false;
  // partial overlap only — change is inside formula
  return snip.startOffset < end && snip.endOffset > start;
}

/**
 * Expand work/compare display for hover card.
 * fullWork / fullCompare are true-side full buffers (not display-swapped).
 */
export function expandHoverPair(
  workFull: string,
  compareFull: string,
  workRange: LineColRange,
  compareRange: LineColRange,
  workSnippet: string,
  compareSnippet: string
): ExpandedPair {
  // If either side needs context, expand both so the pair stays comparable.
  const eitherWeak =
    needsExpansion(workSnippet) ||
    needsExpansion(compareSnippet) ||
    involvesMath(workSnippet) ||
    involvesMath(compareSnippet) ||
    needsMathGlue(
      workFull,
      lineColToOffset(workFull, workRange.start_line, workRange.start_col),
      lineColToOffset(workFull, workRange.end_line, workRange.end_col)
    ) ||
    needsMathGlue(
      compareFull,
      lineColToOffset(
        compareFull,
        compareRange.start_line,
        compareRange.start_col
      ),
      lineColToOffset(compareFull, compareRange.end_line, compareRange.end_col)
    );

  if (!eitherWeak) {
    return {
      work: { text: workSnippet, expanded: false },
      compare: { text: compareSnippet, expanded: false },
    };
  }

  // Prefer joint math expand: if one side is math, try both at corresponding offsets
  return {
    work: expandSide(workFull, workRange, workSnippet, compareSnippet),
    compare: expandSide(
      compareFull,
      compareRange,
      compareSnippet,
      workSnippet
    ),
  };
}

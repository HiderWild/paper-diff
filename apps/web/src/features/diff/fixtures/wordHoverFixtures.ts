/**
 * Golden string fixtures for word/phrase hover-accept (Phase 0).
 * Used by unit tests; also a quick reference for manual smoke.
 */
import type { DiffUnit } from "../sentenceMapper";

export type WordHoverFixture = {
  id: string;
  /** short description */
  note: string;
  work: string;
  compare: string;
  /** Expected primary word unit after buildDiffUnits with synthetic line change */
  expectedWord?: {
    workText: string;
    compareText: string;
  };
};

/** Single mid-phrase token change */
export const FIX_SINGLE_TOKEN: WordHoverFixture = {
  id: "single-token",
  note: "The analysis → The review (one word)",
  work: "The analysis shows that.\n",
  compare: "The review shows that.\n",
  expectedWord: { workText: "analysis", compareText: "review" },
};

/** Multi-token same line */
export const FIX_MULTI_TOKEN: WordHoverFixture = {
  id: "multi-token",
  note: "several tokens differ on one line",
  work: "alpha beta gamma\n",
  compare: "alpha BETA delta\n",
};

/** Insert-only into work (empty left span conceptually) */
export const FIX_INSERT: WordHoverFixture = {
  id: "insert-only",
  note: "work missing a word that compare has",
  work: "Hello world\n",
  compare: "Hello big world\n",
};

/** Delete-only from work */
export const FIX_DELETE: WordHoverFixture = {
  id: "delete-only",
  note: "work has extra word",
  work: "Hello big world\n",
  compare: "Hello world\n",
};

/** LaTeX-ish command token */
export const FIX_LATEX: WordHoverFixture = {
  id: "latex-cmd",
  note: "LaTeX command change",
  work: "Use \\emph{x} here.\n",
  compare: "Use \\textbf{x} here.\n",
  expectedWord: { workText: "\\emph", compareText: "\\textbf" },
};

export const ALL_WORD_HOVER_FIXTURES: WordHoverFixture[] = [
  FIX_SINGLE_TOKEN,
  FIX_MULTI_TOKEN,
  FIX_INSERT,
  FIX_DELETE,
  FIX_LATEX,
];

/** Build a minimal synthetic word unit for apply tests. */
export function syntheticWordUnit(
  workText: string,
  compareText: string,
  workStartCol: number,
  workEndCol: number,
  compareStartCol: number,
  compareEndCol: number,
  line = 1
): DiffUnit {
  return {
    id: "fixture-word",
    granularity: "word",
    left: {
      start_line: line,
      start_col: workStartCol,
      end_line: line,
      end_col: workEndCol,
    },
    right: {
      start_line: line,
      start_col: compareStartCol,
      end_line: line,
      end_col: compareEndCol,
    },
    leftText: workText,
    rightText: compareText,
  };
}

/**
 * Locate LaTeX math under a character offset (for hover preview).
 * Supports $...$, $$...$$, \(...\), \[...\], and common math environments.
 */

export type MathSnippet = {
  /** Inner LaTeX (delimiters stripped for $ / $$ / \( \) / \[ \]; environments keep begin/end) */
  latex: string;
  display: boolean;
  startOffset: number;
  endOffset: number;
};

const ENV_NAMES =
  "equation\\*?|align\\*?|alignat\\*?|flalign\\*?|gather\\*?|multline\\*?|eqnarray\\*?|displaymath|math";

function isEscapedDollar(text: string, i: number): boolean {
  // odd number of preceding backslashes escapes $
  let n = 0;
  let j = i - 1;
  while (j >= 0 && text[j] === "\\") {
    n++;
    j--;
  }
  return n % 2 === 1;
}

type Span = { start: number; end: number; latex: string; display: boolean };

function collectDollarSpans(text: string): Span[] {
  const spans: Span[] = [];
  let i = 0;
  while (i < text.length) {
    if (text[i] !== "$" || isEscapedDollar(text, i)) {
      i++;
      continue;
    }
    // $$ display
    if (text[i + 1] === "$") {
      const open = i;
      let j = i + 2;
      while (j < text.length - 1) {
        if (text[j] === "$" && text[j + 1] === "$" && !isEscapedDollar(text, j)) {
          const inner = text.slice(open + 2, j);
          spans.push({
            start: open,
            end: j + 2,
            latex: inner,
            display: true,
          });
          i = j + 2;
          break;
        }
        j++;
      }
      if (j >= text.length - 1) break;
      continue;
    }
    // single $
    const open = i;
    let j = i + 1;
    while (j < text.length) {
      if (text[j] === "$" && !isEscapedDollar(text, j)) {
        // skip empty
        if (j > open + 1) {
          spans.push({
            start: open,
            end: j + 1,
            latex: text.slice(open + 1, j),
            display: false,
          });
        }
        i = j + 1;
        break;
      }
      // unescaped newline ends failed inline search (display uses $$ only)
      if (text[j] === "\n") {
        i = open + 1;
        break;
      }
      j++;
    }
    if (j >= text.length) break;
  }
  return spans;
}

function collectParenSpans(text: string): Span[] {
  const spans: Span[] = [];
  // \( ... \)
  const reInline = /\\\(([\s\S]*?)\\\)/g;
  let m: RegExpExecArray | null;
  while ((m = reInline.exec(text))) {
    spans.push({
      start: m.index,
      end: m.index + m[0].length,
      latex: m[1] || "",
      display: false,
    });
  }
  // \[ ... \]
  const reDisp = /\\\[([\s\S]*?)\\\]/g;
  while ((m = reDisp.exec(text))) {
    spans.push({
      start: m.index,
      end: m.index + m[0].length,
      latex: m[1] || "",
      display: true,
    });
  }
  return spans;
}

function collectEnvSpans(text: string): Span[] {
  const spans: Span[] = [];
  const re = new RegExp(
    `\\\\begin\\{(${ENV_NAMES})\\}([\\s\\S]*?)\\\\end\\{\\1\\}`,
    "g"
  );
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    const full = m[0];
    // KaTeX does not fully emulate LaTeX envs — preview inner body as display math
    const inner = (m[2] || "").trim();
    spans.push({
      start: m.index,
      end: m.index + full.length,
      latex: inner || full,
      display: true,
    });
  }
  return spans;
}

/** Prefer smallest span containing offset (innermost). */
export function findMathAtOffset(
  text: string,
  offset: number
): MathSnippet | null {
  if (offset < 0 || offset > text.length) return null;
  const all = [
    ...collectDollarSpans(text),
    ...collectParenSpans(text),
    ...collectEnvSpans(text),
  ];
  // offset may be at end of formula — treat end as inclusive for last char
  const hits = all.filter((s) => offset >= s.start && offset <= s.end);
  if (!hits.length) return null;
  hits.sort((a, b) => a.end - a.start - (b.end - b.start));
  const best = hits[0]!;
  const latex = best.latex.trim();
  if (!latex) return null;
  return {
    latex,
    display: best.display,
    startOffset: best.start,
    endOffset: best.end,
  };
}

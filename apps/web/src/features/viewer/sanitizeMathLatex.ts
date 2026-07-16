/**
 * Strip LaTeX constructs that must not appear in KaTeX hover preview
 * (ref anchors, tags, numbering helpers, comments, etc.).
 */

/** Optional braced arg `{...}` with light nesting for \label{eq:a_1}. */
const BRACED = String.raw`\{(?:[^{}]|\{[^{}]*\})*\}`;

/**
 * Commands that only affect cross-refs / numbering — omit from render.
 * Keeps the math body; does not rewrite structural math macros.
 */
const STRIP_CMDS = [
  "label",
  "tag",
  "notag",
  "nonumber",
  "eqref",
  "ref",
  "pageref",
  "cite",
  "citep",
  "hypertarget",
  "hyperlink",
  "index",
  "glossary",
  "footnote",
  "marginpar",
];

export function sanitizeMathLatex(latex: string): string {
  let s = latex;

  // Line comments in displayed multi-line math
  s = s.replace(/(^|[^\\])%.*$/gm, "$1");

  for (const cmd of STRIP_CMDS) {
    // \cmd*{...} or \cmd{...} or bare \cmd (nonumber etc.)
    const reStarBrace = new RegExp(String.raw`\\${cmd}\*?\s*${BRACED}`, "g");
    s = s.replace(reStarBrace, "");
    const reBare = new RegExp(String.raw`\\${cmd}\b\*?(?![a-zA-Z@])`, "g");
    s = s.replace(reBare, "");
  }

  // leftover whitespace after stripping labels
  s = s.replace(/[ \t]+\n/g, "\n");
  s = s.replace(/\n{3,}/g, "\n\n");
  return s.trim();
}

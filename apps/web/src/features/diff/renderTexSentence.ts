/**
 * Pure-function client-side TeX sentence renderer.
 *
 * Tokenizes a LaTeX sentence string into math, citations, refs, footnotes,
 * links, formatting commands and plain text, producing HTML safe for v-html.
 *
 * Reuses KaTeX (via katex.renderToString) for math and sanitizeMathLatex for
 * cleaning math bodies. All user text is escaped; URLs are restricted to
 * http/https.
 */
import katex from "katex";
import "katex/dist/katex.min.css";
import { sanitizeMathLatex } from "../viewer/sanitizeMathLatex";
import type { TexContext } from "./texSentenceContext";

export type RenderOptions = { theme?: "dark" | "light" };

export function renderTexSentence(
  sentence: string,
  ctx: TexContext,
  _options?: RenderOptions
): { html: string; footnoteCount: number } {
  if (!sentence) return { html: "", footnoteCount: 0 };

  const state: RenderState = {
    ctx,
    fnCounter: { n: 0 },
    footnotes: [] as FootnoteEntry[],
  };
  const html = tokenize(sentence, state);
  // Sort footnotes by number so nested footnotes (pushed during outer body
  // tokenization) appear in reading order, not push order.
  const fnHtml = state.footnotes
    .slice()
    .sort((a, b) => a.n - b.n)
    .map(
      (f) =>
        `<div class="pd-tex-fn"><sup>${f.n}</sup> <span>${f.html}</span></div>`
    )
    .join("");
  return { html: html + fnHtml, footnoteCount: state.fnCounter.n };
}

// ---------------------------------------------------------------------------
// Internals
// ---------------------------------------------------------------------------

interface FootnoteEntry {
  n: number;
  html: string;
}

interface RenderState {
  ctx: TexContext;
  fnCounter: { n: number };
  footnotes: FootnoteEntry[];
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderMath(body: string, displayMode: boolean): string {
  const cleaned = sanitizeMathLatex(body);
  try {
    return katex.renderToString(cleaned, {
      displayMode,
      throwOnError: false,
      strict: "ignore",
      trust: false,
      output: "html",
    });
  } catch {
    return `<span class="pd-math-err">${escapeHtml(cleaned || body)}</span>`;
  }
}

/** Read a brace-balanced group starting at index `i` (str[i] === "{"). Returns {body, end}. */
function readBraced(s: string, i: number): { body: string; end: number } | null {
  if (s[i] !== "{") return null;
  let depth = 0;
  for (let j = i; j < s.length; j++) {
    const c = s[j];
    if (c === "\\") {
      j++; // skip escaped char
      continue;
    }
    if (c === "{") depth++;
    else if (c === "}") {
      depth--;
      if (depth === 0) {
        return { body: s.slice(i + 1, j), end: j + 1 };
      }
    }
  }
  return null; // unbalanced
}

/** Read an optional [..] group starting at index i (after optional whitespace). */
function readOptional(
  s: string,
  i: number
): { body: string; end: number } | null {
  let j = i;
  while (j < s.length && /\s/.test(s[j])) j++;
  if (s[j] !== "[") return null;
  let depth = 0;
  for (let k = j; k < s.length; k++) {
    const c = s[k];
    if (c === "\\") {
      k++;
      continue;
    }
    if (c === "[") depth++;
    else if (c === "]") {
      depth--;
      if (depth === 0) {
        return { body: s.slice(j + 1, k), end: k + 1 };
      }
    }
  }
  return null;
}

const CITE_CMDS = [
  "cite",
  "citep",
  "citet",
  "citeauthor",
  "citealt",
  "citealp",
];

const FORMAT_CMDS: Record<string, string> = {
  textbf: "strong",
  emph: "em",
  textit: "i",
  texttt: "code",
  underline: "u",
  textsf: 'span class="pd-tex-sans"',
};

function tokenize(s: string, state: RenderState): string {
  let out = "";
  let i = 0;
  let textStart = 0;

  const flushText = (end: number) => {
    if (end > textStart) {
      const chunk = s.slice(textStart, end);
      out += `<span data-pd-raw="${escapeHtml(chunk)}">${escapeHtml(chunk)}</span>`;
    }
    textStart = end;
  };

  while (i < s.length) {
    const c = s[i];

    // Display math $$...$$
    if (c === "$" && s[i + 1] === "$") {
      const end = findDelim(s, i + 2, "$$");
      if (end >= 0) {
        flushText(i);
        const body = s.slice(i + 2, end);
        const original = s.slice(i, end + 2);
        out += `<span class="pd-tex-math display" data-pd-raw="${escapeHtml(original)}">${renderMath(body, true)}</span>`;
        i = end + 2;
        textStart = i;
        continue;
      }
    }
    // Display math \[...\]
    if (c === "\\" && s[i + 1] === "[") {
      const end = findDelim(s, i + 2, "\\]");
      if (end >= 0) {
        flushText(i);
        const body = s.slice(i + 2, end);
        const original = s.slice(i, end + 2);
        out += `<span class="pd-tex-math display" data-pd-raw="${escapeHtml(original)}">${renderMath(body, true)}</span>`;
        i = end + 2;
        textStart = i;
        continue;
      }
    }
    // Inline math $...$
    if (c === "$") {
      const end = findDelim(s, i + 1, "$");
      if (end >= 0) {
        flushText(i);
        const body = s.slice(i + 1, end);
        const original = s.slice(i, end + 1);
        out += `<span class="pd-tex-math inline" data-pd-raw="${escapeHtml(original)}">${renderMath(body, false)}</span>`;
        i = end + 1;
        textStart = i;
        continue;
      }
    }
    // Inline math \(...\)
    if (c === "\\" && s[i + 1] === "(") {
      const end = findDelim(s, i + 2, "\\)");
      if (end >= 0) {
        flushText(i);
        const body = s.slice(i + 2, end);
        const original = s.slice(i, end + 2);
        out += `<span class="pd-tex-math inline" data-pd-raw="${escapeHtml(original)}">${renderMath(body, false)}</span>`;
        i = end + 2;
        textStart = i;
        continue;
      }
    }

    // Backslash commands
    if (c === "\\") {
      // \\ line break
      if (s[i + 1] === "\\" && s[i + 2] !== "\\") {
        flushText(i);
        out += "<br>";
        i += 2;
        textStart = i;
        continue;
      }
      // \par
      const parMatch = /^\\par\b/.exec(s.slice(i));
      if (parMatch) {
        flushText(i);
        out += '<br class="pd-tex-par">';
        i += parMatch[0].length;
        textStart = i;
        continue;
      }

      // Read command name
      const cmdMatch = /^\\([a-zA-Z@]+)\*?/.exec(s.slice(i));
      if (cmdMatch) {
        const cmd = cmdMatch[1];
        const cmdEnd = i + cmdMatch[0].length;

        // Citations
        if (CITE_CMDS.includes(cmd)) {
          let p = cmdEnd;
          const opt = readOptional(s, p);
          if (opt) p = opt.end;
          const arg = readBraced(s, p);
          if (arg) {
            flushText(i);
            const original = s.slice(i, arg.end);
            const keys = arg.body.split(",").map((k) => k.trim()).filter(Boolean);
            const rendered = keys
              .map((k) => ctxLookupCite(state.ctx, k))
              .join(",");
            out += `<span class="pd-tex-cite" data-pd-raw="${escapeHtml(original)}">[${rendered}]</span>`;
            i = arg.end;
            textStart = i;
            continue;
          }
        }

        // References
        if (cmd === "ref" || cmd === "eqref" || cmd === "autoref" || cmd === "pageref") {
          const arg = readBraced(s, cmdEnd);
          if (arg) {
            flushText(i);
            const original = s.slice(i, arg.end);
            const key = arg.body.trim();
            const label = state.ctx.labels[key];
            const num = label?.number ?? key;
            let rendered: string;
            if (cmd === "ref") rendered = num;
            else if (cmd === "eqref") rendered = `(${num})`;
            else if (cmd === "autoref") rendered = `§ ${num}`;
            else rendered = label?.page ?? key;
            out += `<span class="pd-tex-ref" data-pd-raw="${escapeHtml(original)}">${escapeHtml(rendered)}</span>`;
            i = arg.end;
            textStart = i;
            continue;
          }
        }

        // Footnote
        if (cmd === "footnote") {
          const arg = readBraced(s, cmdEnd);
          if (arg) {
            flushText(i);
            const original = s.slice(i, arg.end);
            state.fnCounter.n += 1;
            const n = state.fnCounter.n;
            // Use tokenize (not renderTexSentence) so nested footnotes share
            // the same counter and footnotes array via state.
            const inner = tokenize(arg.body, state);
            state.footnotes.push({ n, html: inner });
            out += `<sup class="pd-tex-fn-mark" data-pd-raw="${escapeHtml(original)}">${n}</sup>`;
            i = arg.end;
            textStart = i;
            continue;
          }
        }

        // href
        if (cmd === "href") {
          const urlArg = readBraced(s, cmdEnd);
          if (urlArg) {
            const textArg = readBraced(s, urlArg.end);
            if (textArg) {
              flushText(i);
              const original = s.slice(i, textArg.end);
              const url = urlArg.body;
              if (/^https?:\/\//i.test(url)) {
                const inner = tokenize(textArg.body, state);
                out += `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer"><span data-pd-raw="${escapeHtml(textArg.body)}">${inner}</span></a>`;
              } else {
                out += `<span class="pd-tex-unknown" data-pd-raw="${escapeHtml(original)}">${escapeHtml(original)}</span>`;
              }
              i = textArg.end;
              textStart = i;
              continue;
            }
          }
        }

        // url
        if (cmd === "url") {
          const arg = readBraced(s, cmdEnd);
          if (arg) {
            flushText(i);
            const original = s.slice(i, arg.end);
            const url = arg.body;
            if (/^https?:\/\//i.test(url)) {
              out += `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" data-pd-raw="${escapeHtml(original)}">${escapeHtml(url)}</a>`;
            } else {
              out += `<span class="pd-tex-unknown" data-pd-raw="${escapeHtml(original)}">${escapeHtml(original)}</span>`;
            }
            i = arg.end;
            textStart = i;
            continue;
          }
        }

        // Formatting
        if (cmd in FORMAT_CMDS) {
          const arg = readBraced(s, cmdEnd);
          if (arg) {
            flushText(i);
            const inner = tokenize(arg.body, state);
            const tag = FORMAT_CMDS[cmd];
            if (tag.startsWith("span")) {
              out += `<${tag}>${inner}</span>`;
            } else {
              out += `<${tag}>${inner}</${tag}>`;
            }
            i = arg.end;
            textStart = i;
            continue;
          }
        }

        // Unknown command: render \cmd as unknown span, advance past name only.
        flushText(i);
        const original = cmdMatch[0];
        out += `<span class="pd-tex-unknown" data-pd-raw="${escapeHtml(original)}">${escapeHtml(original)}</span>`;
        i = cmdEnd;
        textStart = i;
        continue;
      }

      // Lone backslash (not a command) — treat as literal
      flushText(i + 1);
      out += `<span data-pd-raw="${escapeHtml("\\")}">${escapeHtml("\\")}</span>`;
      i += 1;
      textStart = i;
      continue;
    }

    // Bare braced group {...}
    if (c === "{") {
      const br = readBraced(s, i);
      if (br) {
        flushText(i);
        const original = s.slice(i, br.end);
        const inner = tokenize(br.body, state);
        out += `<span data-pd-raw="${escapeHtml(original)}">${inner}</span>`;
        i = br.end;
        textStart = i;
        continue;
      }
    }

    // Closing brace without opener — literal
    if (c === "}") {
      flushText(i + 1);
      out += `<span data-pd-raw="${escapeHtml("}")}">${escapeHtml("}")}</span>`;
      i += 1;
      textStart = i;
      continue;
    }

    i++;
  }

  flushText(s.length);
  return out;
}

function ctxLookupCite(ctx: TexContext, key: string): string {
  return ctx.citations[key] ?? key;
}

/** Find the next occurrence of `delim` in `s` starting at `from`. Returns index or -1. */
function findDelim(s: string, from: number, delim: string): number {
  let i = from;
  while (i < s.length) {
    if (s[i] === "\\") {
      i += 2;
      continue;
    }
    if (s.startsWith(delim, i)) return i;
    i++;
  }
  return -1;
}

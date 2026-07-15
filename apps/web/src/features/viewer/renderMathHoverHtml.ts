/**
 * Pure KaTeX HTML renderer for hover previews (no Monaco import — testable).
 */
import katex from "katex";
import "katex/dist/katex.min.css";

let cssInjected = false;

export function injectMathHoverCss() {
  if (cssInjected || typeof document === "undefined") return;
  cssInjected = true;
  const style = document.createElement("style");
  style.id = "pd-latex-math-hover-css";
  style.textContent = `
    .pd-math-hover {
      padding: 0.55rem 0.75rem;
      border-radius: 6px;
      max-width: min(36rem, 80vw);
      overflow: auto;
      line-height: 1.4;
    }
    .pd-math-hover.dark {
      background: #0b0f14;
      color: #e8eef7;
      border: 1px solid #2a3544;
    }
    .pd-math-hover.light {
      background: #ffffff;
      color: #111827;
      border: 1px solid #d1d5db;
    }
    .pd-math-hover.dark .katex,
    .pd-math-hover.dark .katex * {
      color: #e8eef7 !important;
    }
    .pd-math-hover.light .katex,
    .pd-math-hover.light .katex * {
      color: #111827 !important;
    }
    .pd-math-hover .pd-math-err {
      font-family: ui-monospace, Menlo, Consolas, monospace;
      font-size: 0.78rem;
      white-space: pre-wrap;
      color: #f87171;
    }
    .pd-math-hover .pd-math-src {
      margin-top: 0.35rem;
      font-size: 0.68rem;
      opacity: 0.65;
      font-family: ui-monospace, Menlo, Consolas, monospace;
      white-space: pre-wrap;
      word-break: break-word;
      max-height: 4rem;
      overflow: auto;
    }
  `;
  document.head.appendChild(style);
}

export function currentThemeMode(): "dark" | "light" {
  if (typeof document === "undefined") return "dark";
  const d = document.documentElement.dataset.theme;
  if (d === "light") return "light";
  if (d === "dark") return "dark";
  try {
    if (window.matchMedia?.("(prefers-color-scheme: light)").matches)
      return "light";
  } catch {
    /* ignore */
  }
  return "dark";
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function renderMathHoverHtml(
  latex: string,
  display: boolean,
  theme: "dark" | "light" = currentThemeMode()
): string {
  injectMathHoverCss();
  try {
    // Prefer HTML-only (no MathML) so v-html + CSS color overrides apply cleanly
    const body = katex.renderToString(latex, {
      displayMode: display,
      throwOnError: false,
      strict: "ignore",
      trust: false,
      output: "html",
    });
    // Fail closed: if KaTeX produced nothing useful, surface latex as error
    if (!body || !body.includes("katex")) {
      return `<div class="pd-math-hover ${theme}"><div class="pd-math-err">${escapeHtml(latex)}</div></div>`;
    }
    const src = latex.length > 200 ? latex.slice(0, 200) + "…" : latex;
    return `<div class="pd-math-hover ${theme}"><div class="pd-math-body">${body}</div><div class="pd-math-src">${escapeHtml(src)}</div></div>`;
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return `<div class="pd-math-hover ${theme}"><div class="pd-math-err">${escapeHtml(msg)}</div><div class="pd-math-src">${escapeHtml(latex)}</div></div>`;
  }
}

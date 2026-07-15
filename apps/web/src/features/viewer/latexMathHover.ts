/**
 * Monaco HoverProvider: KaTeX preview for LaTeX math under cursor.
 * Theme follows document.dataset.theme (dark = black bg / light text).
 */
import * as monaco from "monaco-editor";
import { findMathAtOffset } from "./findMathAtOffset";
import {
  currentThemeMode,
  injectMathHoverCss,
  renderMathHoverHtml,
} from "./renderMathHoverHtml";

export { renderMathHoverHtml, currentThemeMode } from "./renderMathHoverHtml";

let registered = false;

/** Register once for language id `latex`. */
export function registerLatexMathHover() {
  if (registered) return;
  registered = true;
  injectMathHoverCss();

  monaco.languages.registerHoverProvider("latex", {
    provideHover(model, position) {
      try {
        const offset = model.getOffsetAt(position);
        const text = model.getValue();
        const snip = findMathAtOffset(text, offset);
        if (!snip) return null;
        const theme = currentThemeMode();
        const html = renderMathHoverHtml(snip.latex, snip.display, theme);
        const start = model.getPositionAt(snip.startOffset);
        const endPos = model.getPositionAt(snip.endOffset);
        // Hover contents as MarkdownString-like object (Monaco accepts IMarkdownString)
        const content: monaco.IMarkdownString = {
          value: html,
          supportHtml: true,
          isTrusted: true,
        };
        return {
          range: new monaco.Range(
            start.lineNumber,
            start.column,
            endPos.lineNumber,
            endPos.column
          ),
          contents: [content],
        };
      } catch {
        return null;
      }
    },
  });
}

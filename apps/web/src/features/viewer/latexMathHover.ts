/**
 * LaTeX math hover entry: inject CSS early.
 * Actual formula UI is MathHoverCard driven from MonacoDiff mouse listeners —
 * Monaco's HoverProvider sanitizes KaTeX HTML (only limited tags/attrs), so we
 * cannot rely on built-in hover contents for real math rendering.
 */
import { injectMathHoverCss } from "./renderMathHoverHtml";

export { renderMathHoverHtml, currentThemeMode } from "./renderMathHoverHtml";
export { findMathAtOffset } from "./findMathAtOffset";

let bootstrapped = false;

/** Call once when registering latex language. */
export function registerLatexMathHover() {
  if (bootstrapped) return;
  bootstrapped = true;
  injectMathHoverCss();
}

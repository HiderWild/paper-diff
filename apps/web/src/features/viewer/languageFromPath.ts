/**
 * Map research/paper paths → Monaco language ids (or custom ids we register).
 */

export type ViewerKind =
  | "monaco"
  | "markdown"
  | "table"
  | "notebook"
  | "latexlog"
  | "pdf"
  | "word"
  | "image"
  | "other";

/** Monaco language id for a path (after registerExtraLanguages). */
export function monacoLanguageFromPath(path: string): string {
  const base = path.split(/[/\\]/).pop() || path;
  const lower = base.toLowerCase();
  if (/\.(tex|ltx|sty|cls|dtx|bbx|cbx|lbx)$/i.test(lower)) return "latex";
  if (/\.(bib|bbl|bst)$/i.test(lower)) return "bibtex";
  if (/\.py$/i.test(lower)) return "python";
  if (/\.ipynb$/i.test(lower)) return "json"; // source mode for notebooks
  if (/\.r$/i.test(lower)) return "r";
  if (/\.jl$/i.test(lower)) return "julia";
  if (/\.m$/i.test(lower)) return "plaintext"; // MATLAB ambiguous
  if (/\.(md|markdown|mdown|mkd)$/i.test(lower)) return "markdown";
  if (/\.(rst)$/i.test(lower)) return "restructuredtext";
  if (/\.(json|jsonl)$/i.test(lower)) return "json";
  if (/\.(ya?ml)$/i.test(lower)) return "yaml";
  if (/\.(xml|xsl|xsd|svg)$/i.test(lower)) return "xml";
  if (/\.(html|htm)$/i.test(lower)) return "html";
  if (/\.css$/i.test(lower)) return "css";
  if (/\.(js|mjs|cjs)$/i.test(lower)) return "javascript";
  if (/\.(ts|tsx)$/i.test(lower)) return "typescript";
  if (/\.(sh|bash|zsh)$/i.test(lower)) return "shell";
  if (/\.(toml|ini|cfg|conf)$/i.test(lower)) return "ini";
  if (/\.(sql)$/i.test(lower)) return "sql";
  if (/\.(rs)$/i.test(lower)) return "rust";
  if (/\.(go)$/i.test(lower)) return "go";
  if (/\.(c|h)$/i.test(lower)) return "c";
  if (/\.(cpp|cc|cxx|hpp|hh)$/i.test(lower)) return "cpp";
  if (/\.(java)$/i.test(lower)) return "java";
  if (/\.(csv|tsv)$/i.test(lower)) return "plaintext";
  // Common TeX log names → latexlog syntax
  if (
    /\.log$/i.test(lower) ||
    /^(pdflatex|xelatex|lualatex|latexmk|bibtex|biber)/i.test(lower)
  ) {
    return "latexlog";
  }
  if (/\.(txt|out)$/i.test(lower)) return "plaintext";
  return "plaintext";
}

export function viewerKindFromPath(path: string): ViewerKind {
  const p = path.toLowerCase();
  const base = p.split(/[/\\]/).pop() || p;
  if (p.endsWith(".pdf")) return "pdf";
  if (p.endsWith(".docx") || (p.endsWith(".doc") && !p.endsWith(".docx")))
    return "word";
  if (/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(p)) return "image";
  if (/\.(md|markdown|mdown|mkd)$/i.test(p)) return "markdown";
  if (/\.(csv|tsv)$/i.test(p)) return "table";
  if (/\.ipynb$/i.test(p)) return "notebook";
  // Heuristic: *.log under paper trees almost always latex/latexmk
  if (
    /\.log$/i.test(base) ||
    /^(pdflatex|xelatex|lualatex|latexmk|bibtex|biber)/i.test(base)
  ) {
    return "latexlog";
  }
  if (
    /\.(tex|bib|cls|sty|txt|json|ya?ml|xml|py|r|html|css|js|ts|sh|toml|ini|cfg|bbl|rst|sql|jl|out)$/i.test(
      p
    ) ||
    !p.includes(".")
  ) {
    return "monaco";
  }
  return "other";
}

/**
 * Research/paper formats worth supporting (docs for product).
 * Implemented subset marked with ✓.
 */
export const RESEARCH_FORMAT_NOTES = [
  "✓ LaTeX (.tex/.sty/.cls) — syntax highlight",
  "✓ BibTeX (.bib) — syntax highlight",
  "✓ Python (.py) — syntax highlight",
  "✓ Markdown (.md) — rendered preview + source",
  "✓ CSV/TSV — table view + source",
  "✓ Jupyter (.ipynb) — cell renderer (md/code/stream/image/error) + source",
  "✓ LaTeX log (.log) — error/warning list + Monarch source",
  "✓ R / Julia / JSON / YAML / XML / shell — highlight when Monaco provides",
  "○ MATLAB / Mathematica notebooks — defer",
  "○ NIfTI / FITS / HDF5 scientific binary — not text viewers",
  "○ Origin/GraphPad proprietary — defer",
] as const;

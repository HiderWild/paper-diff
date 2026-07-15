/**
 * Lightweight text/glyph icons for research & code files (no emoji folders).
 * Display only — not a full language-pack.
 */

export type FileIconSpec = {
  /** Short label shown in a colored pill (1–4 chars) */
  label: string;
  /** CSS color for the icon foreground */
  color: string;
};

const MAP: Array<{ re: RegExp; icon: FileIconSpec }> = [
  // Documents
  { re: /\.pdf$/i, icon: { label: "PDF", color: "#e74c3c" } },
  { re: /\.docx?$/i, icon: { label: "W", color: "#2b579a" } },
  { re: /\.(pptx?|key)$/i, icon: { label: "P", color: "#d24726" } },
  { re: /\.(xlsx?|xls)$/i, icon: { label: "X", color: "#1d6f42" } },
  { re: /\.(tex|ltx|sty|cls|dtx)$/i, icon: { label: "TEX", color: "#008080" } },
  { re: /\.(bib|bbl|bst)$/i, icon: { label: "BIB", color: "#6b5b95" } },
  { re: /\.(md|markdown|rst|txt|text)$/i, icon: { label: "MD", color: "#519aba" } },
  { re: /\.(rtf)$/i, icon: { label: "RTF", color: "#6d8086" } },

  // Data
  { re: /\.(csv|tsv)$/i, icon: { label: "CSV", color: "#89e051" } },
  { re: /\.(json|jsonl|ndjson)$/i, icon: { label: "{}", color: "#cbcb41" } },
  { re: /\.(ya?ml)$/i, icon: { label: "YML", color: "#cb171e" } },
  { re: /\.(xml|xsl|xsd)$/i, icon: { label: "XML", color: "#e37933" } },
  { re: /\.(parquet|feather|arrow|hdf5?|h5|nc|netcdf)$/i, icon: { label: "DAT", color: "#a074c4" } },
  { re: /\.(rds|rda|rdata)$/i, icon: { label: "R", color: "#198ce7" } },
  { re: /\.(sav|dta|sas7bdat)$/i, icon: { label: "STAT", color: "#4ec9b0" } },
  { re: /\.(mat)$/i, icon: { label: "MAT", color: "#e16737" } },

  // Languages / notebooks
  { re: /\.py$/i, icon: { label: "PY", color: "#3572A5" } },
  { re: /\.ipynb$/i, icon: { label: "IPY", color: "#DA5B0B" } },
  { re: /\.r$/i, icon: { label: "R", color: "#198ce7" } },
  { re: /\.jl$/i, icon: { label: "JL", color: "#a270ba" } },
  { re: /\.m$/i, icon: { label: "M", color: "#e16737" } }, // MATLAB / Obj-C ambiguous
  { re: /\.(js|mjs|cjs)$/i, icon: { label: "JS", color: "#f1e05a" } },
  { re: /\.(ts|tsx)$/i, icon: { label: "TS", color: "#3178c6" } },
  { re: /\.(jsx)$/i, icon: { label: "JSX", color: "#61dafb" } },
  { re: /\.(vue)$/i, icon: { label: "VUE", color: "#41b883" } },
  { re: /\.(java)$/i, icon: { label: "JV", color: "#b07219" } },
  { re: /\.(c|h)$/i, icon: { label: "C", color: "#555555" } },
  { re: /\.(cpp|cc|cxx|hpp|hh)$/i, icon: { label: "C++", color: "#f34b7d" } },
  { re: /\.(cs)$/i, icon: { label: "C#", color: "#178600" } },
  { re: /\.(go)$/i, icon: { label: "GO", color: "#00ADD8" } },
  { re: /\.(rs)$/i, icon: { label: "RS", color: "#dea584" } },
  { re: /\.(swift)$/i, icon: { label: "SW", color: "#F05138" } },
  { re: /\.(rb)$/i, icon: { label: "RB", color: "#701516" } },
  { re: /\.(php)$/i, icon: { label: "PHP", color: "#4F5D95" } },
  { re: /\.(sh|bash|zsh|fish)$/i, icon: { label: "SH", color: "#89e051" } },
  { re: /\.(sql)$/i, icon: { label: "SQL", color: "#e38c00" } },
  { re: /\.(scala)$/i, icon: { label: "SC", color: "#c22d40" } },
  { re: /\.(lua)$/i, icon: { label: "LUA", color: "#000080" } },
  { re: /\.(nb)$/i, icon: { label: "NB", color: "#dd1100" } }, // Mathematica

  // Images / figures
  { re: /\.(png|jpe?g|gif|webp|bmp|tiff?|ico|heic)$/i, icon: { label: "IMG", color: "#a074c4" } },
  { re: /\.(svg)$/i, icon: { label: "SVG", color: "#ffb13b" } },
  { re: /\.(eps|ps)$/i, icon: { label: "EPS", color: "#9263de" } },

  // Config / build / paper build artifacts labels
  { re: /\.(toml|ini|cfg|conf)$/i, icon: { label: "CFG", color: "#6d8086" } },
  { re: /\.(lock)$/i, icon: { label: "LCK", color: "#6d8086" } },
  { re: /^(makefile|cmakelists\.txt)$/i, icon: { label: "MK", color: "#427819" } },
  { re: /\.(dockerfile|dockerignore)$/i, icon: { label: "DKR", color: "#384d54" } },
  { re: /^\.gitignore$/i, icon: { label: "GIT", color: "#f14e32" } },

  // Archives
  { re: /\.(zip|tar|gz|tgz|bz2|7z|rar|xz)$/i, icon: { label: "ZIP", color: "#cfcfc2" } },
];

/** Generic file — avoid "·" which looked like a broken directory twisty. */
const DEFAULT_FILE: FileIconSpec = { label: "f", color: "#8b9bb4" };
const BINARY: FileIconSpec = { label: "BIN", color: "#6366f1" };

export function fileIconForPath(
  path: string,
  kind?: string
): FileIconSpec {
  const base = path.split(/[/\\]/).pop() || path;
  if (kind === "binary") {
    // still try typed binary (pdf/png) first
    for (const { re, icon } of MAP) {
      if (re.test(base) || re.test(path)) return icon;
    }
    return BINARY;
  }
  for (const { re, icon } of MAP) {
    if (re.test(base) || re.test(path)) return icon;
  }
  // extension-less names sometimes used in research
  const lower = base.toLowerCase();
  if (lower === "makefile" || lower === "dockerfile" || lower === "readme") {
    return { label: base.slice(0, 3).toUpperCase(), color: "#6d8086" };
  }
  return DEFAULT_FILE;
}

/**
 * Register extra Monaco languages not shipped with default bundles.
 * Call once before creating models.
 */
import * as monaco from "monaco-editor";

let registered = false;

export function registerExtraLanguages() {
  if (registered) return;
  registered = true;

  // --- LaTeX (minimal Monarch for papers) ---
  monaco.languages.register({ id: "latex", extensions: [".tex", ".ltx", ".sty", ".cls"] });
  monaco.languages.setMonarchTokensProvider("latex", {
    defaultToken: "",
    tokenizer: {
      root: [
        [/%.*$/, "comment"],
        [/\\\[/, { token: "string", next: "@displaymath" }],
        [/\\\(/, { token: "string", next: "@inlinemath" }],
        [/\$\$/, { token: "string", next: "@displaymathd" }],
        [/\$/, { token: "string", next: "@inlinemathd" }],
        [/\\begin\{[^}]+\}/, "keyword"],
        [/\\end\{[^}]+\}/, "keyword"],
        [/\\[a-zA-Z@]+/, "keyword"],
        [/[{}]/, "delimiter.bracket"],
        [/[[\]]/, "delimiter.square"],
        [/[0-9]+(\.[0-9]+)?/, "number"],
        [/[{}]/, "delimiter"],
      ],
      displaymath: [
        [/\\\]/, { token: "string", next: "@pop" }],
        [/[^\\]+/, "string"],
        [/./, "string"],
      ],
      displaymathd: [
        [/\$\$/, { token: "string", next: "@pop" }],
        [/[^$]+/, "string"],
        [/./, "string"],
      ],
      inlinemath: [
        [/\\\)/, { token: "string", next: "@pop" }],
        [/[^\\]+/, "string"],
        [/./, "string"],
      ],
      inlinemathd: [
        [/\$/, { token: "string", next: "@pop" }],
        [/[^$]+/, "string"],
        [/./, "string"],
      ],
    },
  });
  monaco.languages.setLanguageConfiguration("latex", {
    comments: { lineComment: "%" },
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: "$", close: "$" },
    ],
  });

  // --- BibTeX ---
  monaco.languages.register({ id: "bibtex", extensions: [".bib"] });
  monaco.languages.setMonarchTokensProvider("bibtex", {
    tokenizer: {
      root: [
        [/%.*$/, "comment"],
        [/@[a-zA-Z]+/, "keyword"],
        [/[{}]/, "delimiter.bracket"],
        [/=/, "operator"],
        [/"[^"]*"/, "string"],
        [/\{[^}]*\}/, "string"],
        [/[a-zA-Z_][\w-]*/, "attribute.name"],
      ],
    },
  });
  monaco.languages.setLanguageConfiguration("bibtex", {
    comments: { lineComment: "%" },
    brackets: [
      ["{", "}"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: '"', close: '"' },
    ],
  });

  // --- LaTeX / latexmk compile logs ---
  monaco.languages.register({ id: "latexlog", extensions: [".log"] });
  monaco.languages.setMonarchTokensProvider("latexlog", {
    tokenizer: {
      root: [
        [/^!.*$/, "invalid"],
        [/.*\bError:.*$/, "invalid"],
        [/.*Emergency stop.*$/, "invalid"],
        [/^l\.\d+.*$/, "number"],
        [/.*\bWarning:.*$/, "comment"],
        [/Overfull \\[hv]box.*$/, "comment"],
        [/Underfull \\[hv]box.*$/, "comment"],
        [/\([^()\s]+\.(?:tex|sty|cls|ltx)/, "type"],
        [/Output written on .*/, "keyword"],
        [/Transcript written on .*/, "keyword"],
      ],
    },
  });
}

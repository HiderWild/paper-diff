import { describe, expect, it } from "vitest";
import { monacoLanguageFromPath, viewerKindFromPath } from "./languageFromPath";

describe("monacoLanguageFromPath", () => {
  it("maps research types", () => {
    expect(monacoLanguageFromPath("p.tex")).toBe("latex");
    expect(monacoLanguageFromPath("r.bib")).toBe("bibtex");
    expect(monacoLanguageFromPath("a.py")).toBe("python");
    expect(monacoLanguageFromPath("README.md")).toBe("markdown");
    expect(monacoLanguageFromPath("x.r")).toBe("r");
    expect(monacoLanguageFromPath("main.log")).toBe("latexlog");
    expect(monacoLanguageFromPath("nb.ipynb")).toBe("json");
  });
});

describe("viewerKindFromPath", () => {
  it("routes md, csv, notebook, latexlog", () => {
    expect(viewerKindFromPath("a.md")).toBe("markdown");
    expect(viewerKindFromPath("a.csv")).toBe("table");
    expect(viewerKindFromPath("a.tsv")).toBe("table");
    expect(viewerKindFromPath("a.tex")).toBe("monaco");
    expect(viewerKindFromPath("a.pdf")).toBe("pdf");
    expect(viewerKindFromPath("analysis.ipynb")).toBe("notebook");
    expect(viewerKindFromPath("build/main.log")).toBe("latexlog");
  });
});

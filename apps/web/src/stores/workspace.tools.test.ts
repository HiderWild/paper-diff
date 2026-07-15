import { describe, expect, it } from "vitest";
import { fileKindForPath, toolAcceptsPath } from "./workbench";

describe("toolAcceptsPath", () => {
  it("pdf tool only accepts pdf", () => {
    expect(toolAcceptsPath("pdf", "a.pdf")).toBe(true);
    expect(toolAcceptsPath("pdf", "a.docx")).toBe(false);
    expect(toolAcceptsPath("pdf", "a.tex")).toBe(false);
  });

  it("word tool accepts doc/docx only", () => {
    expect(toolAcceptsPath("word", "x.docx")).toBe(true);
    expect(toolAcceptsPath("word", "x.doc")).toBe(true);
    expect(toolAcceptsPath("word", "x.pdf")).toBe(false);
  });

  it("comparer/editor accept text", () => {
    expect(toolAcceptsPath("comparer", "main.tex")).toBe(true);
    expect(toolAcceptsPath("editor", "notes.md")).toBe(true);
    expect(toolAcceptsPath("comparer", "fig.png")).toBe(false);
  });

  it("output rejects files", () => {
    expect(toolAcceptsPath("output", "a.tex")).toBe(false);
  });

  it("fileKindForPath", () => {
    expect(fileKindForPath("a.PDF")).toBe("pdf");
    expect(fileKindForPath("a.docx")).toBe("word");
    expect(fileKindForPath("a.png")).toBe("image");
  });
});

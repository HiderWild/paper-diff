import { describe, expect, it } from "vitest";
import {
  buildDiffUnits,
  isSentenceEndToken,
  tokenizeLatex,
} from "./sentenceMapper";

describe("tokenizeLatex", () => {
  it("keeps commands atomic", () => {
    const t = tokenizeLatex("Hello \\textbf{x} world.");
    expect(t).toContain("\\textbf");
  });

  it("keeps math atomic", () => {
    const t = tokenizeLatex("see $a+b$ end.");
    expect(t.some((x) => x.startsWith("$"))).toBe(true);
  });
});

describe("isSentenceEndToken", () => {
  it("detects Chinese and English ends", () => {
    expect(isSentenceEndToken("完。")).toBe(true);
    expect(isSentenceEndToken("done.")).toBe(true);
    expect(isSentenceEndToken("mid")).toBe(false);
  });
});

describe("buildDiffUnits", () => {
  it("creates hunk and word/sentence units", () => {
    const left = "Hello world. Second line.\n";
    const right = "Hello cosmos. Second line.\n";
    const units = buildDiffUnits(left, right, [
      {
        originalStartLineNumber: 1,
        originalEndLineNumber: 1,
        modifiedStartLineNumber: 1,
        modifiedEndLineNumber: 1,
      },
    ]);
    expect(units.some((u) => u.granularity === "hunk")).toBe(true);
    expect(units.some((u) => u.granularity === "word")).toBe(true);
  });
});

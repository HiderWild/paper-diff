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

  it("builds word units from charChanges", () => {
    const left = "abc def\n";
    const right = "abc xyz\n";
    const units = buildDiffUnits(left, right, [
      {
        originalStartLineNumber: 1,
        originalEndLineNumber: 1,
        modifiedStartLineNumber: 1,
        modifiedEndLineNumber: 1,
        charChanges: [
          {
            originalStartLineNumber: 1,
            originalStartColumn: 5,
            originalEndLineNumber: 1,
            originalEndColumn: 8,
            modifiedStartLineNumber: 1,
            modifiedStartColumn: 5,
            modifiedEndLineNumber: 1,
            modifiedEndColumn: 8,
          },
        ],
      },
    ]);
    const words = units.filter((u) => u.granularity === "word");
    expect(words.length).toBeGreaterThan(0);
    expect(words[0].leftText).toBe("def");
    expect(words[0].rightText).toBe("xyz");
  });

  it("aggregates Chinese sentence endings", () => {
    const left = "第一句。第二句。\n";
    const right = "第一句。改写句。\n";
    const units = buildDiffUnits(left, right, [
      {
        originalStartLineNumber: 1,
        originalEndLineNumber: 1,
        modifiedStartLineNumber: 1,
        modifiedEndLineNumber: 1,
      },
    ]);
    expect(units.some((u) => u.granularity === "sentence")).toBe(true);
  });
});

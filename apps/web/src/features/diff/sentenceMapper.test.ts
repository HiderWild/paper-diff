import { describe, expect, it } from "vitest";
import {
  buildDiffUnits,
  findSentenceContaining,
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

  it("sentence units cover full clause, not just changed tokens", () => {
    const left =
      "We introduce pointwise conformal deformations which expand area.";
    const right =
      "We study pointwise conformal deformations which expand area.";
    const units = buildDiffUnits(left, right, [
      {
        originalStartLineNumber: 1,
        originalEndLineNumber: 1,
        modifiedStartLineNumber: 1,
        modifiedEndLineNumber: 1,
      },
    ]);
    const sents = units.filter((u) => u.granularity === "sentence");
    expect(sents.length).toBeGreaterThan(0);
    // Full English sentence on both sides (not mid-clause fragments)
    expect(sents[0]!.leftText.trim()).toMatch(/^We introduce/);
    expect(sents[0]!.leftText.trim()).toMatch(/area\.$/);
    expect(sents[0]!.rightText.trim()).toMatch(/^We study/);
    expect(sents[0]!.rightText.trim()).toMatch(/area\.$/);
    // Must not look like the truncated intermediate blob from word-join only
    expect(sents[0]!.leftText.includes("introduce pointwise")).toBe(true);
  });
});

describe("findSentenceContaining", () => {
  it("expands to enclosing English sentence", () => {
    const t = "One. Two words here. Three.";
    const i = t.indexOf("words");
    const r = findSentenceContaining(t, i, i + 5);
    expect(t.slice(r.start, r.end)).toBe("Two words here.");
  });

  it("does not swallow next paragraph across blank line", () => {
    const t = "First sentence.\n\nNext paragraph continues.";
    const i = t.indexOf("First");
    const r = findSentenceContaining(t, i, i + 5);
    expect(t.slice(r.start, r.end)).toBe("First sentence.");
    expect(t.slice(r.start, r.end)).not.toContain("Next");
  });
});

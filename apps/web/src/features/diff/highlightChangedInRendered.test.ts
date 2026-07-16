import { describe, expect, it } from "vitest";
import { highlightChangedInRendered } from "./highlightChangedInRendered";

describe("highlightChangedInRendered", () => {
  it("highlights simple text match", () => {
    const out = highlightChangedInRendered("We see this", ["see"]);
    expect(out).toContain('<mark class="pd-diff-changed">see</mark>');
  });

  it("highlights inside strong", () => {
    const out = highlightChangedInRendered("We <strong>see</strong> this", ["see"]);
    expect(out).toContain("<strong>");
    expect(out).toContain('<mark class="pd-diff-changed">see</mark>');
    // mark is inside the strong, not outside
    expect(out).toContain("<strong><mark");
  });

  it("highlights multiple occurrences", () => {
    const out = highlightChangedInRendered("see and see again", ["see"]);
    const count = (out.match(/<mark/g) || []).length;
    expect(count).toBe(2);
  });

  it("highlights multiple different words", () => {
    const out = highlightChangedInRendered("introduce and study", [
      "introduce",
      "study",
    ]);
    expect(out).toContain('<mark class="pd-diff-changed">introduce</mark>');
    expect(out).toContain('<mark class="pd-diff-changed">study</mark>');
  });

  it("does not highlight inside katex", () => {
    const html =
      '<span class="katex"><span class="katex-mathml">...</span><span class="katex-html">x^2</span></span>';
    const out = highlightChangedInRendered(html, ["x"]);
    expect(out).not.toContain("<mark");
  });

  it("does not highlight inside pd-tex-math", () => {
    const html =
      '<span class="pd-tex-math inline" data-pd-raw="$x^2$"><span class="katex">x</span></span>';
    const out = highlightChangedInRendered(html, ["x"]);
    expect(out).not.toContain("<mark");
  });

  it("does not highlight inside pd-tex-cite", () => {
    const html =
      '<span class="pd-tex-cite" data-pd-raw="\\cite{a}">[7]</span>';
    const out = highlightChangedInRendered(html, ["7"]);
    expect(out).not.toContain("<mark");
  });

  it("does not highlight inside pd-tex-ref", () => {
    const html =
      '<span class="pd-tex-ref" data-pd-raw="\\ref{sec}">3</span>';
    const out = highlightChangedInRendered(html, ["3"]);
    expect(out).not.toContain("<mark");
  });

  it("does not nest marks", () => {
    const out = highlightChangedInRendered(
      '<mark class="pd-diff-changed">already</mark>',
      ["already"]
    );
    const count = (out.match(/<mark/g) || []).length;
    expect(count).toBe(1);
  });

  it("empty changedTexts returns unchanged", () => {
    const out = highlightChangedInRendered("hello world", []);
    expect(out).toBe("hello world");
    expect(out).not.toContain("<mark");
  });

  it("whitespace-only changedTexts ignored", () => {
    const out = highlightChangedInRendered("hello", ["", "  "]);
    expect(out).not.toContain("<mark");
  });

  it("longer match takes priority", () => {
    const out = highlightChangedInRendered("conformal maps here", [
      "conformal maps",
      "maps",
    ]);
    expect(out).toContain('<mark class="pd-diff-changed">conformal maps</mark>');
    // no nested mark
    const count = (out.match(/<mark/g) || []).length;
    expect(count).toBe(1);
  });

  it("no match returns unchanged", () => {
    const out = highlightChangedInRendered("hello world", ["xyz"]);
    expect(out).not.toContain("<mark");
  });

  it("case sensitive match", () => {
    const out = highlightChangedInRendered("Hello hello", ["hello"]);
    const count = (out.match(/<mark/g) || []).length;
    expect(count).toBe(1);
    expect(out).toContain('<mark class="pd-diff-changed">hello</mark>');
  });

  it("CJK text match", () => {
    const out = highlightChangedInRendered("我们 研究 这个", ["研究"]);
    expect(out).toContain('<mark class="pd-diff-changed">研究</mark>');
  });

  it("highlights inside anchor text", () => {
    const out = highlightChangedInRendered(
      '<a href="http://x.com">click here</a>',
      ["here"]
    );
    expect(out).toContain("<a ");
    expect(out).toContain('<mark class="pd-diff-changed">here</mark>');
  });
});

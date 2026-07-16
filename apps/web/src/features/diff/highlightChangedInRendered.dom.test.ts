// @vitest-environment happy-dom
/**
 * DOM-path tests for highlightChangedInRendered.
 *
 * The sibling .test.ts file runs in the default node environment (no
 * DOMParser) and exercises the regex fallback. This file runs in
 * happy-dom so `DOMParser` is available and the `highlightWithDom` branch
 * is covered.
 */
import { describe, expect, it } from "vitest";
import { highlightChangedInRendered } from "./highlightChangedInRendered";

describe("highlightChangedInRendered (DOM path)", () => {
  it("confirms DOMParser is available (exercising DOM branch)", () => {
    expect(typeof DOMParser).toBe("function");
  });

  it("highlights simple text match", () => {
    const out = highlightChangedInRendered("We see this", ["see"]);
    expect(out).toContain('<mark class="pd-diff-changed">see</mark>');
  });

  it("highlights inside strong", () => {
    const out = highlightChangedInRendered(
      "We <strong>see</strong> this",
      ["see"]
    );
    expect(out).toContain("<strong>");
    expect(out).toContain('<mark class="pd-diff-changed">see</mark>');
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
    expect(out).toContain(
      '<mark class="pd-diff-changed">introduce</mark>'
    );
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
    expect(out).not.toContain("<mark");
  });

  it("longer match takes priority", () => {
    const out = highlightChangedInRendered("conformal maps here", [
      "conformal maps",
      "maps",
    ]);
    expect(out).toContain(
      '<mark class="pd-diff-changed">conformal maps</mark>'
    );
    const count = (out.match(/<mark/g) || []).length;
    expect(count).toBe(1);
  });

  it("case sensitive match", () => {
    const out = highlightChangedInRendered("Hello hello", ["hello"]);
    const count = (out.match(/<mark/g) || []).length;
    expect(count).toBe(1);
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

  it("preserves existing attributes and structure", () => {
    const html =
      '<span data-pd-raw="hello">hello</span> <strong>world</strong>';
    const out = highlightChangedInRendered(html, ["world"]);
    expect(out).toContain('data-pd-raw="hello"');
    expect(out).toContain("<strong>");
    expect(out).toContain('<mark class="pd-diff-changed">world</mark>');
  });

  it("handles text split across multiple text nodes in one element", () => {
    // DOMParser will parse this as: <div>ab<em>cd</em>ef</div>
    // changed text "cd" is inside <em>, "ef" is a separate text node
    const html = "<div>ab<em>cd</em>ef</div>";
    const out = highlightChangedInRendered(html, ["cd", "ef"]);
    expect(out).toContain('<mark class="pd-diff-changed">cd</mark>');
    expect(out).toContain('<mark class="pd-diff-changed">ef</mark>');
  });
});

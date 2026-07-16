import { describe, expect, it } from "vitest";
import { renderTexSentence } from "./renderTexSentence";
import { EMPTY_TEX_CONTEXT } from "./texSentenceContext";

describe("renderTexSentence", () => {
  it("renders inline math with katex class", () => {
    const { html } = renderTexSentence("see $x^2$ here", EMPTY_TEX_CONTEXT);
    expect(html).toContain("katex");
    expect(html).toContain("pd-tex-math inline");
    // x^2 is rendered by katex (superscript), not left as literal visible text
    // (it only appears in data-pd-raw)
    expect(html).toContain('data-pd-raw="$x^2$"');
  });

  it("renders display math", () => {
    const { html } = renderTexSentence("$$x^2$$", EMPTY_TEX_CONTEXT);
    expect(html).toContain("katex");
    expect(html).toContain("pd-tex-math display");
  });

  it("cite with ctx resolves to number", () => {
    const ctx = {
      compiled: true,
      citations: { lee2023: "7" },
      labels: {},
    };
    const { html } = renderTexSentence("as in \\cite{lee2023}", ctx);
    expect(html).toContain("[7]");
    // data-pd-raw legitimately stores the original; check the visible cite span
    expect(html).toContain('">[7]</span>');
  });

  it("cite missing key shows placeholder", () => {
    const { html } = renderTexSentence(
      "as in \\cite{nope}",
      EMPTY_TEX_CONTEXT
    );
    expect(html).toContain("[nope]");
  });

  it("cite multiple keys", () => {
    const ctx = { compiled: true, citations: { a: "1", b: "2" }, labels: {} };
    const { html } = renderTexSentence("\\cite{a,b}", ctx);
    expect(html).toContain("[1,2]");
  });

  it("citep and citet work", () => {
    const ctx = { compiled: true, citations: { x: "5" }, labels: {} };
    expect(renderTexSentence("\\citep{x}", ctx).html).toContain("[5]");
    expect(renderTexSentence("\\citet{x}", ctx).html).toContain("[5]");
  });

  it("cite with optional arg strips it", () => {
    const ctx = { compiled: true, citations: { k: "9" }, labels: {} };
    const { html } = renderTexSentence("\\cite[p.5]{k}", ctx);
    expect(html).toContain("[9]");
    // optional arg stripped from rendered output (only in data-pd-raw)
    expect(html).toContain('">[9]</span>');
  });

  it("ref with ctx", () => {
    const ctx = {
      compiled: true,
      citations: {},
      labels: { "sec:intro": { number: "1" } },
    };
    const { html } = renderTexSentence("\\ref{sec:intro}", ctx);
    expect(html).toContain("1");
    // key only appears in data-pd-raw, not as visible text
    expect(html).toContain('">1</span>');
  });

  it("eqref wraps in parens", () => {
    const ctx = {
      compiled: true,
      citations: {},
      labels: { "eq:x": { number: "2" } },
    };
    const { html } = renderTexSentence("\\eqref{eq:x}", ctx);
    expect(html).toContain("(2)");
  });

  it("autoref uses section placeholder", () => {
    const ctx = {
      compiled: true,
      citations: {},
      labels: { "sec:x": { number: "3" } },
    };
    const { html } = renderTexSentence("\\autoref{sec:x}", ctx);
    expect(html).toContain("§");
    expect(html).toContain("3");
  });

  it("href http renders anchor", () => {
    const { html } = renderTexSentence(
      "\\href{http://x.com}{text}",
      EMPTY_TEX_CONTEXT
    );
    expect(html).toContain('<a href="http://x.com"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain(">text<");
  });

  it("href javascript is not rendered as anchor", () => {
    const { html } = renderTexSentence(
      "\\href{javascript:alert(1)}{x}",
      EMPTY_TEX_CONTEXT
    );
    expect(html).not.toContain("<a ");
    expect(html).toContain("javascript");
    expect(html).not.toContain('href="javascript');
  });

  it("url http renders", () => {
    const { html } = renderTexSentence(
      "\\url{http://x.com}",
      EMPTY_TEX_CONTEXT
    );
    expect(html).toContain('<a href="http://x.com"');
  });

  it("url javascript not anchor", () => {
    const { html } = renderTexSentence(
      "\\url{javascript:bad}",
      EMPTY_TEX_CONTEXT
    );
    expect(html).not.toContain("<a ");
  });

  it("textbf nests emph", () => {
    const { html } = renderTexSentence(
      "\\textbf{bold \\emph{italic}}",
      EMPTY_TEX_CONTEXT
    );
    expect(html).toContain("<strong>");
    expect(html).toContain("<em>");
    expect(html).toContain("italic");
    expect(html).toContain("bold");
  });

  it("unknown command does not crash", () => {
    const { html } = renderTexSentence("\\foo{bar}", EMPTY_TEX_CONTEXT);
    expect(html).toContain("pd-tex-unknown");
    expect(html).toContain("foo");
    expect(html).toContain("bar");
  });

  it("pure CJK escapes correctly", () => {
    const { html } = renderTexSentence("你好世界", EMPTY_TEX_CONTEXT);
    expect(html).toContain("你好世界");
    expect(html).toContain("data-pd-raw");
  });

  it("data-pd-raw present on non-math text tokens", () => {
    const { html } = renderTexSentence("hello", EMPTY_TEX_CONTEXT);
    expect(html).toContain('data-pd-raw="hello"');
  });

  it("footnote renders superscript and body", () => {
    const { html, footnoteCount } = renderTexSentence(
      "see\\footnote{note text}",
      EMPTY_TEX_CONTEXT
    );
    expect(html).toContain("<sup");
    expect(html).toContain("pd-tex-fn");
    expect(html).toContain("note text");
    expect(footnoteCount).toBe(1);
  });

  it("multiple footnotes increment", () => {
    const { html, footnoteCount } = renderTexSentence(
      "a\\footnote{x}b\\footnote{y}",
      EMPTY_TEX_CONTEXT
    );
    expect(footnoteCount).toBe(2);
    expect(html).toContain("pd-tex-fn-mark");
  });

  it("nested footnotes share counter (no restart from 1)", () => {
    // Outer footnote 1 contains an inner footnote — it should be numbered 2,
    // not 1 (which would duplicate the outer). Counter is shared via state.
    const { html, footnoteCount } = renderTexSentence(
      "see\\footnote{note\\footnote{inner}}",
      EMPTY_TEX_CONTEXT
    );
    expect(footnoteCount).toBe(2);
    // Both footnote superscript marks should be present: 1 and 2
    expect(html).toContain("pd-tex-fn-mark");
    expect(html).toMatch(/>1<\/sup>/);
    expect(html).toMatch(/>2<\/sup>/);
    // The inner footnote body should appear in the footnotes section
    expect(html).toContain("inner");
    // Footnotes divs should be in numeric order (1 before 2)
    const fn1Pos = html.indexOf('<div class="pd-tex-fn"><sup>1</sup>');
    const fn2Pos = html.indexOf('<div class="pd-tex-fn"><sup>2</sup>');
    expect(fn1Pos).toBeGreaterThanOrEqual(0);
    expect(fn2Pos).toBeGreaterThanOrEqual(0);
    expect(fn1Pos).toBeLessThan(fn2Pos);
  });

  it("xss: script tag in text is escaped", () => {
    const { html } = renderTexSentence(
      "<script>alert(1)</script>",
      EMPTY_TEX_CONTEXT
    );
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });

  it("backslash backslash renders br", () => {
    const { html } = renderTexSentence("line1\\\\line2", EMPTY_TEX_CONTEXT);
    expect(html).toContain("<br");
  });

  it("empty string returns empty", () => {
    const { html, footnoteCount } = renderTexSentence(
      "",
      EMPTY_TEX_CONTEXT
    );
    expect(html).toBe("");
    expect(footnoteCount).toBe(0);
  });

  it("unmatched dollar is literal", () => {
    const { html } = renderTexSentence("price $5", EMPTY_TEX_CONTEXT);
    expect(html).not.toContain("katex");
  });

  it("par renders br", () => {
    const { html } = renderTexSentence(
      "a\\par b",
      EMPTY_TEX_CONTEXT
    );
    expect(html).toContain("<br");
  });

  it("pageref resolves to page", () => {
    const ctx = {
      compiled: true,
      citations: {},
      labels: { k: { number: "1", page: "42" } },
    };
    const { html } = renderTexSentence("\\pageref{k}", ctx);
    expect(html).toContain("42");
  });

  it("nested braces in command args", () => {
    const { html } = renderTexSentence(
      "\\textbf{a {b} c}",
      EMPTY_TEX_CONTEXT
    );
    expect(html).toContain("<strong>");
    expect(html).toContain("a");
    expect(html).toContain("b");
    expect(html).toContain("c");
  });
});

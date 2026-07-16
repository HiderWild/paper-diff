// @vitest-environment happy-dom
/**
 * Component tests for WordHoverCard sentence-render integration (Step 6).
 *
 * Mounts the real component with i18n + KaTeX in a happy-dom environment to
 * verify: toggle behavior, not-compiled banner, rendered HTML output, and
 * changed-word highlighting.
 */
import { describe, expect, it } from "vitest";
import { mount, type VueWrapper } from "@vue/test-utils";
import WordHoverCard from "./WordHoverCard.vue";
import type { WordCardModel } from "./wordHover";
import type { TexContext } from "./texSentenceContext";
import { EMPTY_TEX_CONTEXT } from "./texSentenceContext";
import i18n from "../../i18n";

// --- Fixtures ---------------------------------------------------------------

function sentenceModel(
  workText: string,
  compareText: string
): WordCardModel {
  return {
    unit: {
      id: "s1",
      granularity: "sentence",
      left: { start_line: 1, start_col: 0, end_line: 1, end_col: 20 },
      right: { start_line: 1, start_col: 0, end_line: 1, end_col: 18 },
      leftText: workText,
      rightText: compareText,
    },
    workText,
    compareText,
    isInsert: false,
    isDelete: false,
    kind: "sentence",
  };
}

const COMPILED_CTX: TexContext = {
  compiled: true,
  citations: { lee2023: "7" },
  labels: { "sec:intro": { number: "1" } },
};

function mountCard(
  model: WordCardModel,
  texCtx?: TexContext,
  workChangedTexts?: string[],
  compareChangedTexts?: string[]
): VueWrapper {
  return mount(WordHoverCard, {
    props: {
      model,
      x: 100,
      y: 100,
      placement: "below" as const,
      ...(texCtx !== undefined ? { texCtx } : {}),
      ...(workChangedTexts !== undefined ? { workChangedTexts } : {}),
      ...(compareChangedTexts !== undefined ? { compareChangedTexts } : {}),
    },
    global: {
      plugins: [i18n],
    },
  });
}

// --- Tests ------------------------------------------------------------------

describe("WordHoverCard sentence render", () => {
  it("shows source/render toggle for sentence replace", () => {
    const w = mountCard(
      sentenceModel("We introduce maps.", "We study maps.")
    );
    const toggles = w.findAll(".toggle-btn");
    expect(toggles).toHaveLength(2);
    expect(toggles[0].text()).toBeTruthy(); // "源码" or "Source"
    expect(toggles[1].text()).toBeTruthy(); // "渲染" or "Render"
  });

  it("defaults to render view (render toggle active)", () => {
    const w = mountCard(
      sentenceModel("We introduce maps.", "We study maps.")
    );
    const renderBtn = w.findAll(".toggle-btn")[1];
    expect(renderBtn.classes()).toContain("active");
  });

  it("shows rendered HTML in render mode (not raw code snip)", () => {
    const w = mountCard(
      sentenceModel("See $x^2$ here", "See $x^2$ there"),
      COMPILED_CTX
    );
    // Render mode uses div.snip.rendered with v-html, not <code class="snip">
    const rendered = w.find(".snip.rendered");
    expect(rendered.exists()).toBe(true);
    // KaTeX should have produced math HTML
    expect(rendered.html()).toContain("katex");
  });

  it("switches to source view on toggle click", async () => {
    const w = mountCard(
      sentenceModel("See $x^2$ here", "See $x^2$ there"),
      COMPILED_CTX
    );
    const sourceBtn = w.findAll(".toggle-btn")[0];
    await sourceBtn.trigger("click");
    expect(sourceBtn.classes()).toContain("active");
    // Source mode shows <code class="snip"> with raw text
    const codeSnip = w.find("code.snip");
    expect(codeSnip.exists()).toBe(true);
    expect(codeSnip.text()).toContain("$x^2$");
  });

  it("shows not-compiled banner when ctx.compiled is false", () => {
    const w = mountCard(
      sentenceModel("See \\cite{lee2023} here", "See \\cite{lee2023} there"),
      EMPTY_TEX_CONTEXT
    );
    const banner = w.find(".not-compiled-banner");
    expect(banner.exists()).toBe(true);
  });

  it("hides not-compiled banner when ctx.compiled is true", () => {
    const w = mountCard(
      sentenceModel("See \\cite{lee2023} here", "See \\cite{lee2023} there"),
      COMPILED_CTX
    );
    const banner = w.find(".not-compiled-banner");
    expect(banner.exists()).toBe(false);
  });

  it("resolves citation to [N] in rendered view when compiled", () => {
    const w = mountCard(
      sentenceModel("As in \\cite{lee2023}.", "As in \\cite{lee2023}."),
      COMPILED_CTX
    );
    const rendered = w.findAll(".snip.rendered");
    expect(rendered.length).toBeGreaterThanOrEqual(1);
    // The citation should be resolved to [7], not [lee2023]
    const workSide = rendered[0];
    expect(workSide.html()).toContain("[7]");
  });

  it("shows [key] placeholder in rendered view when not compiled", () => {
    const w = mountCard(
      sentenceModel("As in \\cite{lee2023}.", "As in \\cite{lee2023}."),
      EMPTY_TEX_CONTEXT
    );
    const rendered = w.findAll(".snip.rendered");
    expect(rendered.length).toBeGreaterThanOrEqual(1);
    // Should show [lee2023] placeholder, not [7]
    expect(rendered[0].html()).toContain("[lee2023]");
  });

  it("highlights changed words in rendered view", () => {
    const w = mountCard(
      sentenceModel("We introduce maps.", "We study maps."),
      COMPILED_CTX,
      ["introduce"],
      ["study"]
    );
    const rendered = w.findAll(".snip.rendered");
    // Work side should have "introduce" highlighted
    expect(rendered[0].html()).toContain(
      '<mark class="pd-diff-changed">introduce</mark>'
    );
    // Compare side should have "study" highlighted
    expect(rendered[1].html()).toContain(
      '<mark class="pd-diff-changed">study</mark>'
    );
  });

  it("does not show toggle for word-level (non-sentence) replace", () => {
    const w = mountCard({
      unit: {
        id: "w1",
        granularity: "word",
        left: { start_line: 1, start_col: 0, end_line: 1, end_col: 5 },
        right: { start_line: 1, start_col: 0, end_line: 1, end_col: 5 },
        leftText: "hello",
        rightText: "world",
      },
      workText: "hello",
      compareText: "world",
      isInsert: false,
      isDelete: false,
      kind: "word",
    });
    expect(w.find(".view-toggle").exists()).toBe(false);
  });

  it("renders formatting commands (textbf/emph) as HTML tags", () => {
    const w = mountCard(
      sentenceModel(
        "We \\textbf{introduce} \\emph{maps}.",
        "We \\textbf{study} \\emph{maps}."
      ),
      COMPILED_CTX
    );
    const rendered = w.findAll(".snip.rendered");
    // Formatting wraps inner text in span[data-pd-raw], so check for tags + content
    expect(rendered[0].html()).toContain("<strong>");
    expect(rendered[0].html()).toContain("introduce");
    expect(rendered[0].html()).toContain("</strong>");
    expect(rendered[0].html()).toContain("<em>");
    expect(rendered[0].html()).toContain("maps");
    expect(rendered[0].html()).toContain("</em>");
  });

  it("resets to render view when model changes", async () => {
    const w = mountCard(
      sentenceModel("See $x^2$ here", "See $x^2$ there"),
      COMPILED_CTX
    );
    // Switch to source
    const sourceBtn = w.findAll(".toggle-btn")[0];
    await sourceBtn.trigger("click");
    expect(sourceBtn.classes()).toContain("active");
    // Change model → should reset to render
    await w.setProps({
      model: sentenceModel("New sentence.", "New sentence too."),
    });
    const renderBtn = w.findAll(".toggle-btn")[1];
    expect(renderBtn.classes()).toContain("active");
  });
});

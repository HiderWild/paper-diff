/**
 * Highlight changed words in rendered TeX HTML by wrapping matches in <mark>.
 *
 * Skips KaTeX math subtrees and elements with class `pd-tex-math`,
 * `pd-tex-cite`, `pd-tex-ref`, `pd-tex-fn-mark`, `pd-tex-unknown`, plus text
 * already inside a `<mark>` (no nested marks).
 *
 * In the browser this uses `DOMParser` to walk text nodes. In environments
 * without `DOMParser` (e.g. pure node / vitest default), it falls back to a
 * tag-aware regex tokenizer that produces equivalent results.
 */
export function highlightChangedInRendered(
  html: string,
  changedTexts: string[]
): string {
  if (!html) return html;

  // 1. Normalize the list of changed texts.
  const texts = normalizeChanged(changedTexts);
  if (texts.length === 0) return html;

  // 2. Prefer the DOM path; fall back to a regex tokenizer when no DOM.
  if (typeof DOMParser !== "undefined") {
    return highlightWithDom(html, texts);
  }
  return highlightWithRegex(html, texts);
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

/** Classes whose subtrees must never be highlighted (rendered TeX commands). */
const SKIP_CLASSES = new Set([
  "katex",
  "pd-tex-math",
  "pd-tex-cite",
  "pd-tex-ref",
  "pd-tex-fn-mark",
  "pd-tex-unknown",
]);

/** Void HTML elements that never have children (don't push onto the stack). */
const VOID_TAGS = new Set([
  "area",
  "base",
  "br",
  "col",
  "embed",
  "hr",
  "img",
  "input",
  "link",
  "meta",
  "source",
  "track",
  "wbr",
]);

/**
 * Normalize the changed-texts list: drop empty/whitespace-only entries, dedupe,
 * and sort by length descending so longer phrases are considered first.
 */
function normalizeChanged(changedTexts: string[]): string[] {
  if (!changedTexts || changedTexts.length === 0) return [];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of changedTexts) {
    if (!raw) continue;
    if (raw.trim().length === 0) continue; // whitespace-only
    if (seen.has(raw)) continue;
    seen.add(raw);
    out.push(raw);
  }
  out.sort((a, b) => b.length - a.length);
  return out;
}

interface Range {
  start: number;
  end: number;
}

/**
 * Collect non-overlapping match ranges for `texts` within `text`.
 *
 * Longer texts are scanned first (the caller sorts descending by length) so a
 * phrase like "conformal maps" wins over the later "maps" match that overlaps
 * it. Overlapping ranges are dropped (first/longer wins).
 */
function collectRanges(text: string, texts: string[]): Range[] {
  if (!text) return [];
  const ranges: Range[] = [];
  for (const t of texts) {
    if (!t) continue;
    let idx = 0;
    while ((idx = text.indexOf(t, idx)) !== -1) {
      ranges.push({ start: idx, end: idx + t.length });
      idx += t.length; // advance past this match to avoid self-overlap
    }
  }
  if (ranges.length === 0) return [];
  // Sort by start ascending; for equal starts, longer range first.
  ranges.sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start));
  // Drop ranges that overlap an already-kept range.
  const kept: Range[] = [];
  for (const r of ranges) {
    const last = kept[kept.length - 1];
    if (last && r.start < last.end) continue;
    kept.push(r);
  }
  return kept;
}

/** Build the highlighted string for a single text segment. */
function applyRanges(text: string, ranges: Range[]): string {
  if (ranges.length === 0) return text;
  let out = "";
  let pos = 0;
  for (const r of ranges) {
    if (r.start > pos) out += text.slice(pos, r.start);
    out += `<mark class="pd-diff-changed">${text.slice(r.start, r.end)}</mark>`;
    pos = r.end;
  }
  if (pos < text.length) out += text.slice(pos);
  return out;
}

// ---------------------------------------------------------------------------
// DOM path (browser / DOMParser available)
// ---------------------------------------------------------------------------

function highlightWithDom(html: string, texts: string[]): string {
  const parser = new DOMParser();
  const doc = parser.parseFromString(
    `<div id="__pd-highlight-root">${html}</div>`,
    "text/html"
  );
  const root = doc.getElementById("__pd-highlight-root");
  if (!root) return html;

  const isSkipAncestor = (node: Node | null): boolean => {
    let n: Node | null = node;
    while (n && n !== root) {
      if (n.nodeType === 1) {
        const el = n as Element;
        const tag = el.tagName.toLowerCase();
        if (tag === "mark") return true;
        const cls = el.getAttribute("class");
        if (cls) {
          for (const c of cls.split(/\s+/)) {
            if (SKIP_CLASSES.has(c)) return true;
          }
        }
      }
      n = n.parentNode;
    }
    return false;
  };

  const textNodes: Text[] = [];
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (node) => {
      if (isSkipAncestor(node.parentNode)) return NodeFilter.FILTER_REJECT;
      return node.nodeValue && node.nodeValue.length > 0
        ? NodeFilter.FILTER_ACCEPT
        : NodeFilter.FILTER_REJECT;
    },
  });
  let cur: Node | null;
  while ((cur = walker.nextNode())) textNodes.push(cur as Text);

  for (const tn of textNodes) {
    const value = tn.nodeValue;
    if (!value) continue;
    const ranges = collectRanges(value, texts);
    if (ranges.length === 0) continue;
    const parent = tn.parentNode;
    if (!parent) continue;
    const owner = tn.ownerDocument || doc;
    const frag = owner.createDocumentFragment();
    let pos = 0;
    for (const r of ranges) {
      if (r.start > pos) frag.appendChild(owner.createTextNode(value.slice(pos, r.start)));
      const mark = owner.createElement("mark");
      mark.setAttribute("class", "pd-diff-changed");
      mark.textContent = value.slice(r.start, r.end);
      frag.appendChild(mark);
      pos = r.end;
    }
    if (pos < value.length) frag.appendChild(owner.createTextNode(value.slice(pos)));
    parent.replaceChild(frag, tn);
  }

  return root.innerHTML;
}

// ---------------------------------------------------------------------------
// Regex fallback (no DOMParser — e.g. vitest default node environment)
// ---------------------------------------------------------------------------

const TAG_RE = /<\/?([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*?\/?>/g;

function highlightWithRegex(html: string, texts: string[]): string {
  let out = "";
  let lastIndex = 0;
  // Stack of open elements with a skip flag (skip = math/cite/mark subtree).
  const stack: { tag: string; skip: boolean }[] = [];
  const inSkip = () => stack.some((e) => e.skip);

  const classOf = (tagStr: string): string => {
    const m = /class\s*=\s*"([^"]*)"/.exec(tagStr);
    return m ? m[1] : "";
  };

  let m: RegExpExecArray | null;
  while ((m = TAG_RE.exec(html)) !== null) {
    // Text before this tag.
    const segment = html.slice(lastIndex, m.index);
    if (segment) {
      out += inSkip() ? segment : applyRanges(segment, collectRanges(segment, texts));
    }
    const tagStr = m[0];
    const tagName = m[1].toLowerCase();
    const isClose = tagStr.charCodeAt(1) === 0x2f; // '/'
    const isSelfClose = tagStr.endsWith("/>");
    out += tagStr;

    if (isClose) {
      // Pop the topmost matching open tag (tolerant of minor imbalance).
      for (let i = stack.length - 1; i >= 0; i--) {
        if (stack[i].tag === tagName) {
          stack.splice(i, 1);
          break;
        }
      }
    } else if (!isSelfClose && !VOID_TAGS.has(tagName)) {
      const cls = classOf(tagStr);
      const skip =
        tagName === "mark" ||
        cls.split(/\s+/).some((c) => SKIP_CLASSES.has(c));
      stack.push({ tag: tagName, skip });
    }
    lastIndex = TAG_RE.lastIndex;
  }

  // Trailing text.
  const tail = html.slice(lastIndex);
  if (tail) out += inSkip() ? tail : applyRanges(tail, collectRanges(tail, texts));
  return out;
}

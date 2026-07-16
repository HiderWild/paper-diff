/**
 * Map Monaco-like line/char changes into hunk / word / sentence units.
 * Pure functions — unit tested without Monaco.
 */

export type LineColRange = {
  start_line: number;
  start_col: number;
  end_line: number;
  end_col: number;
};

export type DiffUnit = {
  id: string;
  granularity: "hunk" | "word" | "sentence";
  left: LineColRange;
  right: LineColRange;
  leftText: string;
  rightText: string;
  parentId?: string;
};

export type CharChange = {
  originalStartLineNumber: number;
  originalStartColumn: number;
  originalEndLineNumber: number;
  originalEndColumn: number;
  modifiedStartLineNumber: number;
  modifiedStartColumn: number;
  modifiedEndLineNumber: number;
  modifiedEndColumn: number;
};

export type LineChange = {
  originalStartLineNumber: number;
  originalEndLineNumber: number;
  modifiedStartLineNumber: number;
  modifiedEndLineNumber: number;
  charChanges?: CharChange[];
};

/** Tokenize with rough LaTeX awareness. */
export function tokenizeLatex(text: string): string[] {
  const tokens: string[] = [];
  const re =
    /\\[a-zA-Z@]+(?:\*)?|\$[^$]*\$|\\[\(\)\[\]]|[{}]|[^\s\\{}$]+|\s+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    tokens.push(m[0]);
  }
  return tokens.length ? tokens : text ? [text] : [];
}

export function isSentenceEndToken(tok: string): boolean {
  return /[。！？；.!?]$/.test(tok.trim());
}

export function offsetToLineCol(
  text: string,
  offset: number
): { line: number; col: number } {
  let line = 1;
  let col = 0;
  for (let i = 0; i < offset && i < text.length; i++) {
    if (text[i] === "\n") {
      line++;
      col = 0;
    } else {
      col++;
    }
  }
  return { line, col };
}

export function lineColToOffset(
  text: string,
  line: number,
  col: number
): number {
  const lines = text.split("\n");
  if (line < 1) return 0;
  if (line > lines.length) return text.length;
  let off = 0;
  for (let i = 0; i < line - 1; i++) {
    off += (lines[i]?.length ?? 0) + 1;
  }
  const lineLen = lines[line - 1]?.length ?? 0;
  const c = Math.max(0, Math.min(col, lineLen));
  return off + c;
}

export function sliceRange(text: string, r: LineColRange): string {
  const a = lineColToOffset(text, r.start_line, r.start_col);
  const b = lineColToOffset(text, r.end_line, r.end_col);
  return text.slice(a, b);
}

function rangeFromOffsets(
  text: string,
  start: number,
  end: number
): LineColRange {
  const s = offsetToLineCol(text, start);
  const e = offsetToLineCol(text, end);
  return {
    start_line: s.line,
    start_col: s.col,
    end_line: e.line,
    end_col: e.col,
  };
}

let idSeq = 0;
function nid(prefix: string): string {
  idSeq += 1;
  return `${prefix}-${idSeq}`;
}

export type BuildDiffUnitsOptions = {
  /** Max line-change hunks to process; undefined/null = all */
  maxHunks?: number | null;
  /** When false, only emit hunk units (skip word/sentence). Default true. */
  wordUnits?: boolean;
};

/** Build units from line changes + full left/right file text. */
export function buildDiffUnits(
  leftText: string,
  rightText: string,
  lineChanges: LineChange[],
  options?: BuildDiffUnitsOptions
): DiffUnit[] {
  idSeq = 0;
  const units: DiffUnit[] = [];
  const maxHunks =
    options?.maxHunks != null && options.maxHunks > 0
      ? options.maxHunks
      : null;
  const withWordUnits = options?.wordUnits !== false;
  const changes =
    maxHunks != null ? lineChanges.slice(0, maxHunks) : lineChanges;

  for (const lc of changes) {
    const left: LineColRange = {
      start_line: lc.originalStartLineNumber,
      start_col: 0,
      end_line: Math.max(lc.originalEndLineNumber, lc.originalStartLineNumber),
      end_col:
        lc.originalEndLineNumber >= lc.originalStartLineNumber
          ? (leftText.split("\n")[lc.originalEndLineNumber - 1]?.length ?? 0)
          : 0,
    };
    // pure insert on left: originalEnd < originalStart in Monaco convention sometimes
    if (lc.originalEndLineNumber === 0) {
      left.start_line = lc.originalStartLineNumber;
      left.end_line = lc.originalStartLineNumber;
      left.start_col = 0;
      left.end_col = 0;
    }
    const right: LineColRange = {
      start_line: lc.modifiedStartLineNumber,
      start_col: 0,
      end_line: Math.max(lc.modifiedEndLineNumber, lc.modifiedStartLineNumber),
      end_col:
        lc.modifiedEndLineNumber >= lc.modifiedStartLineNumber
          ? (rightText.split("\n")[lc.modifiedEndLineNumber - 1]?.length ?? 0)
          : 0,
    };
    if (lc.modifiedEndLineNumber === 0) {
      right.start_line = lc.modifiedStartLineNumber;
      right.end_line = lc.modifiedStartLineNumber;
      right.start_col = 0;
      right.end_col = 0;
    }

    const hunkId = nid("hunk");
    const leftSlice = safeSlice(leftText, left);
    const rightSlice = safeSlice(rightText, right);
    units.push({
      id: hunkId,
      granularity: "hunk",
      left,
      right,
      leftText: leftSlice,
      rightText: rightSlice,
    });

    if (!withWordUnits) continue;

    const charChanges = lc.charChanges ?? [];
    if (charChanges.length) {
      for (const cc of charChanges) {
        const wl: LineColRange = {
          start_line: cc.originalStartLineNumber,
          start_col: Math.max(0, cc.originalStartColumn - 1),
          end_line: cc.originalEndLineNumber,
          end_col: Math.max(0, cc.originalEndColumn - 1),
        };
        const wr: LineColRange = {
          start_line: cc.modifiedStartLineNumber,
          start_col: Math.max(0, cc.modifiedStartColumn - 1),
          end_line: cc.modifiedEndLineNumber,
          end_col: Math.max(0, cc.modifiedEndColumn - 1),
        };
        // Monaco columns are 1-based; we store 0-based
        units.push({
          id: nid("word"),
          granularity: "word",
          left: wl,
          right: wr,
          leftText: safeSlice(leftText, wl),
          rightText: safeSlice(rightText, wr),
          parentId: hunkId,
        });
      }
    } else if (leftSlice || rightSlice) {
      // Derive word-level by tokenizing both sides of hunk and simple LCS-free pair
      const wordUnits = wordsFromHunk(leftText, rightText, left, right, hunkId);
      units.push(...wordUnits);
    }

    // Full-document sentence spans covering the changed words (not just concat of diffs)
    const words = units.filter(
      (u) => u.parentId === hunkId && u.granularity === "word"
    );
    units.push(
      ...sentencesFromWords(leftText, rightText, words, hunkId)
    );
  }
  return units;
}

function safeSlice(text: string, r: LineColRange): string {
  try {
    return sliceRange(text, r);
  } catch {
    return "";
  }
}

function wordsFromHunk(
  leftText: string,
  rightText: string,
  left: LineColRange,
  right: LineColRange,
  hunkId: string
): DiffUnit[] {
  const lSlice = safeSlice(leftText, left);
  const rSlice = safeSlice(rightText, right);
  const lToks = tokenizeLatex(lSlice);
  const rToks = tokenizeLatex(rSlice);
  // If same token count, pair by index for changed tokens only
  const out: DiffUnit[] = [];
  if (lToks.join("") === rToks.join("")) return out;

  // Single word unit covering whole hunk if too divergent
  if (Math.abs(lToks.length - rToks.length) > 20) {
    out.push({
      id: nid("word"),
      granularity: "word",
      left,
      right,
      leftText: lSlice,
      rightText: rSlice,
      parentId: hunkId,
    });
    return out;
  }

  // Myers-like greedy: emit one unit per non-equal token index on shorter zip
  let lOff = lineColToOffset(leftText, left.start_line, left.start_col);
  let rOff = lineColToOffset(rightText, right.start_line, right.start_col);
  const n = Math.max(lToks.length, rToks.length);
  for (let i = 0; i < n; i++) {
    const lt = lToks[i] ?? "";
    const rt = rToks[i] ?? "";
    const lStart = lOff;
    const rStart = rOff;
    lOff += lt.length;
    rOff += rt.length;
    if (lt === rt) continue;
    out.push({
      id: nid("word"),
      granularity: "word",
      left: rangeFromOffsets(leftText, lStart, lStart + lt.length),
      right: rangeFromOffsets(rightText, rStart, rStart + rt.length),
      leftText: lt,
      rightText: rt,
      parentId: hunkId,
    });
  }
  return out;
}

/**
 * True at end of a sentence terminator that should close the sentence.
 * English `.` needs following space / end / quote; CJK ends stand alone.
 */
export function isSentenceBoundaryAfter(text: string, i: number): boolean {
  const ch = text[i];
  if (!ch) return false;
  if (/[。！？；]/.test(ch)) return true;
  if (!/[.!?]/.test(ch)) return false;
  // abbreviation-ish: single capital letter before period (U.S.)
  if (ch === "." && i > 0 && /[A-Z]/.test(text[i - 1]!) && (i < 2 || !/\w/.test(text[i - 2]!))) {
    return false;
  }
  const next = text[i + 1];
  if (next == null) return true;
  if (/[\s"'”’)\]]/.test(next)) return true;
  return false;
}

/**
 * Expand [start,end) in `text` to the enclosing sentence (full clauses).
 * Does **not** expand to whole paragraphs — stops at blank line.
 */
export function findSentenceContaining(
  text: string,
  start: number,
  end: number
): { start: number; end: number } {
  if (!text) return { start: 0, end: 0 };
  let s = Math.max(0, Math.min(start, text.length));
  let e = Math.max(s, Math.min(end, text.length));

  // Walk left to previous sentence end or blank-line / doc start
  while (s > 0) {
    const prev = text[s - 1]!;
    if (prev === "\n" && s >= 2 && text[s - 2] === "\n") break; // blank line
    if (isSentenceBoundaryAfter(text, s - 1)) break;
    s--;
  }
  // skip leading whitespace/newlines into the sentence
  while (s < e && /[ \t\r\n]/.test(text[s]!)) s++;

  // Walk right past end to next sentence boundary or blank line
  while (e < text.length) {
    if (text[e] === "\n" && e + 1 < text.length && text[e + 1] === "\n") {
      break;
    }
    if (isSentenceBoundaryAfter(text, e)) {
      e++; // include terminator
      // optional closing quotes
      while (e < text.length && /["'”’)\]»]/.test(text[e]!)) e++;
      break;
    }
    e++;
  }
  return { start: s, end: e };
}

/**
 * Build sentence units from word diffs by expanding into **full sentence
 * text** on each side (document-aware), then merging words that land in the
 * same left+right sentence span. Never emits paragraph-level units.
 */
function sentencesFromWords(
  leftText: string,
  rightText: string,
  words: DiffUnit[],
  hunkId: string
): DiffUnit[] {
  if (!words.length) return [];

  type Key = string;
  const groups = new Map<
    Key,
    {
      leftStart: number;
      leftEnd: number;
      rightStart: number;
      rightEnd: number;
    }
  >();

  for (const w of words) {
    const l0 = lineColToOffset(leftText, w.left.start_line, w.left.start_col);
    const l1 = lineColToOffset(leftText, w.left.end_line, w.left.end_col);
    const r0 = lineColToOffset(rightText, w.right.start_line, w.right.start_col);
    const r1 = lineColToOffset(rightText, w.right.end_line, w.right.end_col);

    // Empty insert/delete: still locate sentence from the non-empty side mid
    const ls = findSentenceContaining(leftText, l0, Math.max(l0, l1));
    const rs = findSentenceContaining(rightText, r0, Math.max(r0, r1));

    // Group by sentence starts so multiple word edits in one sentence merge
    const key = `${ls.start}:${rs.start}`;
    const g = groups.get(key);
    if (!g) {
      groups.set(key, {
        leftStart: ls.start,
        leftEnd: ls.end,
        rightStart: rs.start,
        rightEnd: rs.end,
      });
    } else {
      g.leftStart = Math.min(g.leftStart, ls.start);
      g.leftEnd = Math.max(g.leftEnd, ls.end);
      g.rightStart = Math.min(g.rightStart, rs.start);
      g.rightEnd = Math.max(g.rightEnd, rs.end);
    }
  }

  const sentences: DiffUnit[] = [];
  for (const g of groups.values()) {
    // Re-run containment on the union in case merge crossed a boundary oddly
    const ls = findSentenceContaining(leftText, g.leftStart, g.leftEnd);
    const rs = findSentenceContaining(rightText, g.rightStart, g.rightEnd);
    const leftSlice = leftText.slice(ls.start, ls.end);
    const rightSlice = rightText.slice(rs.start, rs.end);
    // Skip empty noise
    if (!leftSlice && !rightSlice) continue;
    // If sentence equals a single tiny word and identical on both sides, skip
    if (leftSlice === rightSlice && leftSlice.length < 2) continue;

    sentences.push({
      id: nid("sentence"),
      granularity: "sentence",
      left: rangeFromOffsets(leftText, ls.start, ls.end),
      right: rangeFromOffsets(rightText, rs.start, rs.end),
      leftText: leftSlice,
      rightText: rightSlice,
      parentId: hunkId,
    });
  }
  return sentences;
}

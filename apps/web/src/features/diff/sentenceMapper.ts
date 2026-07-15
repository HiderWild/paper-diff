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

/** Build units from line changes + full left/right file text. */
export function buildDiffUnits(
  leftText: string,
  rightText: string,
  lineChanges: LineChange[]
): DiffUnit[] {
  idSeq = 0;
  const units: DiffUnit[] = [];
  for (const lc of lineChanges) {
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

    // Sentence aggregation over word units of this hunk
    const words = units.filter(
      (u) => u.parentId === hunkId && u.granularity === "word"
    );
    units.push(...sentencesFromWords(words, hunkId));
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

function sentencesFromWords(words: DiffUnit[], hunkId: string): DiffUnit[] {
  if (!words.length) return [];
  const sentences: DiffUnit[] = [];
  let buf: DiffUnit[] = [];
  const flush = () => {
    if (!buf.length) return;
    const first = buf[0];
    const last = buf[buf.length - 1];
    sentences.push({
      id: nid("sentence"),
      granularity: "sentence",
      left: {
        start_line: first.left.start_line,
        start_col: first.left.start_col,
        end_line: last.left.end_line,
        end_col: last.left.end_col,
      },
      right: {
        start_line: first.right.start_line,
        start_col: first.right.start_col,
        end_line: last.right.end_line,
        end_col: last.right.end_col,
      },
      leftText: buf.map((w) => w.leftText).join(""),
      rightText: buf.map((w) => w.rightText).join(""),
      parentId: hunkId,
    });
    buf = [];
  };
  for (const w of words) {
    buf.push(w);
    if (
      isSentenceEndToken(w.leftText) ||
      isSentenceEndToken(w.rightText) ||
      /[。！？.!?]/.test(w.leftText + w.rightText)
    ) {
      flush();
    }
  }
  flush();
  // If only one sentence equal to single word, still keep sentence for Accept UI
  return sentences;
}

/**
 * Large-file editor window: viewport → fetch plan (pure helpers).
 * Line numbers are 1-based inclusive, matching file-slice API.
 */

export type LineInterval = { start: number; end: number };

/**
 * Clamp an inclusive [start, end] into [1, lineCount].
 * If lineCount is 0 or the clamped interval is empty, returns null.
 */
export function clampInterval(
  start: number,
  end: number,
  lineCount: number
): LineInterval | null {
  if (lineCount <= 0) return null;
  // Entirely past EOF or before file start
  if (start > lineCount || end < 1) return null;
  const s = Math.max(1, start);
  const e = Math.min(lineCount, end);
  if (e < s) return null;
  return { start: s, end: e };
}

/**
 * Merge overlapping/adjacent inclusive intervals; returns sorted disjoint list.
 */
export function mergeIntervals(intervals: LineInterval[]): LineInterval[] {
  if (!intervals.length) return [];
  const sorted = [...intervals]
    .filter((iv) => iv.end >= iv.start)
    .sort((a, b) => a.start - b.start || a.end - b.end);
  if (!sorted.length) return [];
  const out: LineInterval[] = [{ ...sorted[0]! }];
  for (let i = 1; i < sorted.length; i++) {
    const cur = sorted[i]!;
    const last = out[out.length - 1]!;
    // adjacent (touching) intervals merge: [1,2] + [3,4] → [1,4]
    if (cur.start <= last.end + 1) {
      last.end = Math.max(last.end, cur.end);
    } else {
      out.push({ ...cur });
    }
  }
  return out;
}

/**
 * Given viewport [v0, v1] (1-based inclusive) and H = v1 - v0 + 1:
 *   1. view  [v0, v1]
 *   2. after [v1+1, v1+H]
 *   3. before [v0-H, v0-1]
 * All clamped to [1, lineCount]; empty intervals dropped.
 * Ordered view → after → before (not merged — separate fetch windows).
 */
export function buildPrefetchPlan(
  v0: number,
  v1: number,
  lineCount: number
): LineInterval[] {
  if (lineCount <= 0) return [];
  const lo = Math.min(v0, v1);
  const hi = Math.max(v0, v1);
  const H = Math.max(1, hi - lo + 1);

  const view = clampInterval(lo, hi, lineCount);
  const after = clampInterval(hi + 1, hi + H, lineCount);
  const before = clampInterval(lo - H, lo - 1, lineCount);

  const ordered: LineInterval[] = [];
  if (view) ordered.push(view);
  if (after) ordered.push(after);
  if (before) ordered.push(before);
  return ordered;
}

/**
 * Lightweight CSV/TSV parser for research tables (no dependency).
 * Handles quoted fields and basic escapes.
 */

export type TableData = {
  headers: string[];
  rows: string[][];
  delimiter: "," | "\t" | ";";
  truncated: boolean;
  totalRows: number;
};

export function detectDelimiter(sample: string): "," | "\t" | ";" {
  const line = sample.split(/\r?\n/).find((l) => l.trim()) || "";
  const tabs = (line.match(/\t/g) || []).length;
  const semis = (line.match(/;/g) || []).length;
  const commas = (line.match(/,/g) || []).length;
  if (tabs >= commas && tabs >= semis && tabs > 0) return "\t";
  if (semis > commas) return ";";
  return ",";
}

/** Parse one CSV line with quotes. */
export function parseDelimitedLine(line: string, delim: string): string[] {
  const out: string[] = [];
  let cur = "";
  let i = 0;
  let inQ = false;
  while (i < line.length) {
    const ch = line[i]!;
    if (inQ) {
      if (ch === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i += 2;
          continue;
        }
        inQ = false;
        i++;
        continue;
      }
      cur += ch;
      i++;
      continue;
    }
    if (ch === '"') {
      inQ = true;
      i++;
      continue;
    }
    if (ch === delim) {
      out.push(cur);
      cur = "";
      i++;
      continue;
    }
    cur += ch;
    i++;
  }
  out.push(cur);
  return out;
}

export function parseTableText(
  text: string,
  opts?: { maxRows?: number; delimiter?: "," | "\t" | ";" }
): TableData {
  const maxRows = opts?.maxRows ?? 500;
  const delim =
    opts?.delimiter ??
    (text.includes("\t") && !opts?.delimiter
      ? detectDelimiter(text.slice(0, 4000))
      : detectDelimiter(text.slice(0, 4000)));

  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/);
  // drop trailing empty line from final newline
  while (lines.length && lines[lines.length - 1] === "") lines.pop();

  const totalRows = Math.max(0, lines.length - 1);
  if (!lines.length) {
    return {
      headers: [],
      rows: [],
      delimiter: delim,
      truncated: false,
      totalRows: 0,
    };
  }

  const headers = parseDelimitedLine(lines[0]!, delim);
  const rows: string[][] = [];
  const dataLines = lines.slice(1);
  const take = Math.min(dataLines.length, maxRows);
  for (let i = 0; i < take; i++) {
    const cells = parseDelimitedLine(dataLines[i]!, delim);
    // pad/truncate to header width for display
    while (cells.length < headers.length) cells.push("");
    rows.push(cells.slice(0, Math.max(headers.length, cells.length)));
  }

  return {
    headers,
    rows,
    delimiter: delim,
    truncated: dataLines.length > maxRows,
    totalRows,
  };
}

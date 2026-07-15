/**
 * Parse common LaTeX / latexmk log diagnostics for highlighting and issue list.
 */

export type LatexLogSeverity = "error" | "warning" | "info";

export type LatexLogIssue = {
  severity: LatexLogSeverity;
  message: string;
  /** 1-based line in the log file where the message appears */
  logLine: number;
  /** TeX source file if known */
  file?: string;
  /** 1-based line in the TeX source if known */
  sourceLine?: number;
  raw: string;
};

export type LatexLogSummary = {
  issues: LatexLogIssue[];
  errorCount: number;
  warningCount: number;
};

const ERROR_RE =
  /^(?:! |.*Error:|.*Fatal error|.*Emergency stop|l\.\d+\s)/i;
const WARNING_RE =
  /^(?:.*Warning:|LaTeX Warning:|Package .+ Warning:|Class .+ Warning:|Overfull \\[hv]box|Underfull \\[hv]box)/i;
const FILE_LINE_RE = /^l\.(\d+)\s+(.*)$/;
const FILE_STACK_RE = /^\(([^()\s]+\.(?:tex|sty|cls|ltx|bib))/i;

export function parseLatexLog(text: string): LatexLogSummary {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const issues: LatexLogIssue[] = [];
  let currentFile: string | undefined;
  let pendingError: LatexLogIssue | null = null;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]!;
    const logLine = i + 1;

    // Track last opened input file from (path.tex style markers
    const fileHits = [...line.matchAll(/\(([^()\s]+\.(?:tex|sty|cls|ltx))/gi)];
    if (fileHits.length) {
      currentFile = fileHits[fileHits.length - 1]![1];
    }
    const stackHit = line.match(FILE_STACK_RE);
    if (stackHit) currentFile = stackHit[1];

    const fl = line.match(FILE_LINE_RE);
    if (fl && pendingError) {
      pendingError.sourceLine = Number(fl[1]);
      if (!pendingError.file && currentFile) pendingError.file = currentFile;
      pendingError.message = `${pendingError.message} — l.${fl[1]} ${fl[2]}`.trim();
      pendingError = null;
      continue;
    }

    if (/^! /.test(line) || /Error:/i.test(line) || /Emergency stop/i.test(line)) {
      const issue: LatexLogIssue = {
        severity: "error",
        message: line.replace(/^! /, "").trim() || line.trim(),
        logLine,
        file: currentFile,
        raw: line,
      };
      issues.push(issue);
      pendingError = issue;
      continue;
    }

    if (WARNING_RE.test(line) && !ERROR_RE.test(line)) {
      // Extract optional "on input line N"
      const onLine = line.match(/on input line (\d+)/i);
      // Extract file from "Warning: ... (./file.tex"
      const inFile = line.match(/\(([^()]+\.(?:tex|sty|cls))\)/i);
      issues.push({
        severity: "warning",
        message: line.trim(),
        logLine,
        file: inFile?.[1] || currentFile,
        sourceLine: onLine ? Number(onLine[1]) : undefined,
        raw: line,
      });
      continue;
    }
  }

  const errorCount = issues.filter((x) => x.severity === "error").length;
  const warningCount = issues.filter((x) => x.severity === "warning").length;
  return { issues, errorCount, warningCount };
}

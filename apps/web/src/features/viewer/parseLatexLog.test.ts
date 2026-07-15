import { describe, expect, it } from "vitest";
import { parseLatexLog } from "./parseLatexLog";

const SAMPLE = `
This is pdfTeX
(./main.tex
! Undefined control sequence.
l.12 \\foobarbaz
LaTeX Warning: Reference \`fig:1' on page 1 undefined on input line 40.
Package hyperref Warning: Token not allowed (./main.tex)
Overfull \\hbox (12.0pt too wide) in paragraph at lines 10--12
`;

describe("parseLatexLog", () => {
  it("extracts errors and warnings", () => {
    const s = parseLatexLog(SAMPLE);
    expect(s.errorCount).toBeGreaterThanOrEqual(1);
    expect(s.warningCount).toBeGreaterThanOrEqual(2);
    const err = s.issues.find((i) => i.severity === "error");
    expect(err?.message).toMatch(/Undefined|control/i);
    expect(err?.sourceLine).toBe(12);
    const ref = s.issues.find((i) => /Reference/i.test(i.message));
    expect(ref?.sourceLine).toBe(40);
  });
});

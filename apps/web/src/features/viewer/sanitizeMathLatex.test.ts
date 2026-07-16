import { describe, expect, it } from "vitest";
import { sanitizeMathLatex } from "./sanitizeMathLatex";

describe("sanitizeMathLatex", () => {
  it("strips \\label{...}", () => {
    expect(sanitizeMathLatex(String.raw`E=mc^2\label{eq:einstein}`)).toBe(
      "E=mc^2"
    );
  });

  it("strips nested-ish braces in label", () => {
    expect(
      sanitizeMathLatex(String.raw`x\label{eq:a_{1}} + y`)
    ).toBe("x + y");
  });

  it("strips \\tag and \\nonumber", () => {
    expect(
      sanitizeMathLatex(String.raw`a+b\tag{1}\nonumber`)
    ).toBe("a+b");
  });

  it("strips \\eqref / \\ref", () => {
    expect(
      sanitizeMathLatex(String.raw`see \eqref{eq:1} and \ref{eq:2}`)
    ).toBe("see  and");
  });

  it("keeps real math macros", () => {
    expect(sanitizeMathLatex(String.raw`\frac{1}{2}\sum_i x_i`)).toBe(
      String.raw`\frac{1}{2}\sum_i x_i`
    );
  });
});

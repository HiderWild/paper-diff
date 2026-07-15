import { describe, expect, it } from "vitest";
import { fileIconForPath } from "./fileIcons";

describe("fileIconForPath", () => {
  it("maps common research types", () => {
    expect(fileIconForPath("paper.tex").label).toBe("TEX");
    expect(fileIconForPath("refs.bib").label).toBe("BIB");
    expect(fileIconForPath("out.pdf").label).toBe("PDF");
    expect(fileIconForPath("m.docx").label).toBe("W");
    expect(fileIconForPath("fig.png").label).toBe("IMG");
    expect(fileIconForPath("data.csv").label).toBe("CSV");
    expect(fileIconForPath("train.py").label).toBe("PY");
    expect(fileIconForPath("nb.ipynb").label).toBe("IPY");
    expect(fileIconForPath("plot.r").label).toBe("R");
  });

  it("uses basename for nested paths", () => {
    expect(fileIconForPath("src/model/train.py").label).toBe("PY");
  });
});

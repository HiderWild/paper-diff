import { describe, expect, it } from "vitest";
import { detectDelimiter, parseDelimitedLine, parseTableText } from "./parseTable";

describe("parseTable", () => {
  it("detects tab", () => {
    expect(detectDelimiter("a\tb\tc\n")).toBe("\t");
  });

  it("parses quoted commas", () => {
    expect(parseDelimitedLine('a,"b,c",d', ",")).toEqual(["a", "b,c", "d"]);
  });

  it("parses csv with header", () => {
    const t = parseTableText("name,age\nAda,36\nBob,40\n");
    expect(t.headers).toEqual(["name", "age"]);
    expect(t.rows).toEqual([
      ["Ada", "36"],
      ["Bob", "40"],
    ]);
    expect(t.truncated).toBe(false);
  });

  it("truncates rows", () => {
    const lines = ["h1,h2", ...Array.from({ length: 10 }, (_, i) => `${i},x`)];
    const t = parseTableText(lines.join("\n"), { maxRows: 3 });
    expect(t.rows).toHaveLength(3);
    expect(t.truncated).toBe(true);
    expect(t.totalRows).toBe(10);
  });
});

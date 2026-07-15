import { describe, expect, it } from "vitest";
import { parseNotebook, stripAnsi } from "./parseNotebook";

const SAMPLE = JSON.stringify({
  nbformat: 4,
  nbformat_minor: 5,
  metadata: {
    kernelspec: { language: "python", name: "python3" },
    language_info: { name: "python" },
  },
  cells: [
    {
      cell_type: "markdown",
      source: ["# Title\n", "hello"],
      metadata: {},
    },
    {
      cell_type: "code",
      execution_count: 1,
      source: "print(1)",
      outputs: [
        { output_type: "stream", name: "stdout", text: "1\n" },
        {
          output_type: "execute_result",
          data: { "text/plain": "2" },
          metadata: {},
          execution_count: 1,
        },
        {
          output_type: "display_data",
          data: { "image/png": "iVBORw0KGgo=" },
          metadata: {},
        },
        {
          output_type: "error",
          ename: "ValueError",
          evalue: "bad",
          traceback: ["\u001b[31mValueError\u001b[0m: bad"],
        },
      ],
      metadata: {},
    },
  ],
});

describe("parseNotebook", () => {
  it("parses markdown + code + outputs", () => {
    const nb = parseNotebook(SAMPLE);
    expect(nb.error).toBeUndefined();
    expect(nb.language).toBe("python");
    expect(nb.cells).toHaveLength(2);
    expect(nb.cells[0]!.kind).toBe("markdown");
    expect(nb.cells[0]!.source).toContain("# Title");
    expect(nb.cells[1]!.kind).toBe("code");
    expect(nb.cells[1]!.executionCount).toBe(1);
    expect(nb.cells[1]!.outputs[0]).toMatchObject({
      type: "stream",
      text: "1\n",
    });
    expect(nb.cells[1]!.outputs[1]).toMatchObject({
      type: "execute_result",
      text: "2",
    });
    expect(nb.cells[1]!.outputs[2]).toMatchObject({
      type: "display",
      imagePng: "iVBORw0KGgo=",
    });
    expect(nb.cells[1]!.outputs[3]).toMatchObject({
      type: "error",
      ename: "ValueError",
    });
  });

  it("handles invalid json", () => {
    const nb = parseNotebook("{not json");
    expect(nb.cells).toHaveLength(0);
    expect(nb.error).toBeTruthy();
  });

  it("stripAnsi", () => {
    expect(stripAnsi("\u001b[31mred\u001b[0m")).toBe("red");
  });
});

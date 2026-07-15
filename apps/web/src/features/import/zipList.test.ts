import { describe, expect, it } from "vitest";
import { defaultImportName } from "./zipList";

describe("defaultImportName", () => {
  it("formats 14 digits with hyphen between date and time", () => {
    const d = new Date(2026, 6, 15, 17, 38, 32); // month 0-based
    expect(defaultImportName(d)).toBe("20260715-173832");
    expect(defaultImportName(d).replace("-", "").length).toBe(14);
  });
});

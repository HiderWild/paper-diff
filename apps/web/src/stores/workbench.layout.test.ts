import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import {
  intentFromColumnGap,
  intentFromColumnPoint,
  useWorkbenchStore,
} from "./workbench";

const storeMap = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => storeMap.get(k) ?? null,
  setItem: (k: string, v: string) => {
    storeMap.set(k, v);
  },
  removeItem: (k: string) => {
    storeMap.delete(k);
  },
  clear: () => storeMap.clear(),
});

describe("drop intent heuristics", () => {
  it("edge zones become splits", () => {
    expect(intentFromColumnPoint("c1", 0.05, 0.5).type).toBe("split-left");
    expect(intentFromColumnPoint("c1", 0.95, 0.5).type).toBe("split-right");
    expect(intentFromColumnPoint("c1", 0.5, 0.05).type).toBe("split-above");
    expect(intentFromColumnPoint("c1", 0.5, 0.95).type).toBe("split-below");
    expect(intentFromColumnPoint("c1", 0.5, 0.5).type).toBe("tab-append");
  });

  it("tab bar insert", () => {
    const i = intentFromColumnPoint("c1", 0.5, 0.01, {
      inTabBar: true,
      tabIndex: 2,
    });
    expect(i).toEqual({ type: "tab-insert", columnId: "c1", index: 2 });
  });

  it("column gap: top 10% is above-pair", () => {
    expect(intentFromColumnGap("r1", 1, 0.05).type).toBe("row-above-pair");
    expect(intentFromColumnGap("r1", 1, 0.5).type).toBe("between-columns");
    expect(intentFromColumnGap("r1", 1, 0.95).type).toBe("row-below-pair");
  });
});

describe("workbench columns/tabs", () => {
  beforeEach(() => {
    storeMap.clear();
    setActivePinia(createPinia());
  });

  it("default layout may be empty (no forced comparer)", () => {
    const s = useWorkbenchStore();
    // Fresh store without forced default tools
    expect(s.allTabs.length).toBe(0);
    expect(s.rows.length).toBe(0);
  });

  it("openTool from empty workbench creates column+tab", () => {
    const s = useWorkbenchStore();
    const tab = s.openTool("comparer", "a.tex");
    expect(tab).toBeTruthy();
    expect(s.allTabs.some((t) => t.kind === "comparer")).toBe(true);
    expect(s.rows.length).toBeGreaterThanOrEqual(1);
  });

  it("closing last tab leaves empty workbench (no auto comparer)", () => {
    const s = useWorkbenchStore();
    const tab = s.openTool("editor", "x.tex")!;
    const colId = s.findColumnOfTab(tab.id)!;
    s.closeTab(tab.id);
    expect(s.columns[colId]).toBeUndefined();
    expect(s.rows.length).toBe(0);
    expect(s.allTabs.length).toBe(0);
  });

  it("applyDrop split-right creates new column in same row", () => {
    const s = useWorkbenchStore();
    const hostTab = s.openTool("comparer", null)!;
    const host = s.findColumnOfTab(hostTab.id)!;
    const tab = s.openTool("editor", null)!;
    const rowBefore = s.rows.find((r) => r.columnIds.includes(host))!;
    const n = rowBefore.columnIds.length;
    s.applyDrop(tab.id, { type: "split-right", columnId: host });
    const rowAfter = s.rows.find((r) =>
      r.columnIds.includes(s.findColumnOfTab(tab.id)!)
    )!;
    expect(rowAfter.columnIds.length).toBeGreaterThanOrEqual(n);
    expect(s.findColumnOfTab(tab.id)).not.toBe(host);
  });

  it("empty column auto-closed via prune", () => {
    const s = useWorkbenchStore();
    const t = s.openTool("pdf", null)!;
    const colId = s.findColumnOfTab(t.id)!;
    s.closeTab(t.id);
    expect(s.columns[colId]).toBeUndefined();
  });

  it("bindPath rejects wrong type", () => {
    const s = useWorkbenchStore();
    const pdf = s.openTool("pdf", null)!;
    expect(s.bindPath(pdf.id, "a.tex")).toBe(false);
    expect(s.bindPath(pdf.id, "a.pdf")).toBe(true);
  });
});

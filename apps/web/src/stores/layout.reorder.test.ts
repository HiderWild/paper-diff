import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useLayoutStore } from "./layout";

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

describe("layout pane reorder", () => {
  beforeEach(() => {
    storeMap.clear();
    setActivePinia(createPinia());
  });

  it("swapMain works both directions", () => {
    const s = useLayoutStore();
    s.mainOrder = ["files", "editor", "pdf"];

    s.swapMain("files", "pdf");
    expect([...s.mainOrder]).toEqual(["pdf", "editor", "files"]);

    s.swapMain("files", "pdf");
    expect([...s.mainOrder]).toEqual(["files", "editor", "pdf"]);

    s.swapMain("editor", "files");
    expect([...s.mainOrder]).toEqual(["editor", "files", "pdf"]);

    s.swapMain("pdf", "editor");
    expect([...s.mainOrder]).toEqual(["pdf", "files", "editor"]);
  });

  it("reorder insert-before is no-op for adjacent left-to-right", () => {
    const s = useLayoutStore();
    s.mainOrder = ["files", "editor", "pdf"];
    // documents the old bug: files → editor with place=before keeps order
    s.reorderMain("files", "editor", "before");
    expect([...s.mainOrder]).toEqual(["files", "editor", "pdf"]);
  });
});

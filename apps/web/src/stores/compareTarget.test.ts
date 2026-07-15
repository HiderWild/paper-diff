import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import {
  resolveTargetForWork,
  useCompareTargetStore,
  type ProjectMemory,
} from "./compareTarget";

describe("compareTarget memory (M1–M2)", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    const store: Record<string, string> = {};
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
      removeItem: (k: string) => {
        delete store[k];
      },
    });
  });

  it("setForProject without workPath only updates default", () => {
    const cmp = useCompareTargetStore();
    cmp.setForProject("p1", { kind: "git", ref: "abc", path: "a.tex" });
    expect(cmp.getForProject("p1")).toEqual({
      kind: "git",
      ref: "abc",
      path: "a.tex",
    });
    expect(cmp.getMemoryScope("p1", "a.tex")).toBe("project");
    expect(cmp.memory.p1.byWorkPath).toEqual({});
  });

  it("setForProject with workPath sets override + default", () => {
    const cmp = useCompareTargetStore();
    cmp.setForProject(
      "p1",
      { kind: "git", ref: "aaa", path: "a.tex" },
      "a.tex"
    );
    cmp.setForProject(
      "p1",
      { kind: "zone", zoneId: "z-b", path: "b.tex" },
      "b.tex"
    );

    expect(cmp.getForProject("p1", "a.tex")).toEqual({
      kind: "git",
      ref: "aaa",
      path: "a.tex",
    });
    expect(cmp.getForProject("p1", "b.tex")).toEqual({
      kind: "zone",
      zoneId: "z-b",
      path: "b.tex",
    });
    // latest default is b
    expect(cmp.getForProject("p1")).toEqual({
      kind: "zone",
      zoneId: "z-b",
      path: "b.tex",
    });
    expect(cmp.getMemoryScope("p1", "a.tex")).toBe("file");
    expect(cmp.getMemoryScope("p1", "b.tex")).toBe("file");
  });

  it("resolveForWork prefers byWorkPath then default with path rewrite", () => {
    const entry: ProjectMemory = {
      default: { kind: "git", ref: "deadbeef", path: "old.tex" },
      byWorkPath: {
        "a.tex": { kind: "git", ref: "aaa", path: "a.tex" },
      },
    };
    expect(resolveTargetForWork(entry, "a.tex", null)).toEqual({
      target: { kind: "git", ref: "aaa", path: "a.tex" },
      scope: "file",
    });
    // New file uses default ref but path = work path (M2)
    expect(resolveTargetForWork(entry, "c.tex", null)).toEqual({
      target: { kind: "git", ref: "deadbeef", path: "c.tex" },
      scope: "project",
    });
  });

  it("store resolveForWork matches G/W/T: file A git, file B zone", () => {
    const cmp = useCompareTargetStore();
    cmp.setForProject(
      "p1",
      { kind: "git", ref: "abc", path: "a.tex" },
      "a.tex"
    );
    cmp.setForProject(
      "p1",
      { kind: "zone", zoneId: "Z", path: "b.tex" },
      "b.tex"
    );
    expect(cmp.resolveForWork("p1", "a.tex")).toEqual({
      kind: "git",
      ref: "abc",
      path: "a.tex",
    });
    expect(cmp.resolveForWork("p1", "b.tex")).toEqual({
      kind: "zone",
      zoneId: "Z",
      path: "b.tex",
    });
    // New path C: project default (last set = zone Z) with path rewritten
    expect(cmp.resolveForWork("p1", "c.tex")).toEqual({
      kind: "zone",
      zoneId: "Z",
      path: "c.tex",
    });
  });
});

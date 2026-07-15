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

  it("resolveForWork prefers byWorkPath; default keeps its own path (no rewrite)", () => {
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
    // Opening c.tex does NOT invent compare path c.tex — keeps project default path
    expect(resolveTargetForWork(entry, "c.tex", null)).toEqual({
      target: { kind: "git", ref: "deadbeef", path: "old.tex" },
      scope: "project",
    });
  });

  it("store resolveForWork: file overrides vs project default path preserved", () => {
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
    // c.tex has no override → last project default (zone Z @ b.tex), path not rewritten
    expect(cmp.resolveForWork("p1", "c.tex")).toEqual({
      kind: "zone",
      zoneId: "Z",
      path: "b.tex",
    });
  });
});

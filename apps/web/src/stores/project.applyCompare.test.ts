import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const storeMap = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => storeMap.get(k) ?? null,
  setItem: (k: string, v: string) => storeMap.set(k, v),
  removeItem: (k: string) => storeMap.delete(k),
  clear: () => storeMap.clear(),
});

const putMock = vi.fn(
  async (_pid: string, path: string, content: string) => ({
    path,
    revision: 1,
    content,
  })
);

const putRangeMock = vi.fn(
  async (
    _pid: string,
    body: {
      path: string;
      start_line: number;
      end_line: number;
      content: string;
    }
  ) => ({
    path: body.path,
    revision: 1,
    content: body.content,
  })
);

const pairState = {
  path: "a.tex",
  encoding: "utf-8",
  base: { content: "Hello world\n", sha256: "a" },
  revised: { content: "Hello cosmos\n", sha256: "b" },
  merged: { content: "Hello world\n", sha256: "a", revision: 0 },
  left: {
    kind: "work",
    content: "Hello world\n",
    sha256: "a",
    revision: 0,
  },
  right: { kind: "zone", content: "Hello cosmos\n", sha256: "b" },
};

vi.mock("../shared/api", async () => {
  const actual = await vi.importActual<typeof import("../shared/api")>(
    "../shared/api"
  );
  return {
    ...actual,
    putWorkFile: (
      pid: string,
      path: string,
      content: string
    ) => putMock(pid, path, content),
    putWorkFileRange: (
      pid: string,
      body: {
        path: string;
        start_line: number;
        end_line: number;
        content: string;
      }
    ) => putRangeMock(pid, body),
    getFilePair: async () => ({ ...pairState }),
    acceptOps: vi.fn(async () => {
      throw new Error("acceptOps should not be called for client apply");
    }),
    acceptAll: vi.fn(async () => {
      throw new Error("acceptAll should not be called for client apply");
    }),
  };
});

describe("applyCompareUnit / doAccept client path", () => {
  beforeEach(() => {
    storeMap.clear();
    putMock.mockClear();
    putRangeMock.mockClear();
    setActivePinia(createPinia());
  });

  it("doAccept with rightTextFull puts visible right snippet into work", async () => {
    const { useProjectStore } = await import("./project");
    const p = useProjectStore();
    p.projectId = "p1";
    p.currentPath = "a.tex";
    p.pair = pairState as never;

    const unit = {
      id: "u1",
      granularity: "hunk" as const,
      left: { start_line: 1, start_col: 6, end_line: 1, end_col: 11 },
      right: { start_line: 1, start_col: 6, end_line: 1, end_col: 12 },
      leftText: "world",
      rightText: "cosmos",
    };

    const next = await p.doAccept(unit, {
      workPath: "a.tex",
      leftTextFull: "Hello world\n",
      rightTextFull: "Hello cosmos\n",
    });

    expect(next).toBe("Hello cosmos\n");
    expect(putMock).toHaveBeenCalledWith("p1", "a.tex", "Hello cosmos\n");
    expect(p.isDirty("a.tex")).toBe(false);
    expect(p.localBuffers["a.tex"]).toBe("Hello cosmos\n");
  });

  it("doAcceptAll with rightTextFull puts entire compare file", async () => {
    const { useProjectStore } = await import("./project");
    const p = useProjectStore();
    p.projectId = "p1";
    p.currentPath = "a.tex";
    p.pair = pairState as never;

    const fullRight = "FULL FROM GIT\nline2\n";
    const next = await p.doAcceptAll({
      workPath: "a.tex",
      rightTextFull: fullRight,
    });

    expect(next).toBe(fullRight);
    expect(putMock).toHaveBeenCalledWith("p1", "a.tex", fullRight);
  });

  it("needsClientApply true for git targets", async () => {
    const { useProjectStore } = await import("./project");
    const { useCompareTargetStore } = await import("./compareTarget");
    const p = useProjectStore();
    p.projectId = "p1";
    const cmp = useCompareTargetStore();
    cmp.setForProject("p1", { kind: "git", ref: "abc123", path: "a.tex" });
    expect(p.needsClientApply("a.tex")).toBe(true);
  });

  it("needsClientApply true for any explicit zone target", async () => {
    const { useProjectStore } = await import("./project");
    const { useCompareTargetStore } = await import("./compareTarget");
    const p = useProjectStore();
    p.projectId = "p1";
    const cmp = useCompareTargetStore();
    cmp.setForProject("p1", {
      kind: "zone",
      zoneId: "zone-other",
      path: "a.tex",
    });
    expect(p.needsClientApply("a.tex")).toBe(true);
  });

  it("needsClientApply false without explicit target", async () => {
    const { useProjectStore } = await import("./project");
    const p = useProjectStore();
    p.projectId = "p1";
    expect(p.needsClientApply("a.tex")).toBe(false);
  });

  it("L-tier full-line unit uses putWorkFileRange", async () => {
    const { useProjectStore } = await import("./project");
    const { TIER_M_MAX_LINES } = await import("../features/diff/largeFileTier");
    const p = useProjectStore();
    p.projectId = "p1";
    p.currentPath = "big.tex";

    // > 20k lines → L tier
    const n = TIER_M_MAX_LINES + 5;
    const leftLines = Array.from({ length: n }, (_, i) => `L${i + 1}`);
    leftLines[1] = "OLD";
    const left = leftLines.join("\n") + "\n";
    const rightLines = [...leftLines];
    rightLines[1] = "NEW";
    const right = rightLines.join("\n") + "\n";

    const unit = {
      id: "u-big",
      granularity: "hunk" as const,
      left: {
        start_line: 2,
        start_col: 0,
        end_line: 2,
        end_col: 3,
      },
      right: {
        start_line: 2,
        start_col: 0,
        end_line: 2,
        end_col: 3,
      },
      leftText: "OLD",
      rightText: "NEW",
    };

    const next = await p.applyCompareUnit(unit, {
      workPath: "big.tex",
      leftTextFull: left,
      rightTextFull: right,
    });

    expect(next).toBe(right);
    expect(putRangeMock).toHaveBeenCalledWith("p1", {
      path: "big.tex",
      start_line: 2,
      end_line: 2,
      content: "NEW",
    });
    expect(putMock).not.toHaveBeenCalled();
  });

  it("S-tier still uses full putWorkFile even for full-line unit", async () => {
    const { useProjectStore } = await import("./project");
    const p = useProjectStore();
    p.projectId = "p1";
    p.currentPath = "a.tex";

    const unit = {
      id: "u-line",
      granularity: "hunk" as const,
      left: { start_line: 1, start_col: 0, end_line: 1, end_col: 11 },
      right: { start_line: 1, start_col: 0, end_line: 1, end_col: 12 },
      leftText: "Hello world",
      rightText: "Hello cosmos",
    };

    await p.applyCompareUnit(unit, {
      workPath: "a.tex",
      leftTextFull: "Hello world\n",
      rightTextFull: "Hello cosmos\n",
    });

    expect(putMock).toHaveBeenCalled();
    expect(putRangeMock).not.toHaveBeenCalled();
  });
});

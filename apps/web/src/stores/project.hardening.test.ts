import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useProjectStore } from "./project";

vi.mock("../shared/api", async () => {
  const actual = await vi.importActual<typeof import("../shared/api")>(
    "../shared/api"
  );
  return {
    ...actual,
    createProject: vi.fn(async () => ({ id: "p1", status: "empty" })),
    importWorkZip: vi.fn(async () => ({
      id: "p1",
      status: "ready",
      active_zone_id: null,
      zones: [],
      root_file: null,
      root_recommended: "main.tex",
      root_candidates: [{ path: "main.tex" }],
    })),
    getDiffIndex: vi.fn(async () => ({
      files: [
        {
          path: "main.tex",
          status: "modified",
          kind: "text",
          compare_state: "ready",
        },
      ],
      summary: { total: 1, ready: 1, pending: 0 },
    })),
    listZones: vi.fn(async () => ({ zones: [], active_zone_id: null })),
    getFilePair: vi.fn(async () => ({
      path: "main.tex",
      encoding: "utf-8",
      base: { content: "left\n", sha256: "a" },
      revised: { content: "right\n", sha256: "b" },
      merged: { content: "left\n", sha256: "a", revision: 0 },
      left: { kind: "work", content: "left\n", sha256: "a", revision: 0 },
      right: { kind: "zone", content: "right\n", sha256: "b" },
    })),
    compareFile: vi.fn(async () => ({ queued: [], count: 0 })),
    agentAnalyze: vi.fn(async () => ({
      status: "ok",
      provider: "stub",
      summary: "ok",
      left_strengths: ["a"],
      right_strengths: ["b"],
      risks: [],
      recommendations: [],
    })),
    agentChat: vi.fn(async () => ({
      status: "ok",
      provider: "stub",
      reply: "hello back",
    })),
    agentChatStream: vi.fn(async (_id, _body, opts) => {
      opts?.onToken?.("hello ");
      opts?.onToken?.("back");
      return { status: "ok", provider: "stub", reply: "hello back" };
    }),
    getHealth: vi.fn(async () => ({
      ok: true,
      agent_provider: "off",
      model: "v2",
    })),
    listProjects: vi.fn(async () => ({ projects: [] })),
    csvPreview: vi.fn(async () => ({
      changed_rows: 1,
      changes: [{ row: 0, status: "modified", left: "1,2", right: "1,3" }],
    })),
    workFileRawUrl: (id: string, path: string) =>
      `/api/v1/projects/${id}/work/file-raw?path=${encodeURIComponent(path)}`,
    zoneFileRawUrl: (id: string, z: string, path: string) =>
      `/api/v1/projects/${id}/zones/${z}/file-raw?path=${encodeURIComponent(path)}`,
  };
});

describe("project store hardening", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("pairLeftContent prefers left key", () => {
    const s = useProjectStore();
    const left = s.pairLeftContent({
      path: "x",
      encoding: "utf-8",
      base: { content: "b", sha256: "" },
      revised: { content: "r", sha256: "" },
      merged: { content: "m", sha256: "", revision: 0 },
      left: { kind: "work", content: "L", sha256: "", revision: 0 },
      right: { kind: "zone", content: "R", sha256: "" },
    } as never);
    expect(left).toBe("L");
  });

  it("isCsvPath", () => {
    const s = useProjectStore();
    expect(s.isCsvPath("a.csv")).toBe(true);
    expect(s.isCsvPath("a.TSV")).toBe(true);
    expect(s.isCsvPath("a.tex")).toBe(false);
  });

  it("doImportWork sets project and files", async () => {
    const s = useProjectStore();
    const file = new File(["x"], "p.zip", { type: "application/zip" });
    await s.doImportWork(file);
    expect(s.projectId).toBe("p1");
    expect(s.files.length).toBeGreaterThan(0);
  });

  it("doAgentAnalyze sets result", async () => {
    const s = useProjectStore();
    s.projectId = "p1";
    s.currentPath = "main.tex";
    s.pair = {
      path: "main.tex",
      encoding: "utf-8",
      base: { content: "l", sha256: "" },
      revised: { content: "r", sha256: "" },
      merged: { content: "l", sha256: "", revision: 0 },
    };
    await s.doAgentAnalyze();
    expect(s.agentResult?.status).toBe("ok");
    expect(s.agentProvider).toBe("stub");
  });

  it("doAgentChat appends log", async () => {
    const s = useProjectStore();
    s.projectId = "p1";
    await s.doAgentChat("hi");
    expect(s.agentChatLog.length).toBeGreaterThanOrEqual(2);
    expect(s.agentChatLog.some((m) => m.role === "assistant")).toBe(true);
  });

  it("doCsvPreview fills result for csv path", async () => {
    const s = useProjectStore();
    s.projectId = "p1";
    s.currentPath = "data.csv";
    s.pair = {
      path: "data.csv",
      encoding: "utf-8",
      base: { content: "a,b\n", sha256: "" },
      revised: { content: "a,c\n", sha256: "" },
      merged: { content: "a,b\n", sha256: "", revision: 0 },
    };
    await s.doCsvPreview();
    expect(s.csvPreviewResult?.changed_rows).toBe(1);
  });

  it("refreshAgentProvider sets badge", async () => {
    const s = useProjectStore();
    await s.refreshAgentProvider();
    expect(s.agentProvider).toBe("off");
  });

  it("openFile image sets imagePreview", async () => {
    const s = useProjectStore();
    s.projectId = "p1";
    await s.openFile("fig/a.png");
    expect(s.imagePreview?.path).toBe("fig/a.png");
    expect(s.pair).toBeNull();
  });

  it("openFile pdf sets pdf file source not pair", async () => {
    const s = useProjectStore();
    s.projectId = "p1";
    await s.openFile("out/paper.pdf");
    expect(s.pdfSource).toBe("file");
    expect(s.pdfPath).toBe("out/paper.pdf");
    expect(s.pdfHref).toContain("file-raw");
    expect(s.pair).toBeNull();
  });

  it("swap sides flips pairLeft/Right content", () => {
    const s = useProjectStore();
    const p = {
      path: "x",
      encoding: "utf-8",
      base: { content: "W", sha256: "" },
      revised: { content: "Z", sha256: "" },
      merged: { content: "W", sha256: "", revision: 0 },
      left: { kind: "work", content: "W", sha256: "", revision: 0 },
      right: { kind: "zone", content: "Z", sha256: "" },
    } as never;
    expect(s.pairLeftContent(p)).toBe("W");
    expect(s.pairRightContent(p)).toBe("Z");
    s.toggleSidesSwapped();
    expect(s.pairLeftContent(p)).toBe("Z");
    expect(s.pairRightContent(p)).toBe("W");
  });
});

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
  async (_pid: string, _path: string, _content: string) => ({
    path: "a.tex",
    revision: 1,
  })
);
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
    getFilePair: async () => ({
      path: "a.tex",
      left: { content: "L", sha256: "", revision: 0 },
      right: { content: "R", sha256: "", revision: 0 },
      merged: { content: "L", sha256: "", revision: 0 },
      revised: { content: "R", sha256: "", revision: 0 },
    }),
  };
});

describe("autosave markDirty", () => {
  beforeEach(() => {
    storeMap.clear();
    putMock.mockClear();
    setActivePinia(createPinia());
    vi.useFakeTimers();
  });

  it("debounces putWorkFile when autoSave on", async () => {
    const { useSettingsStore } = await import("./settings");
    const { useProjectStore } = await import("./project");
    const settings = useSettingsStore();
    settings.autoSave = true;
    const p = useProjectStore();
    p.projectId = "p1";
    p.markDirty("a.tex", "hello");
    expect(putMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(3000);
    expect(putMock).toHaveBeenCalled();
    expect(p.isDirty("a.tex")).toBe(false);
  });

  it("does not save when autoSave off", async () => {
    const { useSettingsStore } = await import("./settings");
    const { useProjectStore } = await import("./project");
    const settings = useSettingsStore();
    settings.autoSave = false;
    const p = useProjectStore();
    p.projectId = "p1";
    p.markDirty("a.tex", "x");
    await vi.advanceTimersByTimeAsync(5000);
    expect(putMock).not.toHaveBeenCalled();
    expect(p.isDirty("a.tex")).toBe(true);
  });
});

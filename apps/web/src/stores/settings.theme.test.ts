import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { nextTick } from "vue";
import { useSettingsStore } from "./settings";

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

// Node test env: minimal document stub for theme application
const dataset: Record<string, string> = {};
const style: { colorScheme?: string } = {};
vi.stubGlobal("document", {
  documentElement: {
    dataset,
    style,
    removeAttribute(name: string) {
      if (name === "data-theme") delete dataset.theme;
    },
  },
});

describe("settings theme", () => {
  beforeEach(() => {
    storeMap.clear();
    delete dataset.theme;
    setActivePinia(createPinia());
  });

  it("setTheme updates resolved theme and document dataset", () => {
    const s = useSettingsStore();
    s.setTheme("light");
    expect(s.theme).toBe("light");
    expect(s.resolvedTheme).toBe("light");
    expect(dataset.theme).toBe("light");
    s.setTheme("dark");
    expect(dataset.theme).toBe("dark");
  });

  it("setTheme persists to localStorage via watcher", async () => {
    const s = useSettingsStore();
    s.setTheme("light");
    await nextTick();
    s.persist();
    const raw = localStorage.getItem("paper-diff-settings-v1");
    expect(raw).toBeTruthy();
    expect(raw!).toContain("light");
  });

  it("setAppLocale updates store", async () => {
    const s = useSettingsStore();
    s.setAppLocale("en");
    await nextTick();
    expect(s.locale).toBe("en");
  });
});

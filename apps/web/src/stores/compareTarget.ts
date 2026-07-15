/**
 * Per-project memory of what the comparer compares work against.
 */
import { defineStore } from "pinia";
import { ref } from "vue";

export type CompareTarget =
  | { kind: "zone"; zoneId: string; path: string }
  | { kind: "git"; ref: string; path: string };

const KEY = "paper-diff-compare-targets-v1";

type MemoryMap = Record<string, CompareTarget>;

function load(): MemoryMap {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const p = JSON.parse(raw) as MemoryMap;
    return p && typeof p === "object" ? p : {};
  } catch {
    return {};
  }
}

export function formatTargetLabel(t: CompareTarget | null): string {
  if (!t) return "";
  if (t.kind === "zone") return `zone:${t.zoneId.slice(0, 8)} · ${t.path}`;
  return `git:${t.ref.slice(0, 10)} · ${t.path}`;
}

export const useCompareTargetStore = defineStore("compareTarget", () => {
  const memory = ref<MemoryMap>(load());
  /** Session override for currently focused comparer (not always persisted until set). */
  const session = ref<CompareTarget | null>(null);

  function persist() {
    try {
      localStorage.setItem(KEY, JSON.stringify(memory.value));
    } catch {
      /* ignore */
    }
  }

  function getForProject(projectId: string | null): CompareTarget | null {
    if (!projectId) return session.value;
    return memory.value[projectId] || session.value;
  }

  function setForProject(projectId: string | null, target: CompareTarget) {
    session.value = target;
    if (!projectId) return;
    memory.value = { ...memory.value, [projectId]: target };
    persist();
  }

  function clearSession() {
    session.value = null;
  }

  return {
    memory,
    session,
    getForProject,
    setForProject,
    clearSession,
    formatTargetLabel,
  };
});

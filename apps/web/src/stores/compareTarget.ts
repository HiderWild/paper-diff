/**
 * Per-project memory of what the comparer compares work against.
 * Shape: project default + optional per-workPath overrides (M1–M2).
 */
import { defineStore } from "pinia";
import { ref } from "vue";

export type CompareTarget =
  | { kind: "zone"; zoneId: string; path: string }
  | { kind: "git"; ref: string; path: string };

export type ProjectMemory = {
  default: CompareTarget | null;
  byWorkPath: Record<string, CompareTarget>;
};

export type MemoryScope = "file" | "project" | "none";

const KEY = "paper-diff-compare-targets-v2";
/** Migrate from projectId → single target map. */
const LEGACY_KEY = "paper-diff-compare-targets-v1";

type MemoryMap = Record<string, ProjectMemory>;

function isCompareTarget(x: unknown): x is CompareTarget {
  if (!x || typeof x !== "object") return false;
  const o = x as Record<string, unknown>;
  if (o.kind === "zone" && typeof o.zoneId === "string") return true;
  if (o.kind === "git" && typeof o.ref === "string") return true;
  return false;
}

function emptyEntry(): ProjectMemory {
  return { default: null, byWorkPath: {} };
}

function normalizeEntry(raw: unknown): ProjectMemory {
  if (!raw || typeof raw !== "object") return emptyEntry();
  const o = raw as Record<string, unknown>;
  // New shape
  if ("default" in o || "byWorkPath" in o) {
    const by: Record<string, CompareTarget> = {};
    if (o.byWorkPath && typeof o.byWorkPath === "object") {
      for (const [k, v] of Object.entries(
        o.byWorkPath as Record<string, unknown>
      )) {
        if (isCompareTarget(v)) by[k] = v;
      }
    }
    return {
      default: isCompareTarget(o.default) ? o.default : null,
      byWorkPath: by,
    };
  }
  // Legacy flat target
  if (isCompareTarget(raw)) {
    return { default: raw, byWorkPath: {} };
  }
  return emptyEntry();
}

function load(): MemoryMap {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const p = JSON.parse(raw) as Record<string, unknown>;
      if (!p || typeof p !== "object") return {};
      const out: MemoryMap = {};
      for (const [id, v] of Object.entries(p)) {
        out[id] = normalizeEntry(v);
      }
      return out;
    }
    // One-time migrate from v1 flat map
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      const p = JSON.parse(legacy) as Record<string, unknown>;
      if (!p || typeof p !== "object") return {};
      const out: MemoryMap = {};
      for (const [id, v] of Object.entries(p)) {
        out[id] = normalizeEntry(v);
      }
      try {
        localStorage.setItem(KEY, JSON.stringify(out));
      } catch {
        /* ignore */
      }
      return out;
    }
    return {};
  } catch {
    return {};
  }
}

export function formatTargetLabel(t: CompareTarget | null): string {
  if (!t) return "";
  if (t.kind === "zone") return `zone:${t.zoneId.slice(0, 8)} · ${t.path}`;
  return `git:${t.ref.slice(0, 10)} · ${t.path}`;
}

/**
 * Prefer per-file override; else project default / session — **keep stored path**.
 *
 * Previously (M2) rewrote default path to workPath so "same relative path" pairs
 * auto-bound. That caused refresh ghosts: work `a.tex` + zone only has `b.tex`
 * still showed a compare label for `a.tex` while content load failed → empty pane.
 *
 * Explicit bindings only: byWorkPath[workPath], or default/session with its own path.
 * Callers that need same-path convenience must set a file override when picking.
 */
export function resolveTargetForWork(
  entry: ProjectMemory | null | undefined,
  workPath: string | undefined,
  session: CompareTarget | null
): { target: CompareTarget | null; scope: MemoryScope } {
  if (workPath && entry?.byWorkPath?.[workPath]) {
    return { target: entry.byWorkPath[workPath], scope: "file" };
  }
  const def = entry?.default ?? null;
  if (def) {
    return { target: def, scope: "project" };
  }
  if (session) {
    return { target: session, scope: "project" };
  }
  return { target: null, scope: "none" };
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

  /**
   * Raw lookup: byWorkPath[workPath] || project default || session.
   * Does not rewrite path — use resolveForWork for open-file policy.
   */
  function getForProject(
    projectId: string | null,
    workPath?: string
  ): CompareTarget | null {
    if (!projectId) {
      return session.value;
    }
    const entry = memory.value[projectId];
    if (workPath && entry?.byWorkPath?.[workPath]) {
      return entry.byWorkPath[workPath];
    }
    if (entry?.default) return entry.default;
    return session.value;
  }

  /** Open-work policy: file override, else default with path = workPath. */
  function resolveForWork(
    projectId: string | null,
    workPath: string
  ): CompareTarget | null {
    if (!projectId) {
      return resolveTargetForWork(null, workPath, session.value).target;
    }
    return resolveTargetForWork(
      memory.value[projectId],
      workPath,
      session.value
    ).target;
  }

  function getMemoryScope(
    projectId: string | null,
    workPath?: string
  ): MemoryScope {
    if (!projectId) {
      return session.value ? "project" : "none";
    }
    const entry = memory.value[projectId];
    if (workPath && entry?.byWorkPath?.[workPath]) return "file";
    if (entry?.default) return "project";
    return session.value ? "project" : "none";
  }

  /**
   * Persist target. Always updates project default.
   * When workPath is provided, also writes per-file override.
   */
  function setForProject(
    projectId: string | null,
    target: CompareTarget,
    workPath?: string
  ) {
    session.value = target;
    if (!projectId) return;
    const prev = memory.value[projectId] ?? emptyEntry();
    const next: ProjectMemory = {
      default: target,
      byWorkPath: { ...prev.byWorkPath },
    };
    if (workPath) {
      next.byWorkPath[workPath] = target;
    }
    memory.value = { ...memory.value, [projectId]: next };
    persist();
  }

  function clearSession() {
    session.value = null;
  }

  return {
    memory,
    session,
    getForProject,
    resolveForWork,
    getMemoryScope,
    setForProject,
    clearSession,
    formatTargetLabel,
  };
});

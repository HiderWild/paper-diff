import { defineStore } from "pinia";
import { computed, ref } from "vue";

export type ToolKind = "comparer" | "editor" | "pdf" | "word";

export type ViewInstance = {
  id: string;
  kind: ToolKind;
  /** Primary bound file (work-relative path), null = empty tool */
  path: string | null;
  /** For toast / title */
  title?: string;
};

const KEY = "paper-diff-workspace-views-v1";

function uid(kind: ToolKind) {
  return `${kind}-${Math.random().toString(36).slice(2, 9)}`;
}

function loadViews(): ViewInstance[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return defaultViews();
    const parsed = JSON.parse(raw) as ViewInstance[];
    if (!Array.isArray(parsed) || !parsed.length) return defaultViews();
    return parsed.filter((v) =>
      ["comparer", "editor", "pdf", "word"].includes(v.kind)
    );
  } catch {
    return defaultViews();
  }
}

function defaultViews(): ViewInstance[] {
  return [
    { id: uid("comparer"), kind: "comparer", path: null },
    { id: uid("pdf"), kind: "pdf", path: null },
  ];
}

export function fileKindForPath(path: string): "pdf" | "word" | "image" | "text" | "other" {
  const p = path.toLowerCase();
  if (p.endsWith(".pdf")) return "pdf";
  if (p.endsWith(".docx") || p.endsWith(".doc")) return "word";
  if (/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(p)) return "image";
  if (
    /\.(tex|bib|cls|sty|txt|md|csv|tsv|json|ya?ml|xml|py|r|html|css|js|ts|sh|toml|ini|cfg|bbl)$/i.test(
      p
    ) ||
    !p.includes(".")
  ) {
    return "text";
  }
  return "other";
}

/** Whether tool can host this file path. */
export function toolAcceptsPath(kind: ToolKind, path: string): boolean {
  const fk = fileKindForPath(path);
  if (kind === "pdf") return fk === "pdf";
  if (kind === "word") return fk === "word";
  if (kind === "editor") return fk === "text" || fk === "other";
  if (kind === "comparer") return fk === "text" || fk === "other";
  return false;
}

export const useWorkspaceStore = defineStore("workspace", () => {
  const views = ref<ViewInstance[]>(loadViews());
  const activeViewId = ref<string | null>(views.value[0]?.id ?? null);
  const toasts = ref<
    Array<{ id: string; message: string; level?: "info" | "warn" | "error" }>
  >([]);

  function persist() {
    try {
      localStorage.setItem(KEY, JSON.stringify(views.value));
    } catch {
      /* ignore */
    }
  }

  function toast(
    message: string,
    level: "info" | "warn" | "error" = "warn"
  ) {
    const id = uid("editor");
    toasts.value = [...toasts.value, { id, message, level }];
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id);
    }, 4200);
  }

  function dismissToast(id: string) {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }

  function focusView(id: string) {
    if (views.value.some((v) => v.id === id)) activeViewId.value = id;
  }

  function addView(kind: ToolKind, path: string | null = null, atIndex?: number) {
    const v: ViewInstance = {
      id: uid(kind),
      kind,
      path,
      title: path || undefined,
    };
    const next = [...views.value];
    if (atIndex == null || atIndex < 0 || atIndex > next.length) {
      // place after active, or at end
      const ai = next.findIndex((x) => x.id === activeViewId.value);
      next.splice(ai >= 0 ? ai + 1 : next.length, 0, v);
    } else {
      next.splice(atIndex, 0, v);
    }
    views.value = next;
    activeViewId.value = v.id;
    persist();
    return v;
  }

  function closeView(id: string) {
    const next = views.value.filter((v) => v.id !== id);
    if (!next.length) {
      // keep at least one empty comparer so workbench is not bare
      const v = addView("comparer", null);
      views.value = [v];
      activeViewId.value = v.id;
      persist();
      return;
    }
    views.value = next;
    if (activeViewId.value === id) {
      activeViewId.value = next[next.length - 1]?.id ?? null;
    }
    persist();
  }

  function moveView(fromId: string, toId: string) {
    if (fromId === toId) return;
    const next = [...views.value];
    const fi = next.findIndex((v) => v.id === fromId);
    const ti = next.findIndex((v) => v.id === toId);
    if (fi < 0 || ti < 0) return;
    const [item] = next.splice(fi, 1);
    const insertAt = next.findIndex((v) => v.id === toId);
    next.splice(insertAt < 0 ? next.length : insertAt, 0, item);
    views.value = next;
    persist();
  }

  function insertViewAt(kind: ToolKind, index: number, path: string | null = null) {
    return addView(kind, path, index);
  }

  function bindPath(viewId: string, path: string): boolean {
    const v = views.value.find((x) => x.id === viewId);
    if (!v) return false;
    if (!toolAcceptsPath(v.kind, path)) {
      toast(
        // consumer should pass localized message; this is fallback English key body
        `unsupported:${v.kind}:${path}`,
        "warn"
      );
      return false;
    }
    views.value = views.value.map((x) =>
      x.id === viewId ? { ...x, path, title: path } : x
    );
    activeViewId.value = viewId;
    persist();
    return true;
  }

  function bindPathWithMessage(
    viewId: string,
    path: string,
    failMessage: string
  ): boolean {
    const v = views.value.find((x) => x.id === viewId);
    if (!v) return false;
    if (!toolAcceptsPath(v.kind, path)) {
      toast(failMessage, "warn");
      return false;
    }
    views.value = views.value.map((x) =>
      x.id === viewId ? { ...x, path, title: path } : x
    );
    activeViewId.value = viewId;
    persist();
    return true;
  }

  const activeView = computed(
    () => views.value.find((v) => v.id === activeViewId.value) || null
  );

  return {
    views,
    activeViewId,
    activeView,
    toasts,
    toast,
    dismissToast,
    focusView,
    addView,
    closeView,
    moveView,
    insertViewAt,
    bindPath,
    bindPathWithMessage,
    toolAcceptsPath,
    fileKindForPath,
  };
});

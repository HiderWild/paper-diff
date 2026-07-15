import { defineStore } from "pinia";
import { computed, ref, watch } from "vue";

/** Bump key when shape changes so corrupt layouts reset. */
const KEY = "paper-diff-layout-v3";

export type MainPaneId = "files" | "editor" | "pdf";

export type LayoutState = {
  filesWidth: number;
  pdfWidth: number;
  bottomHeight: number;
  showFiles: boolean;
  showPdf: boolean;
  showBottom: boolean;
  showDotFiles: boolean;
  activity: "explorer" | "zones" | "git" | "compile" | "agent";
  /** Left-to-right order of main workbench panes (VS Code-style rearrange). */
  mainOrder: MainPaneId[];
};

export const DEFAULT_MAIN_ORDER: MainPaneId[] = ["files", "editor", "pdf"];

/** Recommended default: files (~260) + editor (flex) + PDF (~400) */
export const DEFAULT_LAYOUT: LayoutState = {
  filesWidth: 260,
  pdfWidth: 400,
  bottomHeight: 120,
  showFiles: true,
  showPdf: true,
  showBottom: true,
  showDotFiles: false,
  activity: "explorer",
  mainOrder: [...DEFAULT_MAIN_ORDER],
};

function normalizeOrder(raw: unknown): MainPaneId[] {
  const allowed = new Set<MainPaneId>(["files", "editor", "pdf"]);
  const list = Array.isArray(raw) ? raw : DEFAULT_MAIN_ORDER;
  const out: MainPaneId[] = [];
  for (const x of list) {
    if (allowed.has(x as MainPaneId) && !out.includes(x as MainPaneId)) {
      out.push(x as MainPaneId);
    }
  }
  for (const id of DEFAULT_MAIN_ORDER) {
    if (!out.includes(id)) out.push(id);
  }
  // editor should always remain present
  if (!out.includes("editor")) out.splice(1, 0, "editor");
  return out;
}

function load(): LayoutState {
  try {
    const raw = localStorage.getItem(KEY) || localStorage.getItem("paper-diff-layout-v2");
    if (!raw) return { ...DEFAULT_LAYOUT, mainOrder: [...DEFAULT_MAIN_ORDER] };
    const parsed = { ...DEFAULT_LAYOUT, ...JSON.parse(raw) } as LayoutState;
    parsed.filesWidth = Math.min(480, Math.max(160, Number(parsed.filesWidth) || 260));
    parsed.pdfWidth = Math.min(640, Math.max(200, Number(parsed.pdfWidth) || 400));
    parsed.bottomHeight = Math.min(320, Math.max(72, Number(parsed.bottomHeight) || 120));
    parsed.showFiles = parsed.showFiles !== false;
    parsed.showPdf = parsed.showPdf !== false;
    const acts = new Set(["explorer", "zones", "git", "compile", "agent"]);
    if (!acts.has(parsed.activity)) parsed.activity = "explorer";
    parsed.mainOrder = normalizeOrder(parsed.mainOrder);
    return parsed;
  } catch {
    return { ...DEFAULT_LAYOUT, mainOrder: [...DEFAULT_MAIN_ORDER] };
  }
}

export const useLayoutStore = defineStore("layout", () => {
  const initial = load();
  const filesWidth = ref(initial.filesWidth);
  const pdfWidth = ref(initial.pdfWidth);
  const bottomHeight = ref(initial.bottomHeight);
  const showFiles = ref(initial.showFiles);
  const showPdf = ref(initial.showPdf);
  const showBottom = ref(initial.showBottom);
  const showDotFiles = ref(initial.showDotFiles);
  const activity = ref(initial.activity);
  const mainOrder = ref<MainPaneId[]>([...initial.mainOrder]);

  /** Visible main panes in left-to-right order. */
  const visibleMainOrder = computed(() =>
    mainOrder.value.filter((id) => {
      if (id === "files") return showFiles.value;
      if (id === "pdf") return showPdf.value;
      return true;
    })
  );

  function persist() {
    const s: LayoutState = {
      filesWidth: filesWidth.value,
      pdfWidth: pdfWidth.value,
      bottomHeight: bottomHeight.value,
      showFiles: showFiles.value,
      showPdf: showPdf.value,
      showBottom: showBottom.value,
      showDotFiles: showDotFiles.value,
      activity: activity.value,
      mainOrder: [...mainOrder.value],
    };
    try {
      localStorage.setItem(KEY, JSON.stringify(s));
    } catch {
      /* ignore */
    }
  }

  watch(
    [
      filesWidth,
      pdfWidth,
      bottomHeight,
      showFiles,
      showPdf,
      showBottom,
      showDotFiles,
      activity,
      mainOrder,
    ],
    persist,
    { deep: true }
  );

  function reset() {
    const d = DEFAULT_LAYOUT;
    filesWidth.value = d.filesWidth;
    pdfWidth.value = d.pdfWidth;
    bottomHeight.value = d.bottomHeight;
    showFiles.value = d.showFiles;
    showPdf.value = d.showPdf;
    showBottom.value = d.showBottom;
    showDotFiles.value = d.showDotFiles;
    activity.value = d.activity;
    mainOrder.value = [...DEFAULT_MAIN_ORDER];
  }

  function toggleFiles() {
    showFiles.value = !showFiles.value;
  }
  function togglePdf() {
    showPdf.value = !showPdf.value;
  }
  function toggleBottom() {
    showBottom.value = !showBottom.value;
  }

  /** Move `from` pane before/after `to` (both must be main pane ids). */
  function reorderMain(from: MainPaneId, to: MainPaneId, place: "before" | "after" = "before") {
    if (from === to) return;
    const next = mainOrder.value.filter((x) => x !== from);
    let idx = next.indexOf(to);
    if (idx < 0) return;
    if (place === "after") idx += 1;
    next.splice(idx, 0, from);
    mainOrder.value = normalizeOrder(next);
  }

  function moveMainToIndex(from: MainPaneId, index: number) {
    const next = mainOrder.value.filter((x) => x !== from);
    const i = Math.max(0, Math.min(index, next.length));
    next.splice(i, 0, from);
    mainOrder.value = normalizeOrder(next);
  }

  return {
    filesWidth,
    pdfWidth,
    bottomHeight,
    showFiles,
    showPdf,
    showBottom,
    showDotFiles,
    activity,
    mainOrder,
    visibleMainOrder,
    reset,
    toggleFiles,
    togglePdf,
    toggleBottom,
    reorderMain,
    moveMainToIndex,
  };
});

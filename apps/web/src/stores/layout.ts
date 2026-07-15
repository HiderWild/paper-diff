import { defineStore } from "pinia";
import { ref, watch } from "vue";

/** Bump key when defaults change so stale corrupt layouts don't stick. */
const KEY = "paper-diff-layout-v2";

export type LayoutState = {
  filesWidth: number;
  pdfWidth: number;
  bottomHeight: number;
  showFiles: boolean;
  showPdf: boolean;
  showBottom: boolean;
  showDotFiles: boolean;
  activity: "explorer" | "zones" | "git" | "compile" | "agent";
};

/** Recommended default: files (~240) + editor (flex) + PDF (~420) */
export const DEFAULT_LAYOUT: LayoutState = {
  filesWidth: 260,
  pdfWidth: 400,
  bottomHeight: 120,
  showFiles: true,
  showPdf: true,
  showBottom: true,
  showDotFiles: false,
  activity: "explorer",
};

function load(): LayoutState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_LAYOUT };
    const parsed = { ...DEFAULT_LAYOUT, ...JSON.parse(raw) } as LayoutState;
    // Clamp widths so a bad drag never leaves only one pane
    parsed.filesWidth = Math.min(480, Math.max(160, Number(parsed.filesWidth) || 260));
    parsed.pdfWidth = Math.min(640, Math.max(200, Number(parsed.pdfWidth) || 400));
    parsed.bottomHeight = Math.min(320, Math.max(72, Number(parsed.bottomHeight) || 120));
    parsed.showFiles = parsed.showFiles !== false;
    parsed.showPdf = parsed.showPdf !== false;
    const acts = new Set(["explorer", "zones", "git", "compile", "agent"]);
    if (!acts.has(parsed.activity)) parsed.activity = "explorer";
    return parsed;
  } catch {
    return { ...DEFAULT_LAYOUT };
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
    ],
    persist
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

  return {
    filesWidth,
    pdfWidth,
    bottomHeight,
    showFiles,
    showPdf,
    showBottom,
    showDotFiles,
    activity,
    reset,
    toggleFiles,
    togglePdf,
    toggleBottom,
  };
});

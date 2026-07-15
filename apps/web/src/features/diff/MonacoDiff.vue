<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import {
  buildDiffUnits,
  type DiffUnit,
  type LineChange,
} from "./sentenceMapper";
import { gutterActionsFromUnits, type GutterAction } from "./gutterActions";
import {
  diffOptionsForTier,
  estimatePairTier,
  type FileTier,
} from "./largeFileTier";

self.MonacoEnvironment = {
  getWorker() {
    return new editorWorker();
  },
};

const props = withDefaults(
  defineProps<{
    left: string;
    right: string;
    path: string;
    editableLeft?: boolean;
    singlePane?: boolean;
    monacoTheme?: string;
    /** Show between-pane pull arrows */
    showGutterActions?: boolean;
    /** Word wrap on both sides (Alt/Option+Z) */
    wordWrap?: boolean;
    /** Override content tier; omit to derive from left+right size */
    fileTier?: FileTier;
  }>(),
  {
    editableLeft: false,
    singlePane: false,
    monacoTheme: "vs-dark",
    showGutterActions: true,
    wordWrap: false,
  }
);

const emit = defineEmits<{
  units: [DiffUnit[]];
  ready: [];
  leftChange: [content: string];
  pullUnit: [unit: DiffUnit];
}>();

const { t } = useI18n();
const host = ref<HTMLDivElement | null>(null);
const arrowLayer = ref<HTMLDivElement | null>(null);
/** Arrows always mean "pull compare → work"; sidesSwapped only flips display panes. */
const arrows = ref<
  Array<GutterAction & { top: number; left: number; title: string; glyph: string }>
>([]);

/** Diff mode (comparer); null when single-pane editor mode. */
let editor: monaco.editor.IStandaloneDiffEditor | null = null;
/** Single editor mode (editor tab) — one line-number column only. */
let codeEditor: monaco.editor.IStandaloneCodeEditor | null = null;
let original: monaco.editor.ITextModel | null = null;
let modified: monaco.editor.ITextModel | null = null;
let sub: monaco.IDisposable | null = null;
let contentSub: monaco.IDisposable | null = null;
const viewSubs: monaco.IDisposable[] = [];
let suppressEmit = false;
let lastUnits: DiffUnit[] = [];
/** Cancel pending idle unit build when content changes / unmount. */
let unitIdleHandle: number | null = null;
let unitTimeoutHandle: ReturnType<typeof setTimeout> | null = null;

const KIND_RANK = { line: 3, block: 2, hunk: 1 } as const;
/** Max vertical offset (px) for one secondary arrow when primary is already on the line. */
const SECONDARY_OFFSET_PX = 16;

const resolvedTier = computed<FileTier>(() => {
  if (props.fileTier) return props.fileTier;
  return estimatePairTier(props.left, props.right);
});

const tierOpts = computed(() => diffOptionsForTier(resolvedTier.value));

function cancelPendingUnits() {
  if (unitIdleHandle != null && typeof cancelIdleCallback === "function") {
    cancelIdleCallback(unitIdleHandle);
  }
  unitIdleHandle = null;
  if (unitTimeoutHandle != null) {
    clearTimeout(unitTimeoutHandle);
    unitTimeoutHandle = null;
  }
}

/** Schedule buildDiffUnits: immediate for S/M; idle (with timeout fallback) for L. */
function scheduleRecomputeUnits() {
  cancelPendingUnits();
  if (!editor || props.singlePane) return;
  if (resolvedTier.value === "L") {
    const run = () => {
      unitIdleHandle = null;
      unitTimeoutHandle = null;
      recomputeUnitsNow();
    };
    if (typeof requestIdleCallback === "function") {
      unitIdleHandle = requestIdleCallback(run, { timeout: 800 });
    } else {
      unitTimeoutHandle = setTimeout(run, 50);
    }
    return;
  }
  recomputeUnitsNow();
}

function recomputeUnitsNow() {
  if (!editor || props.singlePane) {
    lastUnits = [];
    emit("units", []);
    arrows.value = [];
    return;
  }
  const opts = tierOpts.value;
  const changes = (editor.getLineChanges() || []) as LineChange[];
  const units = buildDiffUnits(
    original?.getValue() ?? props.left,
    modified?.getValue() ?? props.right,
    changes,
    {
      maxHunks: opts.maxUnits,
      wordUnits: opts.wordUnits,
    }
  );
  lastUnits = units;
  emit("units", units);
  void nextTick(() => placeArrows());
}

/** Public / exposed recompute (synchronous). */
function recomputeUnits() {
  cancelPendingUnits();
  recomputeUnitsNow();
}

/**
 * Monaco Diff split rail x (relative to host/arrow-layer).
 * Midpoint between original editor's right edge and modified editor's left edge.
 */
function splitRailLeftPx(): number | null {
  if (!editor || !host.value) return null;
  const hostRect = host.value.getBoundingClientRect();
  if (hostRect.width <= 0) return null;
  const leftNode = editor.getOriginalEditor().getDomNode();
  const rightNode = editor.getModifiedEditor().getDomNode();
  if (!leftNode || !rightNode) return null;
  const leftRect = leftNode.getBoundingClientRect();
  const rightRect = rightNode.getBoundingClientRect();
  // Midpoint of the gap between panes (= Monaco's sash rail)
  const mid = (leftRect.right + rightRect.left) / 2 - hostRect.left;
  if (!Number.isFinite(mid) || mid <= 0) {
    // Fallback: original editor width relative to host
    return Math.max(0, leftRect.right - hostRect.left);
  }
  return mid;
}

function placeArrows() {
  if (!props.showGutterActions || props.singlePane || !editor || !host.value) {
    arrows.value = [];
    return;
  }
  const railLeft = splitRailLeftPx();
  if (railLeft == null) {
    arrows.value = [];
    return;
  }

  const leftEd = editor.getOriginalEditor();
  const acts = gutterActionsFromUnits(lastUnits);
  // Primary: one arrow per leftLine, prefer line > block > hunk
  const byLine = new Map<number, GutterAction>();
  for (const a of acts) {
    const prev = byLine.get(a.leftLine);
    if (!prev || KIND_RANK[a.kind] > KIND_RANK[prev.kind]) {
      byLine.set(a.leftLine, a);
    }
  }

  type Placed = GutterAction & {
    top: number;
    left: number;
    title: string;
    glyph: string;
  };
  const list: Placed[] = [];
  const hostH = host.value.clientHeight || 800;

  function glyphFor(kind: GutterAction["kind"]): string {
    return kind === "line" ? "←" : kind === "block" ? "⇐" : "⟸";
  }

  function lineTop(line: number): number {
    const top = leftEd.getTopForLineNumber(Math.max(1, line));
    return top - leftEd.getScrollTop() + 2;
  }

  for (const a of byLine.values()) {
    list.push({
      ...a,
      top: lineTop(a.leftLine),
      left: railLeft,
      glyph: glyphFor(a.kind),
      title: t(a.labelKey),
    });
  }

  // At most one secondary (block/hunk) under the primary on that line if useful
  const secondaryPlaced = new Set<number>();
  for (const a of acts) {
    if (a.kind === "line") continue;
    const primary = byLine.get(a.leftLine);
    if (!primary || primary.id === a.id) continue;
    // Only keep secondary when primary is the finer-grained "line" action
    // and secondary is a wider accept (block preferred over hunk).
    if (primary.kind !== "line") continue;
    if (secondaryPlaced.has(a.leftLine)) continue;
    // Prefer block over hunk when both lost to line
    if (a.kind === "hunk") {
      const hasBlock = acts.some(
        (x) =>
          x.leftLine === a.leftLine &&
          x.kind === "block" &&
          x.id !== primary.id
      );
      if (hasBlock) continue;
    }
    secondaryPlaced.add(a.leftLine);
    list.push({
      ...a,
      top: lineTop(a.leftLine) + SECONDARY_OFFSET_PX,
      left: railLeft,
      glyph: glyphFor(a.kind),
      title: t(a.labelKey),
    });
  }

  arrows.value = list.filter(
    (x) => x.top > -40 && x.top < hostH + 40
  );
}

function applyEditability() {
  if (codeEditor) {
    codeEditor.updateOptions({ readOnly: !props.editableLeft });
    applyWordWrap();
    return;
  }
  if (!editor) return;
  editor.updateOptions({
    readOnly: !props.editableLeft,
    originalEditable: !!props.editableLeft,
    renderSideBySide: true,
  });
  applyWordWrap();
  void nextTick(() => placeArrows());
}

function applyWordWrap() {
  const wrap: "on" | "off" = props.wordWrap ? "on" : "off";
  if (codeEditor) {
    codeEditor.updateOptions({ wordWrap: wrap });
    return;
  }
  if (!editor) return;
  const leftEd = editor.getOriginalEditor();
  const rightEd = editor.getModifiedEditor();
  leftEd.updateOptions({ wordWrap: wrap });
  rightEd.updateOptions({ wordWrap: wrap });
  void nextTick(() => placeArrows());
}

function bindViewListeners() {
  while (viewSubs.length) viewSubs.pop()?.dispose();
  if (!editor || props.singlePane) return;
  const leftEd = editor.getOriginalEditor();
  const rightEd = editor.getModifiedEditor();
  const onView = () => placeArrows();
  viewSubs.push(
    leftEd.onDidScrollChange(onView),
    rightEd.onDidScrollChange(onView),
    leftEd.onDidLayoutChange(onView),
    rightEd.onDidLayoutChange(onView)
  );
}

function applyDiffAlgorithm() {
  if (!editor || props.singlePane) return;
  editor.updateOptions({
    diffAlgorithm: tierOpts.value.diffAlgorithm,
  });
}

function mountEditor() {
  if (!host.value) return;
  original = monaco.editor.createModel(props.left, "plaintext");

  // Editor tool: single CodeEditor → one line-number gutter (no diff overview)
  if (props.singlePane) {
    codeEditor = monaco.editor.create(host.value, {
      model: original,
      automaticLayout: true,
      readOnly: !props.editableLeft,
      theme: props.monacoTheme,
      fontSize: 13,
      wordWrap: props.wordWrap ? "on" : "off",
      lineNumbers: "on",
      glyphMargin: false,
      folding: true,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      // Avoid residual mono-diff dual chrome
      renderLineHighlight: "line",
    });
    contentSub = original.onDidChangeContent(() => {
      if (suppressEmit || !props.editableLeft) return;
      emit("leftChange", original!.getValue());
    });
    emit("units", []);
    setTimeout(() => emit("ready"), 100);
    return;
  }

  modified = monaco.editor.createModel(props.right, "plaintext");
  editor = monaco.editor.createDiffEditor(host.value, {
    automaticLayout: true,
    readOnly: !props.editableLeft,
    renderSideBySide: true,
    originalEditable: !!props.editableLeft,
    theme: props.monacoTheme,
    diffAlgorithm: tierOpts.value.diffAlgorithm,
    ignoreTrimWhitespace: false,
    renderIndicators: true,
    fontSize: 13,
    enableSplitViewResizing: true,
    // Hide diff-specific overview that can look like a second line-number rail
    renderOverviewRuler: true,
    renderMarginRevertIcon: false,
  });
  // Single line-number column per pane (default); hide glyph margin noise
  editor.getOriginalEditor().updateOptions({
    glyphMargin: false,
    folding: true,
    lineNumbers: "on",
  });
  editor.getModifiedEditor().updateOptions({
    glyphMargin: false,
    folding: true,
    lineNumbers: "on",
  });
  editor.setModel({ original, modified });
  applyWordWrap();
  sub = editor.onDidUpdateDiff(() => {
    scheduleRecomputeUnits();
  });
  contentSub = original.onDidChangeContent(() => {
    if (suppressEmit || !props.editableLeft) return;
    emit("leftChange", original!.getValue());
  });
  bindViewListeners();
  setTimeout(() => {
    scheduleRecomputeUnits();
    emit("ready");
  }, 200);
}

watch(
  () => [props.left, props.right, props.path] as const,
  () => {
    if (!original) return;
    suppressEmit = true;
    try {
      if (original.getValue() !== props.left) original.setValue(props.left);
      if (modified && modified.getValue() !== props.right) {
        modified.setValue(props.right);
      }
    } finally {
      suppressEmit = false;
    }
    if (!props.singlePane) {
      applyDiffAlgorithm();
      setTimeout(scheduleRecomputeUnits, 150);
    }
  }
);

watch(
  () => resolvedTier.value,
  () => {
    applyDiffAlgorithm();
    scheduleRecomputeUnits();
  }
);

watch(
  () => [props.editableLeft, props.singlePane] as const,
  () => applyEditability()
);

watch(
  () => props.monacoTheme,
  (th) => {
    monaco.editor.setTheme(th || "vs-dark");
  }
);

watch(
  () => props.wordWrap,
  () => applyWordWrap()
);

onMounted(mountEditor);

onBeforeUnmount(() => {
  cancelPendingUnits();
  contentSub?.dispose();
  sub?.dispose();
  while (viewSubs.length) viewSubs.pop()?.dispose();
  codeEditor?.dispose();
  codeEditor = null;
  editor?.dispose();
  original?.dispose();
  modified?.dispose();
  editor = null;
});

function setLeftContent(text: string) {
  suppressEmit = true;
  try {
    original?.setValue(text);
  } finally {
    suppressEmit = false;
  }
  if (!props.singlePane) setTimeout(scheduleRecomputeUnits, 150);
}

function revealLine(line: number) {
  const ed = codeEditor || editor?.getOriginalEditor();
  if (!ed || !line || line < 1) return;
  ed.revealLineInCenter(line);
  ed.setPosition({ lineNumber: line, column: 1 });
  ed.focus();
}

function getLeftContent() {
  return original?.getValue() ?? props.left;
}

function onArrowClick(a: GutterAction) {
  // Always pull compare → work (glyph unchanged by display swap)
  emit("pullUnit", a.unit);
}

defineExpose({ setLeftContent, recomputeUnits, revealLine, getLeftContent });
</script>

<template>
  <div class="diff-wrap">
    <div ref="host" class="diff-host" />
    <div
      v-if="showGutterActions && !singlePane"
      ref="arrowLayer"
      class="arrow-layer"
    >
      <button
        v-for="a in arrows"
        :key="a.id"
        type="button"
        class="gutter-arrow"
        :class="a.kind"
        :style="{ top: a.top + 'px', left: a.left + 'px' }"
        :title="a.title"
        @click="onArrowClick(a)"
      >
        {{ a.glyph }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.diff-wrap {
  position: relative;
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.diff-host {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
}
.arrow-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 4;
}
.gutter-arrow {
  position: absolute;
  /* left set from real Monaco split rail in placeArrows */
  transform: translateX(-50%);
  pointer-events: auto;
  width: 1.35rem;
  height: 1.35rem;
  padding: 0;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--accent);
  font-size: 0.85rem;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
  cursor: pointer;
}
.gutter-arrow:hover {
  background: color-mix(in srgb, var(--accent) 35%, var(--panel));
  color: var(--text);
}
.gutter-arrow.block {
  color: #a855f7;
  font-size: 0.95rem;
}
.gutter-arrow.hunk {
  color: var(--green);
  font-size: 0.8rem;
}
</style>

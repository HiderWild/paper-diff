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
import WordHoverCard from "./WordHoverCard.vue";
import MathHoverCard from "../viewer/MathHoverCard.vue";
import { findMathAtOffset } from "../viewer/findMathAtOffset";
import { injectMathHoverCss } from "../viewer/renderMathHoverHtml";
import {
  hitTestHoverUnit,
  MAX_WORD_DECORATIONS,
  sentenceUnitsOf,
  trueSideForVisualEditor,
  unitCardModel,
  unitToMonacoRange,
  wordUnitsOf,
  type WordCardModel,
} from "./wordHover";

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
    /**
     * When true, props.left is compare and props.right is work (display flip).
     * Unit left/right still match props order; true-source labels use this flag.
     */
    sidesSwapped?: boolean;
    /** Enable word/phrase hover card (default on for diff when word units exist) */
    enableWordHover?: boolean;
    /** Monaco language id for syntax highlight (default plaintext) */
    language?: string;
  }>(),
  {
    editableLeft: false,
    singlePane: false,
    monacoTheme: "vs-dark",
    showGutterActions: true,
    wordWrap: false,
    sidesSwapped: false,
    enableWordHover: true,
    language: "plaintext",
  }
);

const emit = defineEmits<{
  units: [DiffUnit[]];
  ready: [];
  leftChange: [content: string];
  pullUnit: [unit: DiffUnit];
  /** Original-pane width ratio 0–1 relative to diff host (for header alignment) */
  splitRatio: [ratio: number];
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
const mouseSubs: monaco.IDisposable[] = [];
let suppressEmit = false;
let lastUnits: DiffUnit[] = [];
/** Cancel pending idle unit build when content changes / unmount. */
let unitIdleHandle: number | null = null;
let unitTimeoutHandle: ReturnType<typeof setTimeout> | null = null;
let wordDecoOrig: monaco.editor.IEditorDecorationsCollection | null = null;
let wordDecoMod: monaco.editor.IEditorDecorationsCollection | null = null;
let hoverTimer: ReturnType<typeof setTimeout> | null = null;
/** When true, mouse is over the float card — do not auto-dismiss on editor leave */
let pointerOnCard = false;

const hoverCard = ref<{
  model: WordCardModel;
  x: number;
  y: number;
} | null>(null);

/** KaTeX formula preview (editor / tex language) — not Monaco built-in hover. */
const mathHover = ref<{
  latex: string;
  display: boolean;
  x: number;
  y: number;
} | null>(null);
const mathSubs: monaco.IDisposable[] = [];
let mathHoverTimer: ReturnType<typeof setTimeout> | null = null;
let pointerOnMathCard = false;

const KIND_RANK = { line: 3, block: 2, hunk: 1 } as const;
/** Max vertical offset (px) for one secondary arrow when primary is already on the line. */
const SECONDARY_OFFSET_PX = 16;

const resolvedTier = computed<FileTier>(() => {
  if (props.fileTier) return props.fileTier;
  return estimatePairTier(props.left, props.right);
});

const tierOpts = computed(() => diffOptionsForTier(resolvedTier.value));

const wordHoverEnabled = computed(
  () =>
    props.enableWordHover &&
    !props.singlePane &&
    props.showGutterActions &&
    tierOpts.value.wordUnits
);

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

function clearWordHover() {
  if (hoverTimer != null) {
    clearTimeout(hoverTimer);
    hoverTimer = null;
  }
  pointerOnCard = false;
  hoverCard.value = null;
}

function clearMathHover() {
  if (mathHoverTimer != null) {
    clearTimeout(mathHoverTimer);
    mathHoverTimer = null;
  }
  pointerOnMathCard = false;
  mathHover.value = null;
}

function scheduleMathDismiss(ms = 280) {
  if (pointerOnMathCard) return;
  if (mathHoverTimer != null) clearTimeout(mathHoverTimer);
  mathHoverTimer = setTimeout(() => {
    if (!pointerOnMathCard) mathHover.value = null;
    mathHoverTimer = null;
  }, ms);
}

function onMathCardEnter() {
  pointerOnMathCard = true;
  if (mathHoverTimer != null) {
    clearTimeout(mathHoverTimer);
    mathHoverTimer = null;
  }
}

function onMathCardLeave() {
  pointerOnMathCard = false;
  scheduleMathDismiss(200);
}

function latexMathEnabled() {
  return (props.language || "") === "latex";
}

function tryShowMathHover(
  ed: monaco.editor.ICodeEditor,
  e: monaco.editor.IEditorMouseEvent
) {
  if (!latexMathEnabled()) {
    clearMathHover();
    return false;
  }
  // Word-accept card takes priority in comparer when active
  if (hoverCard.value) return false;

  const target = e.target;
  // CONTENT_TEXT=6, CONTENT_EMPTY=7 — also allow numeric for older typings
  const t = target.type as number;
  if (t !== 6 && t !== 7) {
    scheduleMathDismiss(150);
    return false;
  }
  const model = ed.getModel();
  const pos = target.position;
  if (!model || !pos) return false;
  const offset = model.getOffsetAt(pos);
  const snip = findMathAtOffset(model.getValue(), offset);
  if (!snip) {
    scheduleMathDismiss(120);
    return false;
  }
  // Prefer viewport client coords for position:fixed card
  const be = e.event.browserEvent as MouseEvent | undefined;
  const px = be?.clientX ?? e.event.posx ?? 0;
  const py = be?.clientY ?? e.event.posy ?? 0;

  if (mathHoverTimer != null) clearTimeout(mathHoverTimer);
  mathHoverTimer = setTimeout(() => {
    mathHover.value = {
      latex: snip.latex,
      display: snip.display,
      x: px,
      y: py + 14,
    };
    mathHoverTimer = null;
  }, 220);
  return true;
}

function bindLatexMathHoverListeners() {
  while (mathSubs.length) mathSubs.pop()?.dispose();
  if (!latexMathEnabled()) return;
  injectMathHoverCss();
  const editors: monaco.editor.ICodeEditor[] = [];
  if (codeEditor) editors.push(codeEditor);
  if (editor) {
    editors.push(editor.getOriginalEditor(), editor.getModifiedEditor());
  }
  for (const ed of editors) {
    mathSubs.push(
      ed.onMouseMove((ev) => {
        tryShowMathHover(ed, ev);
      }),
      ed.onMouseLeave(() => {
        scheduleMathDismiss(220);
      })
    );
  }
}

function scheduleDismiss(ms = 280) {
  if (pointerOnCard) return;
  if (hoverTimer != null) clearTimeout(hoverTimer);
  hoverTimer = setTimeout(() => {
    if (!pointerOnCard) hoverCard.value = null;
    hoverTimer = null;
  }, ms);
}

function onCardPointerEnter() {
  pointerOnCard = true;
  if (hoverTimer != null) {
    clearTimeout(hoverTimer);
    hoverTimer = null;
  }
}

function onCardPointerLeave() {
  pointerOnCard = false;
  scheduleDismiss(200);
}

function syncWordDecorations(units: DiffUnit[]) {
  if (!editor || props.singlePane || !wordHoverEnabled.value) {
    wordDecoOrig?.clear();
    wordDecoMod?.clear();
    return;
  }
  const words = wordUnitsOf(units);
  const sentences = sentenceUnitsOf(units);
  // Prefer words, then fill remaining budget with sentences
  const budget = MAX_WORD_DECORATIONS;
  const pick = [
    ...words.slice(0, budget),
    ...sentences.slice(0, Math.max(0, budget - words.length)),
  ];
  const origDecs: monaco.editor.IModelDeltaDecoration[] = [];
  const modDecs: monaco.editor.IModelDeltaDecoration[] = [];
  const wordOpts: monaco.editor.IModelDecorationOptions = {
    className: "pd-word-hover-deco",
    inlineClassName: "pd-word-hover-inline",
    stickiness:
      monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
    zIndex: 2,
  };
  const sentOpts: monaco.editor.IModelDecorationOptions = {
    className: "pd-sentence-hover-deco",
    inlineClassName: "pd-sentence-hover-inline",
    stickiness:
      monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
    zIndex: 1,
  };
  for (const u of pick) {
    const opts = u.granularity === "sentence" ? sentOpts : wordOpts;
    // Ranges are in props/original-modified (display) order
    origDecs.push({
      range: unitToMonacoRange(u.left),
      options: opts,
    });
    modDecs.push({
      range: unitToMonacoRange(u.right),
      options: opts,
    });
  }
  if (!wordDecoOrig) {
    wordDecoOrig = editor.getOriginalEditor().createDecorationsCollection();
  }
  if (!wordDecoMod) {
    wordDecoMod = editor.getModifiedEditor().createDecorationsCollection();
  }
  wordDecoOrig.set(origDecs);
  wordDecoMod.set(modDecs);
}

function recomputeUnitsNow() {
  if (!editor || props.singlePane) {
    lastUnits = [];
    emit("units", []);
    arrows.value = [];
    clearWordHover();
    wordDecoOrig?.clear();
    wordDecoMod?.clear();
    return;
  }
  const opts = tierOpts.value;
  const changes = (editor.getLineChanges() || []) as LineChange[];
  // When word hover is enabled, force wordUnits even if tier said false for M —
  // stay aligned with tierOpts.wordUnits (S only by default).
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
  syncWordDecorations(units);
  clearWordHover();
  void nextTick(() => placeArrows());
}

function onEditorMouseMove(
  visual: "original" | "modified",
  e: monaco.editor.IEditorMouseEvent
) {
  if (!wordHoverEnabled.value || !editor) {
    clearWordHover();
    return;
  }
  const t = e.target;
  const pos = t.position;
  // CONTENT_TEXT = 6 in Monaco MouseTargetType
  if (!pos || (t.type !== 6 && t.type !== 7)) {
    scheduleDismiss(200);
    return;
  }
  const trueSide = trueSideForVisualEditor(visual, props.sidesSwapped);
  // Monaco columns are 1-based → DiffUnit 0-based
  const col0 = Math.max(0, pos.column - 1);
  const unit = hitTestHoverUnit(
    lastUnits,
    trueSide,
    pos.lineNumber,
    col0,
    props.sidesSwapped,
    true // include sentence if no smaller word hit
  );
  if (!unit) {
    scheduleDismiss(250);
    return;
  }
  const bx = e.event.posx;
  const by = e.event.posy;
  if (hoverTimer != null) clearTimeout(hoverTimer);
  hoverTimer = setTimeout(() => {
    hoverCard.value = {
      model: unitCardModel(unit, props.sidesSwapped),
      x: bx,
      y: by,
    };
    hoverTimer = null;
  }, 350);
}

function bindWordHoverListeners() {
  while (mouseSubs.length) mouseSubs.pop()?.dispose();
  if (!editor || props.singlePane || !wordHoverEnabled.value) return;
  const orig = editor.getOriginalEditor();
  const mod = editor.getModifiedEditor();
  mouseSubs.push(
    orig.onMouseMove((e) => onEditorMouseMove("original", e)),
    mod.onMouseMove((e) => onEditorMouseMove("modified", e)),
    orig.onMouseLeave(() => scheduleDismiss(450)),
    mod.onMouseLeave(() => scheduleDismiss(450)),
    orig.onDidScrollChange(() => clearWordHover()),
    mod.onDidScrollChange(() => clearWordHover())
  );
}

function onHoverApply() {
  const h = hoverCard.value;
  if (!h) return;
  emit("pullUnit", h.model.unit);
  clearWordHover();
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

/** Emit original pane width / host width so headers can match Monaco columns. */
function emitSplitRatio() {
  if (!editor || !host.value || props.singlePane) return;
  const hostRect = host.value.getBoundingClientRect();
  if (hostRect.width <= 0) return;
  const mid = splitRailLeftPx();
  if (mid == null) return;
  const ratio = Math.min(0.92, Math.max(0.08, mid / hostRect.width));
  emit("splitRatio", ratio);
}

function placeArrows() {
  if (!props.showGutterActions || props.singlePane || !editor || !host.value) {
    arrows.value = [];
    emitSplitRatio();
    return;
  }
  const railLeft = splitRailLeftPx();
  if (railLeft == null) {
    arrows.value = [];
    return;
  }
  emitSplitRatio();

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
  const onView = () => {
    placeArrows();
    emitSplitRatio();
  };
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
  original = monaco.editor.createModel(props.left, props.language || "plaintext");

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
    bindLatexMathHoverListeners();
    emit("units", []);
    setTimeout(() => emit("ready"), 100);
    return;
  }

  modified = monaco.editor.createModel(props.right, props.language || "plaintext");
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
  bindWordHoverListeners();
  bindLatexMathHoverListeners();
  setTimeout(() => {
    scheduleRecomputeUnits();
    emitSplitRatio();
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

// Keep model language in sync when path changes (e.g. switching tabs in editor)
watch(
  () => props.language,
  (lang) => {
    const id = lang || "plaintext";
    if (original && original.getLanguageId() !== id) {
      monaco.editor.setModelLanguage(original, id);
    }
    if (modified && modified.getLanguageId() !== id) {
      monaco.editor.setModelLanguage(modified, id);
    }
    clearMathHover();
    bindLatexMathHoverListeners();
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

watch(
  () => [props.sidesSwapped, props.enableWordHover, resolvedTier.value] as const,
  () => {
    syncWordDecorations(lastUnits);
    bindWordHoverListeners();
    clearWordHover();
  }
);

onMounted(mountEditor);

onBeforeUnmount(() => {
  cancelPendingUnits();
  clearWordHover();
  clearMathHover();
  contentSub?.dispose();
  sub?.dispose();
  while (viewSubs.length) viewSubs.pop()?.dispose();
  while (mouseSubs.length) mouseSubs.pop()?.dispose();
  while (mathSubs.length) mathSubs.pop()?.dispose();
  wordDecoOrig?.clear();
  wordDecoMod?.clear();
  wordDecoOrig = null;
  wordDecoMod = null;
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

defineExpose({
  setLeftContent,
  recomputeUnits,
  revealLine,
  getLeftContent,
  emitSplitRatio,
});
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
    <Teleport to="body">
      <WordHoverCard
        v-if="hoverCard"
        :model="hoverCard.model"
        :x="hoverCard.x"
        :y="hoverCard.y"
        @apply="onHoverApply"
        @dismiss="clearWordHover"
        @pointer-enter="onCardPointerEnter"
        @pointer-leave="onCardPointerLeave"
      />
      <MathHoverCard
        v-if="mathHover"
        :latex="mathHover.latex"
        :display="mathHover.display"
        :x="mathHover.x"
        :y="mathHover.y"
        @dismiss="clearMathHover"
        @pointer-enter="onMathCardEnter"
        @pointer-leave="onMathCardLeave"
      />
    </Teleport>
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
/* Word / sentence hover decorations (global class names for Monaco DOM) */
:global(.pd-word-hover-inline) {
  border-bottom: 1px dashed color-mix(in srgb, var(--accent, #3b82f6) 70%, transparent);
  cursor: help;
}
:global(.pd-sentence-hover-inline) {
  border-bottom: 1px dotted color-mix(in srgb, var(--green, #22c55e) 55%, transparent);
  cursor: help;
}
:global(.pd-word-hover-deco),
:global(.pd-sentence-hover-deco) {
  /* range marker; keep light so Monaco char diff stays primary */
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

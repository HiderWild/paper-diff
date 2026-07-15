<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import {
  buildDiffUnits,
  type DiffUnit,
  type LineChange,
} from "./sentenceMapper";
import { gutterActionsFromUnits, type GutterAction } from "./gutterActions";

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
  }>(),
  {
    editableLeft: false,
    singlePane: false,
    monacoTheme: "vs-dark",
    showGutterActions: true,
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
const arrows = ref<
  Array<GutterAction & { top: number; title: string; glyph: string }>
>([]);

let editor: monaco.editor.IStandaloneDiffEditor | null = null;
let original: monaco.editor.ITextModel | null = null;
let modified: monaco.editor.ITextModel | null = null;
let sub: monaco.IDisposable | null = null;
let contentSub: monaco.IDisposable | null = null;
let scrollSub: monaco.IDisposable | null = null;
let layoutSub: monaco.IDisposable | null = null;
let suppressEmit = false;
let lastUnits: DiffUnit[] = [];

function recomputeUnits() {
  if (!editor) return;
  const changes = (editor.getLineChanges() || []) as LineChange[];
  const units = buildDiffUnits(
    original?.getValue() ?? props.left,
    modified?.getValue() ?? props.right,
    changes
  );
  lastUnits = units;
  emit("units", units);
  void nextTick(() => placeArrows());
}

function placeArrows() {
  if (!props.showGutterActions || props.singlePane || !editor || !host.value) {
    arrows.value = [];
    return;
  }
  const leftEd = editor.getOriginalEditor();
  const acts = gutterActionsFromUnits(lastUnits);
  // one arrow per leftLine prefer: line > block > hunk
  const byLine = new Map<number, GutterAction>();
  for (const a of acts) {
    const prev = byLine.get(a.leftLine);
    if (!prev) {
      byLine.set(a.leftLine, a);
      continue;
    }
    const rank = { line: 3, block: 2, hunk: 1 } as const;
    if (rank[a.kind] > rank[prev.kind]) byLine.set(a.leftLine, a);
  }
  // also keep distinct block/hunk at same line with offset if needed
  const list: Array<GutterAction & { top: number; title: string; glyph: string }> =
    [];
  for (const a of byLine.values()) {
    const top = leftEd.getTopForLineNumber(Math.max(1, a.leftLine));
    const scroll = leftEd.getScrollTop();
    const y = top - scroll + 2;
    const glyph =
      a.kind === "line" ? "←" : a.kind === "block" ? "⇐" : "⟸";
    list.push({
      ...a,
      top: y,
      glyph,
      title: t(a.labelKey),
    });
  }
  // add block/hunk extras that lost to line at same spot — offset
  for (const a of acts) {
    if (a.kind === "line") continue;
    if (byLine.get(a.leftLine)?.id === a.id) continue;
    if (a.kind === "block" || a.kind === "hunk") {
      const top = leftEd.getTopForLineNumber(Math.max(1, a.leftLine));
      const scroll = leftEd.getScrollTop();
      list.push({
        ...a,
        top: top - scroll + (a.kind === "block" ? 18 : 34),
        glyph: a.kind === "block" ? "⇐" : "⟸",
        title: t(a.labelKey),
      });
    }
  }
  arrows.value = list.filter((x) => x.top > -40 && x.top < (host.value?.clientHeight || 800) + 40);
}

function applyEditability() {
  if (!editor) return;
  editor.updateOptions({
    readOnly: !props.editableLeft,
    originalEditable: !!props.editableLeft,
    renderSideBySide: !props.singlePane,
  });
}

function mountEditor() {
  if (!host.value) return;
  original = monaco.editor.createModel(props.left, "plaintext");
  modified = monaco.editor.createModel(props.right, "plaintext");
  editor = monaco.editor.createDiffEditor(host.value, {
    automaticLayout: true,
    readOnly: !props.editableLeft,
    renderSideBySide: !props.singlePane,
    originalEditable: !!props.editableLeft,
    theme: props.monacoTheme,
    diffAlgorithm: "advanced",
    ignoreTrimWhitespace: false,
    renderIndicators: true,
    fontSize: 13,
    // leave space for center arrows overlay
    enableSplitViewResizing: true,
  });
  editor.setModel({ original, modified });
  sub = editor.onDidUpdateDiff(() => {
    recomputeUnits();
  });
  contentSub = original.onDidChangeContent(() => {
    if (suppressEmit || !props.editableLeft) return;
    emit("leftChange", original!.getValue());
  });
  const leftEd = editor.getOriginalEditor();
  scrollSub = leftEd.onDidScrollChange(() => placeArrows());
  layoutSub = leftEd.onDidLayoutChange(() => placeArrows());
  setTimeout(() => {
    recomputeUnits();
    emit("ready");
  }, 200);
}

watch(
  () => [props.left, props.right, props.path] as const,
  () => {
    if (!original || !modified) return;
    suppressEmit = true;
    try {
      if (original.getValue() !== props.left) original.setValue(props.left);
      if (modified.getValue() !== props.right) modified.setValue(props.right);
    } finally {
      suppressEmit = false;
    }
    setTimeout(recomputeUnits, 150);
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

onMounted(mountEditor);

onBeforeUnmount(() => {
  contentSub?.dispose();
  sub?.dispose();
  scrollSub?.dispose();
  layoutSub?.dispose();
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
  setTimeout(recomputeUnits, 150);
}

function revealLine(line: number) {
  const ed = editor?.getOriginalEditor();
  if (!ed || !line || line < 1) return;
  ed.revealLineInCenter(line);
  ed.setPosition({ lineNumber: line, column: 1 });
  ed.focus();
}

function getLeftContent() {
  return original?.getValue() ?? props.left;
}

function onArrowClick(a: GutterAction) {
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
        :style="{ top: a.top + 'px' }"
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
  /* Monaco split is ~50%; arrows sit on center rail */
  left: 50%;
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

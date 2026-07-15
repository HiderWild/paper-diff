<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import {
  buildDiffUnits,
  type DiffUnit,
  type LineChange,
} from "./sentenceMapper";

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
    /** Work side (original/left) editable */
    editableLeft?: boolean;
    /** Hide right pane (single editor mode) */
    singlePane?: boolean;
    /** Monaco theme name */
    monacoTheme?: string;
  }>(),
  {
    editableLeft: false,
    singlePane: false,
    monacoTheme: "vs-dark",
  }
);

const emit = defineEmits<{
  units: [DiffUnit[]];
  ready: [];
  leftChange: [content: string];
}>();

const host = ref<HTMLDivElement | null>(null);
let editor: monaco.editor.IStandaloneDiffEditor | null = null;
let original: monaco.editor.ITextModel | null = null;
let modified: monaco.editor.ITextModel | null = null;
let sub: monaco.IDisposable | null = null;
let contentSub: monaco.IDisposable | null = null;
let suppressEmit = false;

function recomputeUnits() {
  if (!editor) return;
  const changes = (editor.getLineChanges() || []) as LineChange[];
  const units = buildDiffUnits(
    original?.getValue() ?? props.left,
    modified?.getValue() ?? props.right,
    changes
  );
  emit("units", units);
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
  });
  editor.setModel({ original, modified });
  sub = editor.onDidUpdateDiff(() => {
    recomputeUnits();
  });
  contentSub = original.onDidChangeContent(() => {
    if (suppressEmit || !props.editableLeft) return;
    emit("leftChange", original!.getValue());
  });
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

defineExpose({ setLeftContent, recomputeUnits, revealLine, getLeftContent });
</script>

<template>
  <div ref="host" class="diff-host" />
</template>

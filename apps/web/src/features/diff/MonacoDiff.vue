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

const props = defineProps<{
  left: string;
  right: string;
  path: string;
}>();

const emit = defineEmits<{
  units: [DiffUnit[]];
  ready: [];
}>();

const host = ref<HTMLDivElement | null>(null);
let editor: monaco.editor.IStandaloneDiffEditor | null = null;
let original: monaco.editor.ITextModel | null = null;
let modified: monaco.editor.ITextModel | null = null;
let sub: monaco.IDisposable | null = null;

function recomputeUnits() {
  if (!editor) return;
  const changes = (editor.getLineChanges() || []) as LineChange[];
  const units = buildDiffUnits(props.left, props.right, changes);
  emit("units", units);
}

function mountEditor() {
  if (!host.value) return;
  original = monaco.editor.createModel(props.left, "plaintext");
  modified = monaco.editor.createModel(props.right, "plaintext");
  editor = monaco.editor.createDiffEditor(host.value, {
    automaticLayout: true,
    readOnly: true,
    renderSideBySide: true,
    originalEditable: false,
    theme: "vs-dark",
    diffAlgorithm: "advanced",
    ignoreTrimWhitespace: false,
    renderIndicators: true,
    fontSize: 13,
  });
  editor.setModel({ original, modified });
  sub = editor.onDidUpdateDiff(() => {
    recomputeUnits();
  });
  setTimeout(() => {
    recomputeUnits();
    emit("ready");
  }, 200);
}

watch(
  () => [props.left, props.right, props.path],
  () => {
    if (!original || !modified) return;
    if (original.getValue() !== props.left) original.setValue(props.left);
    if (modified.getValue() !== props.right) modified.setValue(props.right);
    setTimeout(recomputeUnits, 150);
  }
);

onMounted(mountEditor);

onBeforeUnmount(() => {
  sub?.dispose();
  editor?.dispose();
  original?.dispose();
  modified?.dispose();
  editor = null;
});

function setLeftContent(text: string) {
  original?.setValue(text);
  setTimeout(recomputeUnits, 150);
}

/** Jump original (left) editor to 1-based line. */
function revealLine(line: number) {
  const ed = editor?.getOriginalEditor();
  if (!ed || !line || line < 1) return;
  ed.revealLineInCenter(line);
  ed.setPosition({ lineNumber: line, column: 1 });
  ed.focus();
}

defineExpose({ setLeftContent, recomputeUnits, revealLine });
</script>

<template>
  <div ref="host" class="diff-host" />
</template>

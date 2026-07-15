<script setup lang="ts">
import { useI18n } from "vue-i18n";
import type { ToolKind } from "../stores/workspace";

const { t } = useI18n();

const tools: Array<{ kind: ToolKind; icon: string; labelKey: string }> = [
  { kind: "comparer", icon: "hankelijk", labelKey: "tools.comparer" },
  { kind: "editor", icon: "✎", labelKey: "tools.editor" },
  { kind: "pdf", icon: "PDF", labelKey: "tools.pdf" },
  { kind: "word", icon: "W", labelKey: "tools.word" },
];

const emit = defineEmits<{
  open: [kind: ToolKind];
  dragStart: [kind: ToolKind, e: DragEvent];
}>();

function onDragStart(kind: ToolKind, e: DragEvent) {
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "copyMove";
    e.dataTransfer.setData("text/plain", `tool:${kind}`);
    e.dataTransfer.setData("application/x-paper-diff-tool", kind);
  }
  emit("dragStart", kind, e);
}
</script>

<template>
  <div class="tool-strip" role="toolbar" :aria-label="t('tools.strip')">
    <button
      v-for="tool in tools"
      :key="tool.kind"
      type="button"
      class="tool-icon"
      :title="t(tool.labelKey)"
      draggable="true"
      @click="emit('open', tool.kind)"
      @dragstart="onDragStart(tool.kind, $event)"
    >
      <span class="glyph">{{ tool.icon }}</span>
    </button>
  </div>
</template>

<style scoped>
.tool-strip {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0 0.25rem;
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  margin: 0 0.25rem;
}
.tool-icon {
  width: 2rem;
  height: 1.75rem;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: var(--muted);
  border: 1px solid transparent;
  border-radius: 4px;
  cursor: grab;
  font-size: 0.75rem;
  font-weight: 600;
}
.tool-icon:hover {
  background: #1e293b;
  color: var(--text);
  border-color: var(--border);
}
.tool-icon:active {
  cursor: grabbing;
}
.glyph {
  pointer-events: none;
}
</style>

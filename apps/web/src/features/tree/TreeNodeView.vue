<script setup lang="ts">
import type { TreeNode } from "./buildTree";

defineProps<{
  node: TreeNode;
  depth: number;
  currentPath: string | null;
  expanded: Record<string, boolean>;
  busy?: boolean;
  statusLabel: (s?: string) => string;
  fileActions: (
    s?: string
  ) => Array<{ label: string; action: "add" | "delete" | "replace_all" }>;
  tCompare: string;
}>();

const emit = defineEmits<{
  toggle: [path: string];
  open: [path: string];
  action: [path: string, action: "add" | "delete" | "replace_all"];
  compareDir: [path: string];
}>();
</script>

<template>
  <!-- Directory row -->
  <div v-if="node.type === 'dir'" class="tree-dir">
    <div
      class="tree-row dir"
      :style="{ paddingLeft: `${6 + depth * 12}px` }"
      @click="emit('toggle', node.path)"
    >
      <span class="chevron">{{ expanded[node.path] ? "▾" : "▸" }}</span>
      <span class="folder-icon">📁</span>
      <span class="tree-name dir-name">{{ node.name }}</span>
      <button
        class="cmp-btn"
        type="button"
        :disabled="busy"
        :title="tCompare"
        @click.stop="emit('compareDir', node.path)"
      >
        ≠
      </button>
    </div>
    <template v-if="expanded[node.path] && node.children?.length">
      <TreeNodeView
        v-for="c in node.children"
        :key="c.path + c.type"
        :node="c"
        :depth="depth + 1"
        :current-path="currentPath"
        :expanded="expanded"
        :busy="busy"
        :status-label="statusLabel"
        :file-actions="fileActions"
        :t-compare="tCompare"
        @toggle="emit('toggle', $event)"
        @open="emit('open', $event)"
        @action="(p, a) => emit('action', p, a)"
        @compare-dir="emit('compareDir', $event)"
      />
    </template>
  </div>

  <!-- File row: basename only -->
  <div v-else class="tree-file-block">
    <div
      class="tree-row file"
      :class="{ active: currentPath === node.path }"
      :style="{ paddingLeft: `${6 + depth * 12}px` }"
      :title="node.path"
      draggable="true"
      @click="emit('open', node.path)"
      @dragstart="
        ($event as DragEvent).dataTransfer?.setData(
          'application/x-paper-diff-path',
          node.path
        );
        ($event as DragEvent).dataTransfer?.setData('text/plain', node.path);
        if (($event as DragEvent).dataTransfer)
          ($event as DragEvent).dataTransfer!.effectAllowed = 'copy';
      "
    >
      <span class="chevron placeholder" />
      <span
        v-if="node.file?.status && node.file.status !== 'unknown'"
        class="badge"
        :class="node.file.status"
      >
        {{ statusLabel(node.file.status) }}
      </span>
      <span
        v-else-if="node.file?.compare_state"
        class="badge"
        :class="node.file.compare_state"
      >
        {{ statusLabel(node.file.compare_state) }}
      </span>
      <span class="tree-name">{{ node.name }}</span>
      <span v-if="node.file?.kind === 'binary'" class="badge binary">bin</span>
    </div>
    <div
      v-if="fileActions(node.file?.status).length"
      class="file-ops"
      :style="{ paddingLeft: `${24 + depth * 12}px` }"
    >
      <button
        v-for="a in fileActions(node.file?.status)"
        :key="a.action"
        class="secondary mini"
        type="button"
        :disabled="busy"
        @click.stop="emit('action', node.path, a.action)"
      >
        {{ a.label }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.tree-row {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  width: 100%;
  min-height: 1.55rem;
  text-align: left;
  color: var(--text);
  border-radius: 3px;
  padding: 0.1rem 0.35rem 0.1rem 0;
  font-size: 0.8rem;
  cursor: pointer;
  user-select: none;
}
.tree-row:hover {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.tree-row.active {
  background: color-mix(in srgb, var(--accent) 28%, transparent);
}
.tree-row.dir .dir-name {
  font-weight: 600;
  color: var(--text);
}
.chevron {
  width: 0.9rem;
  flex-shrink: 0;
  text-align: center;
  color: var(--muted);
  font-size: 0.7rem;
}
.chevron.placeholder {
  visibility: hidden;
}
.folder-icon {
  font-size: 0.75rem;
  flex-shrink: 0;
  opacity: 0.85;
}
.tree-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.cmp-btn {
  flex-shrink: 0;
  opacity: 0;
  background: var(--secondary-btn);
  color: var(--text);
  border: none;
  border-radius: 3px;
  font-size: 0.65rem;
  padding: 0.05rem 0.3rem;
  cursor: pointer;
}
.tree-row.dir:hover .cmp-btn {
  opacity: 0.85;
}
.cmp-btn:hover:not(:disabled) {
  opacity: 1 !important;
  background: var(--accent);
}
.file-ops {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem;
  margin: 0 0 0.15rem;
}
.badge {
  font-size: 0.6rem;
  padding: 0.05rem 0.25rem;
  border-radius: 3px;
  background: var(--secondary-btn);
  color: var(--muted);
  flex-shrink: 0;
}
.badge.modified {
  background: color-mix(in srgb, var(--green) 28%, var(--panel));
  color: var(--green);
}
.badge.added {
  background: color-mix(in srgb, var(--accent) 28%, var(--panel));
  color: var(--accent);
}
.badge.removed {
  background: color-mix(in srgb, var(--danger) 28%, var(--panel));
  color: var(--danger);
}
.badge.pending,
.badge.queued,
.badge.comparing {
  background: color-mix(in srgb, #eab308 22%, var(--panel));
  color: color-mix(in srgb, #eab308 75%, var(--text));
}
.badge.skipped {
  background: var(--secondary-btn);
  color: var(--muted);
}
.badge.binary {
  background: color-mix(in srgb, #6366f1 25%, var(--panel));
  color: color-mix(in srgb, #6366f1 70%, var(--text));
}
</style>

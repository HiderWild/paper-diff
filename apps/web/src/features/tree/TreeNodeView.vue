<script setup lang="ts">
import type { TreeNode } from "./buildTree";
import { fileIconForPath } from "./fileIcons";

withDefaults(
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
    fileSource?: "work" | "zone";
    zoneId?: string | null;
    hideFileActions?: boolean;
    hideCompareDir?: boolean;
  }>(),
  {
    fileSource: "work",
    zoneId: null,
    hideFileActions: false,
    hideCompareDir: false,
  }
);

const emit = defineEmits<{
  toggle: [path: string];
  open: [path: string];
  action: [path: string, action: "add" | "delete" | "replace_all"];
  compareDir: [path: string];
  fileContext: [path: string, e: MouseEvent];
}>();

function iconFor(node: TreeNode) {
  return fileIconForPath(node.path, node.file?.kind);
}
</script>

<template>
  <!-- Directory row: CSS triangle twisty (collapsed ▶, open ▼) — no emoji / no ▶ glyph -->
  <div v-if="node.type === 'dir'" class="tree-dir">
    <div
      class="tree-row dir"
      :style="{ paddingLeft: `${6 + depth * 12}px` }"
      :aria-expanded="!!expanded[node.path]"
      role="treeitem"
      @click="emit('toggle', node.path)"
    >
      <span
        class="chevron"
        :class="{ open: expanded[node.path] }"
        aria-hidden="true"
      >
        <span class="chevron-tri" />
      </span>
      <span class="tree-name dir-name">{{ node.name }}</span>
      <button
        v-if="!hideCompareDir"
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
        :file-source="fileSource"
        :zone-id="zoneId"
        :hide-file-actions="hideFileActions"
        :hide-compare-dir="hideCompareDir"
        @toggle="emit('toggle', $event)"
        @open="emit('open', $event)"
        @action="(p, a) => emit('action', p, a)"
        @compare-dir="emit('compareDir', $event)"
        @file-context="(p, e) => emit('fileContext', p, e)"
      />
    </template>
  </div>

  <!-- File row: type icon + name; status is small badge at end (not prefix "work") -->
  <div v-else class="tree-file-block">
    <div
      class="tree-row file"
      :class="{ active: currentPath === node.path }"
      :style="{ paddingLeft: `${6 + depth * 12}px` }"
      :title="node.path"
      draggable="true"
      data-allow-context-menu="1"
      @click="emit('open', node.path)"
      @contextmenu.prevent.stop="
        emit('fileContext', node.path, $event as MouseEvent)
      "
      @dragstart="
        ($event as DragEvent).dataTransfer?.setData(
          'application/x-paper-diff-path',
          node.path
        );
        ($event as DragEvent).dataTransfer?.setData(
          'application/x-paper-diff-side',
          fileSource || 'work'
        );
        if (zoneId)
          ($event as DragEvent).dataTransfer?.setData(
            'application/x-paper-diff-zone-id',
            zoneId
          );
        ($event as DragEvent).dataTransfer?.setData('text/plain', node.path);
        if (($event as DragEvent).dataTransfer)
          ($event as DragEvent).dataTransfer!.effectAllowed = 'copy';
      "
    >
      <span class="chevron placeholder" aria-hidden="true" />
      <span
        class="file-icon"
        :style="{ color: iconFor(node).color }"
        :title="iconFor(node).label"
        >{{ iconFor(node).label }}</span
      >
      <span class="tree-name">{{ node.name }}</span>
      <!-- Diff/accept badges and inline accept buttons removed:
           project tree is the work body; zone comparison is user-initiated only. -->
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
/* VS Code-like twisty: CSS triangle, not a unicode glyph (avoids "·" font fallback) */
.chevron {
  width: 1.1rem;
  height: 1.1rem;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
}
.chevron-tri {
  display: block;
  width: 0;
  height: 0;
  /* ▶ pointing right when collapsed */
  border-style: solid;
  border-width: 4px 0 4px 6px;
  border-color: transparent transparent transparent currentColor;
  transition: transform 0.12s ease;
  transform-origin: 40% 50%;
  transform: rotate(0deg);
}
.chevron.open .chevron-tri {
  /* rotate to ▼ when expanded */
  transform: rotate(90deg);
}
.chevron.placeholder {
  visibility: hidden;
}
.tree-row.dir:hover .chevron {
  color: var(--text);
}
.file-icon {
  flex-shrink: 0;
  min-width: 1.7rem;
  max-width: 2.1rem;
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.1;
  text-align: center;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  opacity: 0.95;
  user-select: none;
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
/* Diff status: trailing, compact — was looking like a "work" prefix when first in the row */
.status-badge {
  margin-left: 0.15rem;
}
.badge {
  font-size: 0.58rem;
  padding: 0.05rem 0.25rem;
  border-radius: 3px;
  background: var(--secondary-btn);
  color: var(--muted);
  flex-shrink: 0;
  max-width: 4.5rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

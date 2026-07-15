<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import OverlayScroll from "../../components/OverlayScroll.vue";
import {
  buildTree,
  filterDotTree,
  topLevelDirPaths,
  type FileMeta,
} from "./buildTree";
import TreeNodeView from "./TreeNodeView.vue";

const props = withDefaults(
  defineProps<{
    files: FileMeta[];
    currentPath: string | null;
    showDotFiles: boolean;
    busy?: boolean;
    /** Allow dragging the toolbar title to rearrange workbench panes */
    draggableTitle?: boolean;
    /** Drag origin for comparers: work project tree vs zone tree */
    fileSource?: "work" | "zone";
    /** Hide toolbar (embedded under a zone header) */
    hideToolbar?: boolean;
    /** Compact layout for nested zone trees */
    compact?: boolean;
    /** When source is zone, optional id embedded in drag payload */
    zoneId?: string | null;
  }>(),
  { fileSource: "work", hideToolbar: false, compact: false, zoneId: null }
);

const emit = defineEmits<{
  open: [path: string];
  action: [path: string, action: "add" | "delete" | "replace_all"];
  compareDir: [prefix: string];
  newCompare: [path: string];
  /** Add path into the focused comparer (or open one), replacing that side. */
  addToCompare: [path: string];
  "update:showDotFiles": [value: boolean];
  hide: [];
  titleDragStart: [e: DragEvent];
  titleDragEnd: [];
}>();

const { t } = useI18n();
/** path -> expanded */
const expanded = ref<Record<string, boolean>>({});
const seeded = ref(false);

const tree = computed(() =>
  filterDotTree(buildTree(props.files), props.showDotFiles)
);

// Seed: expand only top-level dirs once per project load (not every file path flat)
watch(
  () => tree.value,
  (nodes) => {
    if (seeded.value || !nodes.length) return;
    const next: Record<string, boolean> = {};
    for (const p of topLevelDirPaths(nodes)) next[p] = true;
    expanded.value = next;
    seeded.value = true;
  },
  { immediate: true }
);

// Reset seed when file set is cleared (new import)
watch(
  () => props.files.length,
  (n, prev) => {
    if (n === 0) {
      seeded.value = false;
      expanded.value = {};
    } else if (prev === 0 && n > 0) {
      seeded.value = false;
    }
  }
);

function toggle(path: string) {
  expanded.value = { ...expanded.value, [path]: !expanded.value[path] };
}

function statusLabel(s: string | undefined) {
  if (!s) return "";
  const keys = [
    "added",
    "removed",
    "modified",
    "same",
    "unknown",
    "skipped",
    "pending",
    "queued",
    "comparing",
  ];
  if (keys.includes(s)) return t(`status.${s}`);
  return s;
}

function fileActions(status: string | undefined) {
  if (status === "added")
    return [{ label: t("fileActions.add"), action: "add" as const }];
  if (status === "removed")
    return [{ label: t("fileActions.delete"), action: "delete" as const }];
  if (status === "modified")
    return [
      { label: t("fileActions.replaceAll"), action: "replace_all" as const },
    ];
  return [] as Array<{
    label: string;
    action: "add" | "delete" | "replace_all";
  }>;
}

function onAction(path: string, action: "add" | "delete" | "replace_all") {
  emit("action", path, action);
}

function collapseAll() {
  expanded.value = {};
}

function expandTop() {
  const next: Record<string, boolean> = {};
  for (const p of topLevelDirPaths(tree.value)) next[p] = true;
  expanded.value = next;
}

const ctxMenu = ref<{
  x: number;
  y: number;
  path: string;
} | null>(null);

function onFileContext(path: string, e: MouseEvent) {
  e.preventDefault();
  e.stopPropagation();
  ctxMenu.value = { x: e.clientX, y: e.clientY, path };
}

function closeCtx() {
  ctxMenu.value = null;
}

function ctxNewCompare(e?: Event) {
  e?.preventDefault?.();
  e?.stopPropagation?.();
  if (!ctxMenu.value) return;
  const p = ctxMenu.value.path;
  // Close after emit so parent runs before menu unmount teardown
  emit("newCompare", p);
  // Defer close so click is not swallowed by capture listener racing us
  requestAnimationFrame(() => closeCtx());
}

function ctxAddToCompare(e?: Event) {
  e?.preventDefault?.();
  e?.stopPropagation?.();
  if (!ctxMenu.value) return;
  const p = ctxMenu.value.path;
  emit("addToCompare", p);
  requestAnimationFrame(() => closeCtx());
}

function onDocPointerDown(e: Event) {
  const t = e.target as HTMLElement | null;
  if (t?.closest?.(".tree-ctx-menu")) return;
  closeCtx();
}

watch(ctxMenu, (m) => {
  if (m) {
    // pointerdown bubble (not capture): menu buttons receive click first
    window.addEventListener("pointerdown", onDocPointerDown, false);
    window.addEventListener("keydown", onEscClose, true);
  } else {
    window.removeEventListener("pointerdown", onDocPointerDown, false);
    window.removeEventListener("keydown", onEscClose, true);
  }
});

function onEscClose(e: KeyboardEvent) {
  if (e.key === "Escape") closeCtx();
}

onBeforeUnmount(() => {
  window.removeEventListener("pointerdown", onDocPointerDown, false);
  window.removeEventListener("keydown", onEscClose, true);
});
</script>

<template>
  <div class="file-tree" :class="{ compact }">
    <div
      v-if="!hideToolbar"
      class="tree-toolbar"
      :class="{ 'tree-toolbar-drag': draggableTitle }"
      :draggable="!!draggableTitle"
      :title="draggableTitle ? t('panels.dragToRearrange') : undefined"
      @dragstart="draggableTitle && emit('titleDragStart', $event)"
      @dragend="draggableTitle && emit('titleDragEnd')"
    >
      <span v-if="draggableTitle" class="drag-grip" aria-hidden="true">⋮⋮</span>
      <span class="tree-title">{{ t("panels.files") }}</span>
      <label class="dot-toggle" :title="t('tree.showDot')">
        <input
          type="checkbox"
          :checked="showDotFiles"
          @change="
            emit(
              'update:showDotFiles',
              ($event.target as HTMLInputElement).checked
            )
          "
        />
        {{ t("tree.showDotShort") }}
      </label>
      <button
        type="button"
        class="icon-btn"
        :title="t('tree.collapseAll')"
        @click="collapseAll"
      >
        −
      </button>
      <button
        type="button"
        class="icon-btn"
        :title="t('tree.expandTop')"
        @click="expandTop"
      >
        +
      </button>
      <button
        type="button"
        class="icon-btn hide-btn"
        :title="t('toolbar.toggleFiles')"
        @click="emit('hide')"
      >
        ◀
      </button>
    </div>
    <OverlayScroll content-class="tree-scroll">
      <div v-if="!tree.length" class="tree-empty">
        {{ compact ? t("zones.treeEmpty") : t("tree.empty") }}
      </div>
      <TreeNodeView
        v-for="n in tree"
        :key="n.path + n.type"
        :node="n"
        :depth="0"
        :current-path="currentPath"
        :expanded="expanded"
        :busy="busy"
        :status-label="statusLabel"
        :file-actions="fileActions"
        :t-compare="t('tree.compareDir')"
        :file-source="fileSource"
        :zone-id="zoneId"
        :hide-file-actions="fileSource === 'zone'"
        :hide-compare-dir="fileSource === 'zone'"
        @toggle="toggle"
        @open="emit('open', $event)"
        @action="onAction"
        @compare-dir="emit('compareDir', $event)"
        @file-context="onFileContext"
      />
    </OverlayScroll>
    <Teleport to="body">
      <div
        v-if="ctxMenu"
        class="tree-ctx-menu"
        :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
        @click.stop
        @contextmenu.prevent
      >
        <button
          type="button"
          class="tree-ctx-item"
          @pointerdown.stop.prevent="ctxAddToCompare"
          @click.stop.prevent="ctxAddToCompare"
        >
          {{ t("tree.addToCompare") }}
        </button>
        <button
          type="button"
          class="tree-ctx-item"
          @pointerdown.stop.prevent="ctxNewCompare"
          @click.stop.prevent="ctxNewCompare"
        >
          {{ t("tree.newCompare") }}
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.tree-toolbar-drag {
  cursor: grab;
  user-select: none;
}
.tree-toolbar-drag:active {
  cursor: grabbing;
}
.drag-grip {
  color: var(--muted);
  font-size: 0.65rem;
  letter-spacing: -0.1em;
  opacity: 0.7;
}
.file-tree {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  flex: 1;
}
.file-tree.compact {
  height: auto;
  flex: none;
}
.tree-toolbar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.45rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.75rem;
  color: var(--muted);
  background: var(--panel-header);
  flex-shrink: 0;
}
.tree-title {
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-right: 0.25rem;
  color: var(--muted);
}
.dot-toggle {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  cursor: pointer;
  margin-right: auto;
}
.icon-btn {
  background: transparent;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.1rem 0.35rem;
  font-size: 0.75rem;
  line-height: 1.2;
  min-width: 1.4rem;
}
.icon-btn:hover {
  background: color-mix(in srgb, var(--accent) 18%, var(--panel-header));
  color: var(--text);
}
.hide-btn {
  margin-left: 0.15rem;
}
/* Scrollport content padding only; overflow handled by OverlayScroll */
:deep(.tree-scroll) {
  padding: 0.15rem 0;
}
.file-tree.compact :deep(.os-root) {
  height: auto;
  max-height: 22rem;
  flex: none;
}
.tree-empty {
  color: var(--muted);
  padding: 0.75rem;
  font-size: 0.85rem;
}
</style>

<style>
.tree-ctx-menu {
  position: fixed;
  z-index: 200;
  min-width: 10rem;
  padding: 0.25rem;
  background: var(--panel, #1a2332);
  border: 1px solid var(--border, #2d3a4d);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}
.tree-ctx-item {
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--text, #e7ecf3);
  border: none;
  border-radius: 6px;
  padding: 0.4rem 0.6rem;
  font-size: 0.85rem;
  cursor: pointer;
}
.tree-ctx-item:hover {
  background: color-mix(in srgb, var(--accent, #3b82f6) 25%, transparent);
}
</style>

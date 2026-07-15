<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  buildTree,
  filterDotTree,
  topLevelDirPaths,
  type FileMeta,
} from "./buildTree";
import TreeNodeView from "./TreeNodeView.vue";

const props = defineProps<{
  files: FileMeta[];
  currentPath: string | null;
  showDotFiles: boolean;
  busy?: boolean;
}>();

const emit = defineEmits<{
  open: [path: string];
  action: [path: string, action: "add" | "delete" | "replace_all"];
  compareDir: [prefix: string];
  "update:showDotFiles": [value: boolean];
  hide: [];
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
</script>

<template>
  <div class="file-tree">
    <div class="tree-toolbar">
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
    <div class="tree-scroll">
      <div v-if="!tree.length" class="tree-empty">{{ t("tree.empty") }}</div>
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
        @toggle="toggle"
        @open="emit('open', $event)"
        @action="onAction"
        @compare-dir="emit('compareDir', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.file-tree {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  flex: 1;
}
.tree-toolbar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.45rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.75rem;
  color: var(--muted);
  background: #121a24;
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
  background: #243044;
  color: var(--text);
}
.hide-btn {
  margin-left: 0.15rem;
}
.tree-scroll {
  overflow: auto;
  flex: 1;
  min-height: 0;
  padding: 0.15rem 0;
}
.tree-empty {
  color: var(--muted);
  padding: 0.75rem;
  font-size: 0.85rem;
}
</style>

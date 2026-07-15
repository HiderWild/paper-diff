<script setup lang="ts">
/**
 * Compare-zones side panel: list of isolated zone snapshots.
 * Each zone expands into a FileTree; multiple can stay open.
 * No "active zone" concept — user picks files into the comparer.
 */
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import OverlayScroll from "../../components/OverlayScroll.vue";
import FileTree from "../tree/FileTree.vue";
import type { FileMeta } from "../tree/buildTree";
import type { Zone } from "../../shared/api";
import { getZoneTree } from "../../shared/api";

const props = defineProps<{
  projectId: string | null;
  zones: Zone[];
  busy?: boolean;
  showDotFiles: boolean;
  currentPath: string | null;
}>();

const emit = defineEmits<{
  "update:showDotFiles": [value: boolean];
  rename: [zoneId: string, name: string];
  delete: [zoneId: string];
  importZone: [];
  fromWork: [];
  openFile: [zoneId: string, path: string];
  addToCompare: [zoneId: string, path: string];
  newCompare: [zoneId: string, path: string];
  hide: [];
  titleDragStart: [e: DragEvent];
  titleDragEnd: [];
}>();

const { t } = useI18n();

/** zoneId -> expanded */
const openZones = ref<Record<string, boolean>>({});
/** zoneId -> loaded files for FileTree */
const trees = ref<Record<string, FileMeta[]>>({});
const treeError = ref<Record<string, string>>({});
const treeLoading = ref<Record<string, boolean>>({});

const sortedZones = computed(() =>
  [...props.zones].sort((a, b) =>
    (a.name || a.id).localeCompare(b.name || b.id)
  )
);

async function loadTree(zoneId: string, force = false) {
  if (!props.projectId) return;
  if (!force && trees.value[zoneId]?.length) return;
  treeLoading.value = { ...treeLoading.value, [zoneId]: true };
  treeError.value = { ...treeError.value, [zoneId]: "" };
  try {
    const res = await getZoneTree(props.projectId, zoneId);
    const files: FileMeta[] = (res.nodes || []).map((n) => ({
      path: n.path,
      status: "unknown",
      kind: n.kind || "text",
      is_dot: n.path.split("/").some((p) => p.startsWith(".")),
    }));
    if (!files.length && res.files?.length) {
      for (const p of res.files) {
        files.push({
          path: p,
          status: "unknown",
          kind: "text",
          is_dot: p.split("/").some((seg) => seg.startsWith(".")),
        });
      }
    }
    trees.value = { ...trees.value, [zoneId]: files };
  } catch (e) {
    treeError.value = {
      ...treeError.value,
      [zoneId]: e instanceof Error ? e.message : String(e),
    };
    trees.value = { ...trees.value, [zoneId]: [] };
  } finally {
    treeLoading.value = { ...treeLoading.value, [zoneId]: false };
  }
}

function toggleZone(zoneId: string) {
  const next = !openZones.value[zoneId];
  openZones.value = { ...openZones.value, [zoneId]: next };
  if (next) void loadTree(zoneId);
}

// When zones list refreshes (after import), reload open trees
watch(
  () => props.zones.map((z) => `${z.id}:${z.file_count ?? 0}`).join("|"),
  () => {
    for (const id of Object.keys(openZones.value)) {
      if (openZones.value[id]) void loadTree(id, true);
    }
  }
);

// Expand first zone once when list first appears
watch(
  () => props.zones.length,
  (n, prev) => {
    if (!n) return;
    if (Object.values(openZones.value).some(Boolean)) return;
    if (prev && prev > 0) return;
    const first = props.zones[0]?.id;
    if (first) {
      openZones.value = { ...openZones.value, [first]: true };
      void loadTree(first);
    }
  },
  { immediate: true }
);

function zoneFiles(zoneId: string): FileMeta[] {
  return trees.value[zoneId] || [];
}
</script>

<template>
  <div class="zone-explorer">
    <div
      class="panel-header side-header pane-drag-handle"
      draggable="true"
      :title="t('panels.dragToRearrange')"
      @dragstart="emit('titleDragStart', $event)"
      @dragend="emit('titleDragEnd')"
    >
      <span class="drag-grip" aria-hidden="true">⋮⋮</span>
      <span>{{ t("panels.zones") }}</span>
      <button
        type="button"
        class="header-hide"
        :title="t('toolbar.toggleFiles')"
        @click.stop="emit('hide')"
      >
        ◀
      </button>
    </div>

    <div class="zone-actions">
      <button
        type="button"
        class="secondary mini"
        :disabled="busy || !projectId"
        @click="emit('importZone')"
      >
        {{ t("importModal.open") }}
      </button>
      <button
        type="button"
        class="secondary mini"
        :disabled="busy || !projectId"
        @click="emit('fromWork')"
      >
        {{ t("zones.fromWork") }}
      </button>
    </div>

    <p v-if="!zones.length" class="muted empty-msg">{{ t("zones.empty") }}</p>

    <OverlayScroll v-else content-class="zone-scroll">
      <div
        v-for="z in sortedZones"
        :key="z.id"
        class="zone-block"
        :class="{ open: openZones[z.id] }"
      >
        <div class="zone-row">
          <button
            type="button"
            class="zone-toggle"
            :aria-expanded="!!openZones[z.id]"
            :disabled="busy"
            :title="t('zones.toggleTree')"
            @click="toggleZone(z.id)"
          >
            <span class="chevron" :class="{ open: openZones[z.id] }">
              <span class="chevron-tri" />
            </span>
            <span class="zone-name">{{ z.name }}</span>
            <span v-if="z.file_count != null" class="zone-meta">{{
              t("zones.fileCount", { n: z.file_count })
            }}</span>
          </button>
          <div class="zone-ops">
            <button
              type="button"
              class="mini secondary"
              :disabled="busy"
              @click.stop="emit('rename', z.id, z.name)"
            >
              {{ t("zones.rename") }}
            </button>
            <button
              type="button"
              class="mini secondary"
              :disabled="busy"
              @click.stop="emit('delete', z.id)"
            >
              {{ t("zones.delete") }}
            </button>
          </div>
        </div>

        <div v-if="openZones[z.id]" class="zone-tree-wrap">
          <p v-if="treeLoading[z.id]" class="muted tiny">
            {{ t("preview.loading") }}
          </p>
          <p v-else-if="treeError[z.id]" class="error tiny">
            {{ treeError[z.id] }}
          </p>
          <FileTree
            v-else
            :files="zoneFiles(z.id)"
            :current-path="currentPath"
            :show-dot-files="showDotFiles"
            :busy="busy"
            :draggable-title="false"
            file-source="zone"
            compact
            :hide-toolbar="true"
            :zone-id="z.id"
            @update:show-dot-files="emit('update:showDotFiles', $event)"
            @open="emit('openFile', z.id, $event)"
            @add-to-compare="emit('addToCompare', z.id, $event)"
            @new-compare="emit('newCompare', z.id, $event)"
          />
        </div>
      </div>
    </OverlayScroll>
  </div>
</template>

<style scoped>
.zone-explorer {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  flex: 1;
}
.drag-grip {
  color: var(--muted);
  font-size: 0.65rem;
  letter-spacing: -0.1em;
  opacity: 0.7;
}
.panel-header {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.35rem 0.45rem;
  border-bottom: 1px solid var(--border);
  font-size: 0.75rem;
  color: var(--muted);
  background: var(--panel-header);
  flex-shrink: 0;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.header-hide {
  margin-left: auto;
  background: transparent;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.1rem 0.35rem;
  cursor: pointer;
}
.zone-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  padding: 0.4rem 0.5rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.empty-msg {
  padding: 0.75rem;
  font-size: 0.85rem;
}
:deep(.zone-scroll) {
  padding: 0.15rem 0 0.5rem;
}
.zone-explorer > :deep(.os-root) {
  flex: 1 1 auto;
  min-height: 0;
}
.zone-block {
  border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
}
.zone-row {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.2rem 0.35rem 0.25rem;
}
.zone-toggle {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--text);
  border: none;
  border-radius: 4px;
  padding: 0.25rem 0.3rem;
  cursor: pointer;
  font-size: 0.82rem;
}
.zone-toggle:hover {
  background: color-mix(in srgb, var(--accent) 14%, transparent);
}
.zone-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.zone-meta {
  color: var(--muted);
  font-size: 0.7rem;
  flex-shrink: 0;
}
.zone-ops {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  padding-left: 1.4rem;
}
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
  border-style: solid;
  border-width: 4px 0 4px 6px;
  border-color: transparent transparent transparent currentColor;
  transition: transform 0.12s ease;
  transform-origin: 40% 50%;
}
.chevron.open .chevron-tri {
  transform: rotate(90deg);
}
.zone-tree-wrap {
  padding: 0 0 0.35rem;
  min-height: 2rem;
}
.zone-tree-wrap :deep(.file-tree) {
  height: auto;
  flex: none;
}
.zone-tree-wrap :deep(.os-root) {
  max-height: 22rem;
  height: auto;
}
.tiny {
  font-size: 0.75rem;
  padding: 0.35rem 0.75rem;
}
.error {
  color: var(--danger);
}
</style>

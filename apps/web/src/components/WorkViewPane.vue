<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import MonacoDiff from "../features/diff/MonacoDiff.vue";
import DocxPreview from "../features/preview/DocxPreview.vue";
import ImagePreview from "../features/preview/ImagePreview.vue";
import PdfPane from "../features/preview/PdfPane.vue";
import {
  toolAcceptsPath,
  type ViewInstance,
  type ToolKind,
} from "../stores/workspace";
import { useProjectStore } from "../stores/project";
import { workFileRawUrl, zoneFileRawUrl, getFilePair } from "../shared/api";

const props = defineProps<{
  view: ViewInstance;
  active: boolean;
}>();

const emit = defineEmits<{
  close: [];
  focus: [];
  titleDragStart: [e: DragEvent];
  titleDragEnd: [];
  dropTool: [kind: ToolKind, e: DragEvent];
  dropFile: [path: string];
  invalidDrop: [message: string];
}>();

const { t } = useI18n();
const project = useProjectStore();

const left = ref("");
const right = ref("");
const loading = ref(false);
const error = ref("");
const imageUrls = ref<{ work: string; zone?: string | null } | null>(null);
const rawUrl = ref<string | null>(null);
const isLegacyDoc = ref(false);
const dropOver = ref(false);

const kindLabel = computed(() => t(`tools.${props.view.kind}`));

const title = computed(() => {
  if (props.view.path) return `${kindLabel.value} · ${props.view.path}`;
  return `${kindLabel.value} · ${t("tools.empty")}`;
});

async function loadBoundPath(path: string | null) {
  left.value = "";
  right.value = "";
  error.value = "";
  imageUrls.value = null;
  rawUrl.value = null;
  isLegacyDoc.value = false;
  if (!path || !project.projectId) return;
  loading.value = true;
  try {
    const pid = project.projectId;
    if (props.view.kind === "pdf") {
      rawUrl.value = workFileRawUrl(pid, path) + `&t=${Date.now()}`;
      return;
    }
    if (props.view.kind === "word") {
      isLegacyDoc.value = /\.doc$/i.test(path) && !/\.docx$/i.test(path);
      rawUrl.value = workFileRawUrl(pid, path) + `&t=${Date.now()}`;
      return;
    }
    if (props.view.kind === "editor") {
      // prefer text load via file-pair left; images use image panel in openFile but editor rejects them
      if (/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(path)) {
        imageUrls.value = {
          work: workFileRawUrl(pid, path),
          zone: project.activeZoneId
            ? zoneFileRawUrl(pid, project.activeZoneId, path)
            : null,
        };
        return;
      }
      const pair = await getFilePair(pid, path);
      left.value = pair.left?.content ?? pair.merged.content;
      right.value = "";
      return;
    }
    // comparer
    const pair = await getFilePair(pid, path);
    left.value = pair.left?.content ?? pair.merged.content;
    right.value = pair.right?.content ?? pair.revised.content;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.view.path, props.view.kind, project.activeZoneId] as const,
  ([path]) => {
    void loadBoundPath(path);
  },
  { immediate: true }
);

function onDragOver(e: DragEvent) {
  e.preventDefault();
  dropOver.value = true;
  if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
}

function onDragLeave() {
  dropOver.value = false;
}

function onDrop(e: DragEvent) {
  e.preventDefault();
  dropOver.value = false;
  const tool = e.dataTransfer?.getData("application/x-paper-diff-tool");
  if (tool) {
    emit("dropTool", tool as ToolKind, e);
    return;
  }
  const path =
    e.dataTransfer?.getData("application/x-paper-diff-path") ||
    e.dataTransfer?.getData("text/plain");
  if (!path || path.startsWith("tool:")) return;
  if (!toolAcceptsPath(props.view.kind, path)) {
    emit(
      "invalidDrop",
      t("tools.unsupportedFile", {
        tool: kindLabel.value,
        file: path,
      })
    );
    return;
  }
  emit("dropFile", path);
}
</script>

<template>
  <section
    class="work-view-pane"
    :class="{ active, 'drop-over': dropOver }"
    @click="emit('focus')"
    @dragenter.prevent="onDragOver"
    @dragover.prevent="onDragOver"
    @dragleave="onDragLeave"
    @drop.prevent="onDrop"
  >
    <div
      class="panel-header side-header pane-drag-handle"
      draggable="true"
      @dragstart="emit('titleDragStart', $event)"
      @dragend="emit('titleDragEnd')"
    >
      <span class="drag-grip" aria-hidden="true">⋮⋮</span>
      <span class="view-title">{{ title }}</span>
      <button
        type="button"
        class="header-hide"
        :title="t('tools.close')"
        @click.stop="emit('close')"
      >
        ×
      </button>
    </div>
    <div class="view-body">
      <div v-if="loading" class="empty">{{ t("preview.loading") }}</div>
      <div v-else-if="error" class="empty error">{{ error }}</div>
      <div v-else-if="!view.path" class="empty drop-hint">
        {{ t("tools.dropHint", { tool: kindLabel }) }}
      </div>
      <template v-else>
        <PdfPane v-if="view.kind === 'pdf'" :url="rawUrl" />
        <DocxPreview
          v-else-if="view.kind === 'word'"
          :url="rawUrl"
          :legacy-doc="isLegacyDoc"
        />
        <ImagePreview
          v-else-if="imageUrls"
          :path="view.path || ''"
          :work-url="imageUrls.work"
          :zone-url="imageUrls.zone"
        />
        <MonacoDiff
          v-else-if="view.kind === 'comparer'"
          :key="view.id + (view.path || '')"
          :path="view.path || ''"
          :left="left"
          :right="right"
        />
        <!-- single editor: only left content, empty right -->
        <MonacoDiff
          v-else-if="view.kind === 'editor'"
          :key="view.id + '-ed-' + (view.path || '')"
          :path="view.path || ''"
          :left="left"
          :right="left"
        />
      </template>
    </div>
  </section>
</template>

<style scoped>
.work-view-pane {
  display: flex;
  flex-direction: column;
  min-width: 180px;
  min-height: 0;
  flex: 1 1 0;
  border: 1px solid var(--border);
  background: var(--panel);
  overflow: hidden;
}
.work-view-pane.active {
  border-color: #3b82f6;
}
.work-view-pane.drop-over {
  outline: 2px dashed #3b82f6;
  outline-offset: -3px;
}
.view-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.8rem;
}
.view-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.empty {
  color: var(--muted);
  padding: 1rem;
  font-size: 0.85rem;
}
.empty.error {
  color: #fecaca;
}
.drop-hint {
  border: 1px dashed var(--border);
  margin: 1rem;
  border-radius: 8px;
  text-align: center;
  padding: 2rem 1rem;
}
.pane-drag-handle {
  cursor: grab;
}
.drag-grip {
  opacity: 0.7;
  font-size: 0.65rem;
}
</style>

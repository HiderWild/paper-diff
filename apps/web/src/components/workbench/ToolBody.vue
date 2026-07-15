<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import MonacoDiff from "../../features/diff/MonacoDiff.vue";
import DocxPreview from "../../features/preview/DocxPreview.vue";
import ImagePreview from "../../features/preview/ImagePreview.vue";
import PdfPane from "../../features/preview/PdfPane.vue";
import type { ViewTab } from "../../stores/workbench";
import { useProjectStore } from "../../stores/project";
import { workFileRawUrl, zoneFileRawUrl, getFilePair } from "../../shared/api";

const props = defineProps<{
  tab: ViewTab;
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

async function loadBoundPath(path: string | null) {
  left.value = "";
  right.value = "";
  error.value = "";
  imageUrls.value = null;
  rawUrl.value = null;
  isLegacyDoc.value = false;
  if (props.tab.kind === "output") return;
  if (!path || !project.projectId) return;
  loading.value = true;
  try {
    const pid = project.projectId;
    if (props.tab.kind === "pdf") {
      rawUrl.value = workFileRawUrl(pid, path) + `&t=${Date.now()}`;
      return;
    }
    if (props.tab.kind === "word") {
      isLegacyDoc.value = /\.doc$/i.test(path) && !/\.docx$/i.test(path);
      rawUrl.value = workFileRawUrl(pid, path) + `&t=${Date.now()}`;
      return;
    }
    if (props.tab.kind === "editor") {
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
  () => [props.tab.path, props.tab.kind, project.activeZoneId] as const,
  ([path]) => {
    void loadBoundPath(path);
  },
  { immediate: true }
);
</script>

<template>
  <div class="tool-body">
    <div v-if="tab.kind === 'output'" class="log-box flex-log output-body">
      {{ project.logText || t("panels.compileLog") }}
    </div>
    <template v-else>
      <div v-if="loading" class="empty">{{ t("preview.loading") }}</div>
      <div v-else-if="error" class="empty error">{{ error }}</div>
      <div v-else-if="!tab.path" class="empty drop-hint">
        {{ t("tools.dropHint", { tool: t(`tools.${tab.kind}`) }) }}
      </div>
      <template v-else>
        <PdfPane v-if="tab.kind === 'pdf'" :url="rawUrl" />
        <DocxPreview
          v-else-if="tab.kind === 'word'"
          :url="rawUrl"
          :legacy-doc="isLegacyDoc"
        />
        <ImagePreview
          v-else-if="imageUrls"
          :path="tab.path || ''"
          :work-url="imageUrls.work"
          :zone-url="imageUrls.zone"
        />
        <MonacoDiff
          v-else-if="tab.kind === 'comparer'"
          :key="tab.id + (tab.path || '')"
          :path="tab.path || ''"
          :left="left"
          :right="right"
        />
        <MonacoDiff
          v-else-if="tab.kind === 'editor'"
          :key="tab.id + '-ed-' + (tab.path || '')"
          :path="tab.path || ''"
          :left="left"
          :right="left"
        />
      </template>
    </template>
  </div>
</template>

<style scoped>
.tool-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
.output-body {
  flex: 1;
  max-height: none;
  border-top: none;
}
</style>

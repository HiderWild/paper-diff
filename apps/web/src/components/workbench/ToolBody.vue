<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { storeToRefs } from "pinia";
import MonacoDiff from "../../features/diff/MonacoDiff.vue";
import DocxPreview from "../../features/preview/DocxPreview.vue";
import ImagePreview from "../../features/preview/ImagePreview.vue";
import PdfPane from "../../features/preview/PdfPane.vue";
import type { DiffUnit } from "../../features/diff/sentenceMapper";
import type { ViewTab } from "../../stores/workbench";
import { useProjectStore } from "../../stores/project";
import { useSettingsStore } from "../../stores/settings";
import {
  workFileRawUrl,
  zoneFileRawUrl,
  getFilePair,
  getZoneFileText,
  getWorkFileText,
  gitShow,
} from "../../shared/api";
import ComparerChrome from "./ComparerChrome.vue";
import {
  useCompareTargetStore,
  type CompareTarget,
} from "../../stores/compareTarget";

const props = defineProps<{
  tab: ViewTab;
  active: boolean;
}>();

const { t } = useI18n();
const project = useProjectStore();
const settings = useSettingsStore();
const compareTarget = useCompareTargetStore();
const { monacoTheme } = storeToRefs(settings);
const { sidesSwapped } = storeToRefs(project);
const targetTick = ref(0);

const left = ref("");
const right = ref("");
const loading = ref(false);
const error = ref("");
const imageUrls = ref<{ work: string; zone?: string | null } | null>(null);
const rawUrl = ref<string | null>(null);
const isLegacyDoc = ref(false);
const units = ref<DiffUnit[]>([]);
const diffRef = ref<InstanceType<typeof MonacoDiff> | null>(null);

const editableLeft = computed(
  () => props.tab.kind === "editor" || props.tab.kind === "comparer"
);
const singlePane = computed(() => props.tab.kind === "editor");

const displayLeft = computed(() => {
  if (props.tab.kind !== "comparer") return left.value;
  return sidesSwapped.value ? right.value : left.value;
});
const displayRight = computed(() => {
  if (props.tab.kind !== "comparer") return right.value;
  return sidesSwapped.value ? left.value : right.value;
});

async function loadBoundPath(path: string | null) {
  left.value = "";
  right.value = "";
  error.value = "";
  imageUrls.value = null;
  rawUrl.value = null;
  isLegacyDoc.value = false;
  units.value = [];
  if (props.tab.kind === "output") return;
  if (!path || !project.projectId) return;
  loading.value = true;
  try {
    const pid = project.projectId;
    if (props.tab.kind === "pdf") {
      const base = workFileRawUrl(pid, path);
      const sep = base.includes("?") ? "&" : "?";
      rawUrl.value = `${base}${sep}t=${Date.now()}`;
      return;
    }
    if (props.tab.kind === "word") {
      isLegacyDoc.value = /\.doc$/i.test(path) && !/\.docx$/i.test(path);
      const base = workFileRawUrl(pid, path);
      const sep = base.includes("?") ? "&" : "?";
      rawUrl.value = `${base}${sep}t=${Date.now()}`;
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
      const content =
        project.localBuffers[path] ??
        pair.left?.content ??
        pair.merged.content;
      left.value = content;
      right.value = content;
      if (props.active) {
        project.pair = pair;
        project.currentPath = path;
      }
      return;
    }
    // comparer: left=work path, right=remembered target (zone/git)
    let workContent = "";
    try {
      const wf = await getWorkFileText(pid, path);
      workContent = wf.content;
    } catch {
      const pair0 = await getFilePair(pid, path);
      workContent = pair0.left?.content ?? pair0.merged.content;
    }
    left.value = project.localBuffers[path] ?? workContent;

    // Per-workPath override, else project default (path synced to work), else active zone
    const mem =
      compareTarget.resolveForWork(project.projectId, path) ||
      (project.activeZoneId
        ? {
            kind: "zone" as const,
            zoneId: project.activeZoneId,
            path,
          }
        : null);

    if (mem?.kind === "git") {
      const shown = await gitShow(pid, mem.ref, mem.path || path);
      right.value = shown.content ?? "";
    } else if (mem?.kind === "zone") {
      try {
        const zf = await getZoneFileText(pid, mem.zoneId, mem.path || path);
        right.value = zf.content;
      } catch {
        right.value = "";
      }
    } else {
      const pair = await getFilePair(pid, path);
      right.value = pair.right?.content ?? pair.revised.content ?? "";
    }

    // Keep pair meta for accept revision when same-path zone compare
    try {
      const pair = await getFilePair(pid, path);
      if (props.active) {
        project.pair = pair;
        project.currentPath = path;
        project.units = [];
      }
    } catch {
      if (props.active) project.currentPath = path;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

watch(
  () =>
    [
      props.tab.path,
      props.tab.kind,
      project.activeZoneId,
      props.active,
      targetTick.value,
    ] as const,
  ([path]) => {
    void loadBoundPath(path);
  },
  { immediate: true }
);

function onTargetChanged(_t: CompareTarget) {
  targetTick.value++;
}

async function onPullUnit(u: DiffUnit) {
  // Always pass visible buffers so git / non-active zone pulls use true source.
  // left = work, right = compare target (even when display sides are swapped).
  const path = props.tab.path;
  if (!path) return;
  const content = await project.doAccept(u, {
    workPath: path,
    leftTextFull: left.value,
    rightTextFull: right.value,
  });
  onAfterMutation(content ?? null);
}

function onLeftChange(content: string) {
  if (!props.tab.path || !editableLeft.value) return;
  // when swapped, displayed left is zone (readonly) — only work edits mark dirty
  // editable is always work model which we bind as original; display swap is visual only
  // For swapped display we still edit `original` which maps to displayLeft; need care:
  // We bind Monaco left=displayLeft. When swapped, displayLeft is zone → must not edit zone.
  // Fix: when swapped, disable left edit OR map changes to work via inverted content.
  if (props.tab.kind === "comparer" && sidesSwapped.value) {
    // user is seeing zone on left — we set editableLeft false when swapped in computed below
    return;
  }
  project.markDirty(props.tab.path, content);
  left.value = content;
}

const effectiveEditable = computed(() => {
  if (!editableLeft.value) return false;
  if (props.tab.kind === "comparer" && sidesSwapped.value) return false;
  return true;
});

function onUnits(u: DiffUnit[]) {
  units.value = u;
  if (props.active) project.units = u;
}

function onAfterMutation(content: string | null) {
  if (content != null && props.tab.path) {
    left.value = content;
    project.clearDirty(props.tab.path);
    // Remount diff for reliable buffer sync after pull (swap-safe).
    targetTick.value++;
  }
}
</script>

<template>
  <div class="tool-body">
    <div v-if="tab.kind === 'output'" class="log-box flex-log output-body">
      {{ project.logText || t("panels.compileLog") }}
    </div>
    <template v-else>
      <ComparerChrome
        v-if="tab.kind === 'comparer' && active && tab.path"
        :path="tab.path"
        :units="units"
        :left-text="left"
        :right-text="right"
        @after-mutation="onAfterMutation"
        @target-changed="onTargetChanged"
      />
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
          v-else-if="tab.kind === 'comparer' || tab.kind === 'editor'"
          ref="diffRef"
          :key="
            tab.id +
            (tab.path || '') +
            (sidesSwapped ? '-s' : '') +
            '-t' +
            targetTick
          "
          :path="tab.path || ''"
          :left="displayLeft"
          :right="displayRight"
          :editable-left="effectiveEditable"
          :single-pane="singlePane"
          :monaco-theme="monacoTheme"
          :show-gutter-actions="tab.kind === 'comparer'"
          @units="onUnits"
          @left-change="onLeftChange"
          @pull-unit="onPullUnit"
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
  color: var(--danger);
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

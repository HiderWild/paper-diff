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

const emit = defineEmits<{
  /** Jump activity bar to project explorer */
  pickProject: [];
  /** Jump activity bar to zones panel */
  pickZone: [];
  /** Open git commit/file picker modal */
  pickGit: [];
}>();

const { t } = useI18n();
const project = useProjectStore();
const settings = useSettingsStore();
const compareTarget = useCompareTargetStore();
const { monacoTheme, wordWrap, wordHoverAccept } = storeToRefs(settings);
const { sidesSwapped, zones } = storeToRefs(project);
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
/** Editor tool is always single-pane; comparer becomes dual only when both sides ready. */
const singlePane = computed(() => {
  if (props.tab.kind === "editor") return true;
  if (props.tab.kind === "comparer") return !compareReady.value;
  return false;
});

/** True once we intentionally loaded a right-hand target (even if empty file). */
const rightResolved = ref(false);

/** Work path + resolved compare target — show real red/green diff + arrows. */
const compareReady = computed(() => {
  if (props.tab.kind !== "comparer") return true;
  return !!(props.tab.path && rightResolved.value);
});

/** Either side present — one-sided editor/viewer or empty dual drop. */
const hasWorkSide = computed(
  () => props.tab.kind === "comparer" && !!props.tab.path
);
const hasCompareSide = computed(
  () => props.tab.kind === "comparer" && rightResolved.value
);
const hasAnySide = computed(
  () => hasWorkSide.value || hasCompareSide.value
);

/** Resolved compare target for labels (zone name / git short hash). */
const resolvedTarget = computed<CompareTarget | null>(() => {
  if (props.tab.kind !== "comparer") return null;
  if (props.tab.path) {
    return compareTarget.resolveForWork(project.projectId, props.tab.path);
  }
  return compareTarget.getForProject(project.projectId);
});

const projectSideLabel = computed(() => {
  if (props.tab.path) {
    return `${t("comparer.fromProject")} · ${props.tab.path}`;
  }
  return t("comparer.fromProject");
});

const compareSideLabel = computed(() => {
  const mem = resolvedTarget.value;
  if (!mem) return t("comparer.emptyCompareHint");
  if (mem.kind === "zone") {
    const z = zones.value.find((x) => x.id === mem.zoneId);
    const name = z?.name || mem.zoneId.slice(0, 8);
    return `${t("comparer.fromZone")}「${name}」 · ${mem.path}`;
  }
  const short = mem.ref.slice(0, 10);
  return `${t("comparer.fromGit", { ref: short })} · ${mem.path}`;
});

const displayLeft = computed(() => {
  if (props.tab.kind !== "comparer") return left.value;
  if (!compareReady.value) return left.value;
  return sidesSwapped.value ? right.value : left.value;
});
const displayRight = computed(() => {
  if (props.tab.kind !== "comparer") return right.value;
  if (!compareReady.value) return right.value;
  return sidesSwapped.value ? left.value : right.value;
});

async function loadBoundPath(path: string | null) {
  left.value = "";
  right.value = "";
  rightResolved.value = false;
  error.value = "";
  imageUrls.value = null;
  rawUrl.value = null;
  isLegacyDoc.value = false;
  units.value = [];
  if (props.tab.kind === "output") return;
  if (!project.projectId) return;
  // Non-comparer tools need a bound path
  if (!path && props.tab.kind !== "comparer") return;
  loading.value = true;
  try {
    const pid = project.projectId;
    if (props.tab.kind === "pdf") {
      if (!path) return;
      const base = workFileRawUrl(pid, path);
      const sep = base.includes("?") ? "&" : "?";
      rawUrl.value = `${base}${sep}t=${Date.now()}`;
      return;
    }
    if (props.tab.kind === "word") {
      if (!path) return;
      isLegacyDoc.value = /\.doc$/i.test(path) && !/\.docx$/i.test(path);
      const base = workFileRawUrl(pid, path);
      const sep = base.includes("?") ? "&" : "?";
      rawUrl.value = `${base}${sep}t=${Date.now()}`;
      return;
    }
    if (props.tab.kind === "editor") {
      if (!path) return;
      if (/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(path)) {
        imageUrls.value = {
          work: workFileRawUrl(pid, path),
          zone: null,
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
    // comparer: left=work path (optional), right=remembered target (zone/git, optional)
    // One-sided is allowed: show that side as editor/viewer until both are ready.
    if (path) {
      let workContent = "";
      try {
        const wf = await getWorkFileText(pid, path);
        workContent = wf.content;
      } catch {
        try {
          const pair0 = await getFilePair(pid, path);
          workContent = pair0.left?.content ?? pair0.merged.content;
        } catch {
          workContent = "";
        }
      }
      left.value = project.localBuffers[path] ?? workContent;
    } else {
      left.value = "";
    }

    // Only use remembered compare target (file / project default / session).
    // Do NOT auto-seed active zone — empty compare side is intentional until user drops / "Add to compare" / vs…
    const mem: CompareTarget | null = path
      ? compareTarget.resolveForWork(project.projectId, path)
      : compareTarget.getForProject(project.projectId);

    if (mem?.kind === "git") {
      const showPath = mem.path || path;
      if (showPath) {
        try {
          const shown = await gitShow(pid, mem.ref, showPath);
          right.value = shown.content ?? "";
          rightResolved.value = true;
        } catch {
          right.value = "";
          rightResolved.value = false;
        }
      }
    } else if (mem?.kind === "zone") {
      const zPath = mem.path || path;
      if (zPath) {
        try {
          const zf = await getZoneFileText(pid, mem.zoneId, zPath);
          right.value = zf.content;
          rightResolved.value = true;
        } catch {
          right.value = "";
          rightResolved.value = false;
        }
      }
    } else {
      right.value = "";
      rightResolved.value = false;
    }

    // Keep pair meta for accept revision when same-path zone compare
    if (path) {
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
      props.active,
      targetTick.value,
      compareTarget.session,
      compareTarget.memory,
    ] as const,
  ([path]) => {
    void loadBoundPath(path);
  },
  { immediate: true, deep: true }
);

function onTargetChanged(_t: CompareTarget) {
  targetTick.value++;
}

async function onPullUnit(u: DiffUnit) {
  // Always pass visible buffers so git / non-active zone pulls use true source.
  // left = work, right = compare target (even when display sides are swapped).
  const path = props.tab.path;
  if (!path) return;
  try {
    const content = await project.doAccept(u, {
      workPath: path,
      leftTextFull: left.value,
      rightTextFull: right.value,
    });
    onAfterMutation(content ?? null);
    if (content != null && (u.granularity === "word" || u.granularity === "sentence")) {
      const { useWorkbenchStore } = await import("../../stores/workbench");
      useWorkbenchStore().toast(t("hoverAccept.appliedToast"), "info");
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
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
        v-if="tab.kind === 'comparer' && active && hasAnySide"
        :path="tab.path"
        :units="compareReady ? units : []"
        :left-text="left"
        :right-text="right"
        :compare-ready="compareReady"
        @after-mutation="onAfterMutation"
        @target-changed="onTargetChanged"
      />
      <div v-if="loading" class="empty">{{ t("preview.loading") }}</div>
      <div v-else-if="error" class="empty error">{{ error }}</div>
      <!-- Comparer empty / one-sided shells -->
      <div
        v-else-if="tab.kind === 'comparer' && !compareReady"
        class="one-sided"
        :class="{ swapped: sidesSwapped }"
      >
        <div class="side work-side">
          <div class="side-label">{{ projectSideLabel }}</div>
          <MonacoDiff
            v-if="hasWorkSide"
            :key="tab.id + '-work-' + (tab.path || '') + '-t' + targetTick"
            :path="tab.path || ''"
            :left="left"
            :right="left"
            :editable-left="true"
            :single-pane="true"
            :monaco-theme="monacoTheme"
            :word-wrap="wordWrap"
            :show-gutter-actions="false"
            @left-change="onLeftChange"
          />
          <div v-else class="empty drop-hint side-hint pick-panel">
            <p class="pick-hint">{{ t("comparer.emptyProjectHint") }}</p>
            <button
              type="button"
              class="pick-btn primary"
              @click="emit('pickProject')"
            >
              {{ t("comparer.pickProject") }}
            </button>
            <p class="muted tiny">{{ t("comparer.dropWork") }}</p>
          </div>
        </div>
        <div class="side compare-side">
          <div class="side-label">{{ compareSideLabel }}</div>
          <MonacoDiff
            v-if="hasCompareSide"
            :key="tab.id + '-cmp-' + targetTick"
            :path="tab.path || 'compare'"
            :left="right"
            :right="right"
            :editable-left="false"
            :single-pane="true"
            :monaco-theme="monacoTheme"
            :word-wrap="wordWrap"
            :show-gutter-actions="false"
          />
          <div v-else class="empty drop-hint side-hint pick-panel">
            <p class="pick-hint">{{ t("comparer.emptyCompareHint") }}</p>
            <div class="pick-row">
              <button
                type="button"
                class="pick-btn"
                @click="emit('pickZone')"
              >
                {{ t("comparer.pickFromZone") }}
              </button>
              <button
                type="button"
                class="pick-btn"
                @click="emit('pickGit')"
              >
                {{ t("comparer.pickFromGit") }}
              </button>
            </div>
            <p class="muted tiny">{{ t("comparer.dropCompare") }}</p>
          </div>
        </div>
      </div>
      <!-- Non-comparer empty -->
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
            targetTick +
            (compareReady ? '-r' : '-w')
          "
          :path="tab.path || ''"
          :left="displayLeft"
          :right="displayRight"
          :editable-left="effectiveEditable"
          :single-pane="singlePane"
          :monaco-theme="monacoTheme"
          :word-wrap="wordWrap"
          :show-gutter-actions="tab.kind === 'comparer' && compareReady"
          :sides-swapped="tab.kind === 'comparer' && sidesSwapped"
          :enable-word-hover="
            tab.kind === 'comparer' && compareReady && wordHoverAccept
          "
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
/* One-sided / empty comparer: project | compare columns (swap flips order) */
.one-sided {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: row;
}
.one-sided.swapped {
  flex-direction: row-reverse;
}
.one-sided .side {
  flex: 1 1 50%;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
}
.one-sided .side:last-child,
.one-sided.swapped .side:first-child {
  border-right: none;
}
.one-sided.swapped .side:last-child {
  border-right: 1px solid var(--border);
}
.one-sided.swapped .side:first-child {
  border-right: none;
}
.side-label {
  flex-shrink: 0;
  padding: 0.2rem 0.55rem;
  font-size: 0.7rem;
  color: var(--muted);
  background: var(--panel-header);
  border-bottom: 1px solid var(--border);
}
.side-hint {
  flex: 1;
  margin: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pick-panel {
  flex-direction: column;
  gap: 0.75rem;
  text-align: center;
}
.pick-hint {
  margin: 0;
  max-width: 16rem;
  line-height: 1.4;
}
.pick-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
}
.pick-btn {
  min-width: 9rem;
  padding: 0.55rem 0.9rem;
  font-size: 0.85rem;
  background: var(--secondary-btn);
  color: var(--text);
}
.pick-btn.primary {
  background: var(--accent);
  color: #fff;
  min-width: 11rem;
  font-size: 0.9rem;
  padding: 0.7rem 1.1rem;
}
.pick-btn:hover:not(:disabled) {
  filter: brightness(1.08);
}
.tiny {
  font-size: 0.72rem;
  max-width: 18rem;
  margin: 0;
}
.one-sided :deep(.diff-wrap) {
  flex: 1 1 auto;
  min-height: 0;
}
</style>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { storeToRefs } from "pinia";
import type { DiffUnit } from "../../features/diff/sentenceMapper";
import { useProjectStore } from "../../stores/project";
import {
  useCompareTargetStore,
  type CompareTarget,
} from "../../stores/compareTarget";

const props = withDefaults(
  defineProps<{
    /** Work (project) path; null when only compare side is set */
    path: string | null;
    units: DiffUnit[];
    /** Visible work-side full text (true left buffer) */
    leftText?: string;
    /** Visible compare-side full text (true right buffer; git/zone) */
    rightText?: string;
    /** When false, hide accept-all (both sides not ready) */
    compareReady?: boolean;
  }>(),
  { compareReady: true }
);

const emit = defineEmits<{
  acceptUnit: [unit: DiffUnit];
  acceptAll: [];
  afterMutation: [leftContent: string | null];
  targetChanged: [target: CompareTarget];
}>();

const { t } = useI18n();
const store = useProjectStore();
const targets = useCompareTargetStore();
const { sidesSwapped, zones, busy, pair, projectId, gitCommits } =
  storeToRefs(store);

const targetKind = ref<"zone" | "git">("zone");
const zoneId = ref("");
const zonePath = ref(props.path || "");
const gitRef = ref("");
const gitPath = ref(props.path || "");
const pickerOpen = ref(false);

watch(
  () => [props.path, projectId.value, zones.value] as const,
  ([path]) => {
    const workPath = path || "";
    // Prefer per-work-path memory; no global active zone fallback.
    const mem = workPath
      ? targets.resolveForWork(projectId.value, workPath)
      : targets.getForProject(projectId.value);
    if (mem) {
      if (mem.kind === "zone") {
        targetKind.value = "zone";
        zoneId.value = mem.zoneId;
        zonePath.value = mem.path || workPath;
      } else {
        targetKind.value = "git";
        gitRef.value = mem.ref;
        gitPath.value = mem.path || workPath;
      }
    } else {
      targetKind.value = "zone";
      zoneId.value = zones.value[0]?.id || "";
      zonePath.value = workPath;
      gitPath.value = workPath;
    }
    // Opening a new work path: seed fields unless file-scoped override already set them.
    if (workPath) {
      const scope = targets.getMemoryScope(projectId.value, workPath);
      if (scope !== "file") {
        zonePath.value = workPath;
        gitPath.value = workPath;
      }
    }
  },
  { immediate: true }
);

const memoryScope = computed(() =>
  props.path
    ? targets.getMemoryScope(projectId.value, props.path)
    : targets.getMemoryScope(projectId.value)
);

const memoryBadge = computed(() => {
  if (memoryScope.value === "file") return t("comparer.rememberedFile");
  if (memoryScope.value === "project") return t("comparer.rememberedProject");
  return "";
});

const targetLabel = computed(() => {
  // Prefer memory for picker chrome; do not invent readiness here — body owns load state.
  const cur =
    currentTarget() ||
    (props.path
      ? targets.resolveForWork(projectId.value, props.path)
      : targets.getForProject(projectId.value));
  if (!cur) return t("comparer.emptyCompareHint");
  if (cur.kind === "zone") {
    const z = zones.value.find((x) => x.id === cur.zoneId);
    const name = z?.name || cur.zoneId.slice(0, 8);
    return `${t("comparer.fromZone")}「${name}」 · ${cur.path}`;
  }
  return `${t("comparer.fromGit", { ref: cur.ref.slice(0, 10) })} · ${cur.path}`;
});

const projectLabel = computed(() => {
  if (props.path) return `${t("comparer.fromProject")} · ${props.path}`;
  return t("comparer.fromProject");
});

const title = computed(() => {
  // Only claim dual-side title when compareReady; avoid ghost "vs" after failed reload
  if (!props.compareReady) {
    if (props.path) return projectLabel.value;
    return t("panels.comparer");
  }
  const left = sidesSwapped.value ? targetLabel.value : projectLabel.value;
  const right = sidesSwapped.value ? projectLabel.value : targetLabel.value;
  return t("panels.diffHeaderWith", { left, right });
});

function currentTarget(): CompareTarget | null {
  if (targetKind.value === "zone") {
    if (!zoneId.value) return null;
    return {
      kind: "zone",
      zoneId: zoneId.value,
      path: zonePath.value || props.path || "",
    };
  }
  if (!gitRef.value) return null;
  return {
    kind: "git",
    ref: gitRef.value,
    path: gitPath.value || props.path || "",
  };
}

function applyTarget() {
  const t0 = currentTarget();
  if (!t0 || !t0.path) return;
  // Persist as both project default and per-workPath override when work path known
  targets.setForProject(projectId.value, t0, props.path || undefined);
  emit("targetChanged", t0);
  pickerOpen.value = false;
}

async function onAcceptAll() {
  if (!props.path) return;
  if (store.isDirty(props.path)) {
    if (!confirm(t("tools.dirtyAcceptConfirm"))) return;
  }
  // Pass visible right buffer so git/non-active targets write true compare content.
  const content = await store.doAcceptAll({
    workPath: props.path,
    leftTextFull: props.leftText,
    rightTextFull: props.rightText,
  });
  emit("acceptAll");
  emit("afterMutation", content ?? null);
}

async function ensureGitLog() {
  if (!projectId.value) return;
  if (gitCommits.value.length) return;
  await store.refreshGitLog();
}

watch(pickerOpen, (v) => {
  if (v) void ensureGitLog();
});
</script>

<template>
  <div class="cmp-chrome">
    <div class="cmp-title-row">
      <span class="cmp-title">{{ title }}</span>
      <span class="cmp-path muted">{{ path || targetLabel }}</span>
      <span v-if="memoryBadge" class="mem-badge muted" :title="memoryBadge">{{
        memoryBadge
      }}</span>
      <button
        type="button"
        class="mini secondary"
        :title="t('comparer.pickTarget')"
        @click="pickerOpen = !pickerOpen"
      >
        {{ t("comparer.vs") }}…
      </button>
      <button
        type="button"
        class="mini secondary"
        :class="{ 'active-toggle': sidesSwapped }"
        :title="t('panels.swapSides')"
        :disabled="busy"
        @click="store.toggleSidesSwapped()"
      >
        ⇄
      </button>
      <button
        v-if="compareReady"
        type="button"
        class="mini"
        :disabled="busy || (!pair && rightText == null)"
        @click="onAcceptAll"
      >
        {{ t("toolbar.acceptFile") }}
      </button>
    </div>

    <div v-if="pickerOpen" class="target-picker">
      <div class="mode-row">
        <button
          type="button"
          class="method-chip"
          :class="{ active: targetKind === 'zone' }"
          @click="targetKind = 'zone'"
        >
          {{ t("comparer.sourceZone") }}
        </button>
        <button
          type="button"
          class="method-chip"
          :class="{ active: targetKind === 'git' }"
          @click="targetKind = 'git'"
        >
          {{ t("comparer.sourceGit") }}
        </button>
      </div>
      <template v-if="targetKind === 'zone'">
        <label class="field">
          {{ t("panels.zones") }}
          <select v-model="zoneId">
            <option value="" disabled>{{ t("comparer.pickZone") }}</option>
            <option v-for="z in zones" :key="z.id" :value="z.id">
              {{ z.name }}
            </option>
          </select>
        </label>
        <label class="field">
          {{ t("comparer.zonePath") }}
          <input v-model="zonePath" type="text" />
        </label>
      </template>
      <template v-else>
        <label class="field">
          {{ t("comparer.gitRef") }}
          <select v-model="gitRef">
            <option value="" disabled>{{ t("comparer.pickCommit") }}</option>
            <option
              v-for="c in gitCommits"
              :key="c.sha || c.short"
              :value="c.sha || c.short"
            >
              {{ (c.short || c.sha || "").slice(0, 10) }} ·
              {{ (c.subject || "").slice(0, 40) }}
            </option>
          </select>
        </label>
        <label class="field">
          {{ t("comparer.gitPath") }}
          <input v-model="gitPath" type="text" />
        </label>
      </template>
      <div class="picker-actions">
        <button type="button" class="secondary mini" @click="pickerOpen = false">
          {{ t("importModal.cancel") }}
        </button>
        <button type="button" class="mini" :disabled="!currentTarget()" @click="applyTarget">
          {{ t("comparer.applyTarget") }}
        </button>
      </div>
      <p class="muted tip">{{ t("comparer.memoryHint") }}</p>
    </div>
  </div>
</template>

<style scoped>
.cmp-chrome {
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  background: var(--panel-header);
}
.cmp-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.55rem;
  font-size: 0.8rem;
}
.cmp-title {
  font-weight: 600;
}
.cmp-path {
  flex: 1;
  min-width: 4rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.75rem;
}
.mem-badge {
  flex-shrink: 0;
  font-size: 0.68rem;
  padding: 0.1rem 0.35rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  max-width: 10rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.target-picker {
  padding: 0.5rem 0.65rem 0.65rem;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  background: var(--panel);
}
.mode-row {
  display: flex;
  gap: 0.35rem;
}
.method-chip {
  background: var(--secondary-btn);
  color: var(--text);
  border: 1px solid transparent;
  padding: 0.3rem 0.5rem;
  font-size: 0.75rem;
}
.method-chip.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 28%, transparent);
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  font-size: 0.78rem;
  color: var(--muted);
}
.field input,
.field select {
  background: var(--input-bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.3rem 0.4rem;
}
.picker-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.4rem;
}
.tip {
  font-size: 0.72rem;
  margin: 0;
}
.active-toggle {
  outline: 1px solid var(--accent);
}
.muted {
  color: var(--muted);
}
</style>

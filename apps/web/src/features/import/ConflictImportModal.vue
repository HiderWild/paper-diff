<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type { DryRunImportResult } from "../../shared/api";

const props = defineProps<{
  open: boolean;
  dryRun: DryRunImportResult | null;
  fileCount: number;
}>();

const emit = defineEmits<{
  close: [];
  confirm: [
    payload: {
      on_conflict: "overwrite" | "skip" | "rename";
      resolutions: Record<string, string>;
    },
  ];
  cancel: [];
}>();

const { t } = useI18n();

/** Per-path: overwrite | skip | rename */
const perPath = ref<Record<string, "overwrite" | "skip" | "rename">>({});
const globalDefault = ref<"overwrite" | "skip" | "rename">("overwrite");

watch(
  () => props.dryRun,
  (d) => {
    const next: Record<string, "overwrite" | "skip" | "rename"> = {};
    for (const c of d?.conflicts || []) {
      next[c.path] = "overwrite";
    }
    perPath.value = next;
  },
  { immediate: true }
);

const conflicts = computed(() => props.dryRun?.conflicts || []);
const newCount = computed(() => props.dryRun?.new_files?.length || 0);

function applyGlobal() {
  const next = { ...perPath.value };
  for (const k of Object.keys(next)) next[k] = globalDefault.value;
  perPath.value = next;
}

function confirm() {
  const resolutions: Record<string, string> = {};
  for (const [path, action] of Object.entries(perPath.value)) {
    resolutions[path] = action;
  }
  emit("confirm", {
    on_conflict: globalDefault.value,
    resolutions,
  });
}
</script>

<template>
  <div v-if="open" class="modal-overlay" @click.self="emit('close')">
    <div class="modal" role="dialog">
      <h3>{{ t("import.conflictTitle") }}</h3>
      <p class="muted">
        {{
          t("import.conflictSummary", {
            conflicts: conflicts.length,
            fresh: newCount,
            total: fileCount,
          })
        }}
      </p>
      <div class="global-row">
        <label>{{ t("import.defaultAction") }}</label>
        <select v-model="globalDefault" @change="applyGlobal">
          <option value="overwrite">{{ t("import.overwrite") }}</option>
          <option value="skip">{{ t("import.skip") }}</option>
          <option value="rename">{{ t("import.rename") }}</option>
        </select>
        <button type="button" class="secondary mini" @click="applyGlobal">
          {{ t("import.applyAll") }}
        </button>
      </div>
      <ul class="conflict-list">
        <li v-for="c in conflicts" :key="c.path">
          <code>{{ c.path }}</code>
          <select v-model="perPath[c.path]">
            <option value="overwrite">{{ t("import.overwrite") }}</option>
            <option value="skip">{{ t("import.skip") }}</option>
            <option value="rename">{{ t("import.rename") }}</option>
          </select>
        </li>
      </ul>
      <div class="modal-actions">
        <button type="button" class="secondary" @click="emit('cancel')">
          {{ t("import.cancelAll") }}
        </button>
        <button type="button" @click="confirm">
          {{ t("import.continueImport") }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}
.modal {
  background: #0f172a;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem;
  width: min(520px, 96vw);
  max-height: 80vh;
  overflow: auto;
}
.modal h3 {
  margin: 0 0 0.5rem;
  font-size: 1rem;
}
.global-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  margin: 0.75rem 0;
}
.conflict-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 40vh;
  overflow: auto;
}
.conflict-list li {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--border);
}
.conflict-list code {
  flex: 1;
  font-size: 0.75rem;
  word-break: break-all;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 1rem;
}
</style>

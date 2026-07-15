<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { parseLatexLog, type LatexLogIssue } from "./parseLatexLog";

const props = defineProps<{
  content: string;
  path?: string;
}>();

const emit = defineEmits<{
  "update:mode": [mode: "issues" | "source"];
  jumpLogLine: [line: number];
}>();

const { t } = useI18n();
const mode = ref<"issues" | "source">("issues");
const filter = ref<"all" | "error" | "warning">("all");

const summary = computed(() => parseLatexLog(props.content || ""));

const visible = computed(() => {
  const all = summary.value.issues;
  if (filter.value === "all") return all;
  return all.filter((i) => i.severity === filter.value);
});

function onIssue(i: LatexLogIssue) {
  emit("jumpLogLine", i.logLine);
  mode.value = "source";
}

watch(mode, (m) => emit("update:mode", m));
</script>

<template>
  <div class="log-host">
    <div class="log-toolbar">
      <span v-if="path" class="path muted" :title="path">{{ path }}</span>
      <span class="badge err" v-if="summary.errorCount">
        {{ t("viewer.logErrors", { n: summary.errorCount }) }}
      </span>
      <span class="badge warn" v-if="summary.warningCount">
        {{ t("viewer.logWarnings", { n: summary.warningCount }) }}
      </span>
      <span
        v-if="!summary.errorCount && !summary.warningCount"
        class="muted tiny"
      >
        {{ t("viewer.logClean") }}
      </span>
      <div class="seg">
        <button
          type="button"
          class="mini secondary"
          :class="{ active: mode === 'issues' }"
          @click="mode = 'issues'"
        >
          {{ t("viewer.logIssues") }}
        </button>
        <button
          type="button"
          class="mini secondary"
          :class="{ active: mode === 'source' }"
          @click="mode = 'source'"
        >
          {{ t("viewer.mdSource") }}
        </button>
      </div>
    </div>

    <div v-show="mode === 'issues'" class="issues-panel">
      <div class="filters">
        <button
          type="button"
          class="chip"
          :class="{ on: filter === 'all' }"
          @click="filter = 'all'"
        >
          {{ t("viewer.logFilterAll") }}
        </button>
        <button
          type="button"
          class="chip"
          :class="{ on: filter === 'error' }"
          @click="filter = 'error'"
        >
          {{ t("viewer.logFilterErrors") }}
        </button>
        <button
          type="button"
          class="chip"
          :class="{ on: filter === 'warning' }"
          @click="filter = 'warning'"
        >
          {{ t("viewer.logFilterWarnings") }}
        </button>
      </div>
      <ul v-if="visible.length" class="issue-list">
        <li
          v-for="(iss, idx) in visible"
          :key="idx + '-' + iss.logLine"
          class="issue"
          :class="iss.severity"
          @click="onIssue(iss)"
        >
          <span class="sev">{{
            iss.severity === "error"
              ? t("viewer.logSevError")
              : t("viewer.logSevWarning")
          }}</span>
          <span class="msg" :title="iss.message">{{ iss.message }}</span>
          <span class="loc muted">
            <template v-if="iss.file">{{ iss.file }}</template>
            <template v-if="iss.sourceLine">:{{ iss.sourceLine }}</template>
            · log:{{ iss.logLine }}
          </span>
        </li>
      </ul>
      <p v-else class="empty muted">{{ t("viewer.logNoIssues") }}</p>
    </div>

    <div v-show="mode === 'source'" class="source-slot">
      <slot name="source" />
    </div>
  </div>
</template>

<style scoped>
.log-host {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel);
}
.log-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--border);
  background: var(--panel-header);
  flex-shrink: 0;
  font-size: 0.75rem;
}
.path {
  max-width: 30%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.badge {
  font-size: 0.65rem;
  border-radius: 3px;
  padding: 0.05rem 0.35rem;
  border: 1px solid var(--border);
}
.badge.err {
  color: var(--danger);
  border-color: color-mix(in srgb, var(--danger) 50%, var(--border));
}
.badge.warn {
  color: #c9a227;
  border-color: color-mix(in srgb, #c9a227 50%, var(--border));
}
.seg {
  margin-left: auto;
  display: flex;
  gap: 0.25rem;
}
.seg .active {
  border-color: var(--accent);
}
.issues-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.filters {
  display: flex;
  gap: 0.3rem;
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.chip {
  font-size: 0.7rem;
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.chip.on {
  border-color: var(--accent);
  color: var(--text);
}
.issue-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow: auto;
  flex: 1;
}
.issue {
  display: grid;
  grid-template-columns: 4.2rem 1fr auto;
  gap: 0.45rem;
  align-items: baseline;
  padding: 0.4rem 0.65rem;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  font-size: 0.78rem;
}
.issue:hover {
  background: color-mix(in srgb, var(--accent) 8%, transparent);
}
.issue.error .sev {
  color: var(--danger);
}
.issue.warning .sev {
  color: #c9a227;
}
.sev {
  font-weight: 600;
  text-transform: uppercase;
  font-size: 0.65rem;
  letter-spacing: 0.03em;
}
.msg {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.loc {
  font-size: 0.68rem;
  white-space: nowrap;
}
.source-slot {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.empty {
  padding: 1rem;
  font-size: 0.85rem;
}
.muted {
  color: var(--muted);
}
.tiny {
  font-size: 0.72rem;
}
</style>

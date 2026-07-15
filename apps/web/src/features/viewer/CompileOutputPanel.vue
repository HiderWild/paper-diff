<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { parseLatexLog, type LatexLogIssue } from "./parseLatexLog";

const props = defineProps<{
  logText: string;
  /** Structured errors from compile job API (optional) */
  apiErrors?: Array<{
    file?: string | null;
    line?: number | null;
    message: string;
  }>;
}>();

const emit = defineEmits<{
  jump: [
    err: { file?: string | null; line?: number | null; message: string },
  ];
  jumpLogLine: [line: number];
}>();

const { t } = useI18n();
const mode = ref<"issues" | "raw">("issues");
const filter = ref<"all" | "error" | "warning">("all");

const summary = computed(() => parseLatexLog(props.logText || ""));

/** Prefer parsed log issues; fall back to API errors if parse finds nothing. */
const issues = computed<LatexLogIssue[]>(() => {
  if (summary.value.issues.length) return summary.value.issues;
  const api = props.apiErrors || [];
  return api.map((e, i) => ({
    severity: "error" as const,
    message: e.message,
    logLine: i + 1,
    file: e.file || undefined,
    sourceLine: e.line ?? undefined,
    raw: e.message,
  }));
});

const visible = computed(() => {
  if (filter.value === "all") return issues.value;
  return issues.value.filter((i) => i.severity === filter.value);
});

const errorCount = computed(
  () =>
    summary.value.errorCount ||
    issues.value.filter((i) => i.severity === "error").length
);
const warningCount = computed(() => summary.value.warningCount);

function onIssue(iss: LatexLogIssue) {
  if (iss.file || iss.sourceLine) {
    emit("jump", {
      file: iss.file || null,
      line: iss.sourceLine ?? null,
      message: iss.message,
    });
  } else {
    emit("jumpLogLine", iss.logLine);
  }
}

// When new log arrives with errors, default to issues view
watch(
  () => props.logText,
  (v, old) => {
    if (v && v !== old && (summary.value.errorCount || summary.value.warningCount)) {
      mode.value = "issues";
    }
  }
);
</script>

<template>
  <div class="compile-out">
    <div class="out-toolbar">
      <span class="badge err" v-if="errorCount">
        {{ t("viewer.logErrors", { n: errorCount }) }}
      </span>
      <span class="badge warn" v-if="warningCount">
        {{ t("viewer.logWarnings", { n: warningCount }) }}
      </span>
      <span v-if="!errorCount && !warningCount" class="muted tiny">
        {{ logText ? t("viewer.logClean") : t("panels.compileLog") }}
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
          :class="{ active: mode === 'raw' }"
          @click="mode = 'raw'"
        >
          {{ t("viewer.logRaw") }}
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
            <template v-if="!iss.file && !iss.sourceLine"
              >log:{{ iss.logLine }}</template
            >
          </span>
        </li>
      </ul>
      <p v-else class="empty muted">
        {{ logText ? t("viewer.logNoIssues") : t("panels.compileLog") }}
      </p>
    </div>

    <pre v-show="mode === 'raw'" class="raw-log">{{
      logText || t("panels.compileLog")
    }}</pre>
  </div>
</template>

<style scoped>
.compile-out {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.out-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.5rem;
  border-bottom: 1px solid var(--border);
  background: var(--panel-header, var(--panel));
  flex-shrink: 0;
  font-size: 0.75rem;
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
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.chip {
  font-size: 0.7rem;
  padding: 0.12rem 0.4rem;
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
  grid-template-columns: 3.5rem 1fr auto;
  gap: 0.4rem;
  align-items: baseline;
  padding: 0.35rem 0.55rem;
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
  font-size: 0.62rem;
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
.raw-log {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 0.5rem 0.65rem;
  overflow: auto;
  font-size: 0.75rem;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text);
}
.empty {
  padding: 0.75rem;
  font-size: 0.82rem;
}
.muted {
  color: var(--muted);
}
.tiny {
  font-size: 0.72rem;
}
</style>

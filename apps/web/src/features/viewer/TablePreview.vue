<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { parseTableText, type TableData } from "./parseTable";

const props = defineProps<{
  content: string;
  path?: string;
}>();

const emit = defineEmits<{
  "update:mode": [mode: "table" | "source"];
}>();

const { t } = useI18n();
const mode = ref<"table" | "source">("table");
const maxRows = 500;

const table = computed<TableData>(() =>
  parseTableText(props.content || "", { maxRows })
);

const delimLabel = computed(() => {
  const d = table.value.delimiter;
  if (d === "\t") return "TSV";
  if (d === ";") return "CSV(;)";
  return "CSV";
});

watch(mode, (m) => emit("update:mode", m));
</script>

<template>
  <div class="table-host">
    <div class="table-toolbar">
      <span v-if="path" class="path muted" :title="path">{{ path }}</span>
      <span class="badge muted">{{ delimLabel }}</span>
      <span class="meta muted">
        {{
          t("viewer.tableMeta", {
            cols: table.headers.length,
            rows: table.totalRows,
          })
        }}
        <template v-if="table.truncated">
          · {{ t("viewer.tableTruncated", { n: maxRows }) }}
        </template>
      </span>
      <div class="seg">
        <button
          type="button"
          class="mini secondary"
          :class="{ active: mode === 'table' }"
          @click="mode = 'table'"
        >
          {{ t("viewer.tableView") }}
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
    <div v-show="mode === 'table'" class="table-scroll">
      <table v-if="table.headers.length">
        <thead>
          <tr>
            <th class="row-num">#</th>
            <th v-for="(h, i) in table.headers" :key="i">{{ h || `col${i + 1}` }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, ri) in table.rows" :key="ri">
            <td class="row-num">{{ ri + 1 }}</td>
            <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else class="empty muted">{{ t("viewer.tableEmpty") }}</p>
    </div>
    <div v-show="mode === 'source'" class="source-slot">
      <slot name="source" />
    </div>
  </div>
</template>

<style scoped>
.table-host {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel);
}
.table-toolbar {
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
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.badge {
  font-size: 0.65rem;
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0.05rem 0.3rem;
}
.meta {
  font-size: 0.72rem;
}
.seg {
  margin-left: auto;
  display: flex;
  gap: 0.25rem;
}
.seg .active {
  border-color: var(--accent);
}
.table-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
table {
  border-collapse: collapse;
  width: max-content;
  min-width: 100%;
  font-size: 0.78rem;
  font-variant-numeric: tabular-nums;
}
th,
td {
  border: 1px solid var(--border);
  padding: 0.28rem 0.5rem;
  text-align: left;
  max-width: 18rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
th {
  position: sticky;
  top: 0;
  background: var(--panel-header);
  z-index: 1;
  font-weight: 600;
}
.row-num {
  color: var(--muted);
  text-align: right;
  width: 2.5rem;
  background: color-mix(in srgb, var(--panel-header) 80%, transparent);
}
tbody tr:nth-child(even) td {
  background: color-mix(in srgb, var(--accent) 4%, transparent);
}
.source-slot {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.empty {
  padding: 1rem;
}
.muted {
  color: var(--muted);
}
</style>

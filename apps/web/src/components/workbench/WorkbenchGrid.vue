<script setup lang="ts">
import { storeToRefs } from "pinia";
import {
  intentFromColumnGap,
  useWorkbenchStore,
  type DropIntent,
} from "../../stores/workbench";
import WorkbenchColumn from "./WorkbenchColumn.vue";

const emit = defineEmits<{
  fileDrop: [tabId: string, path: string];
  invalidDrop: [message: string];
}>();

const wb = useWorkbenchStore();
const { rows, columns, dropPreview } = storeToRefs(wb);

function onGapDragOver(
  rowId: string,
  insertIndex: number,
  e: DragEvent
) {
  e.preventDefault();
  const el = e.currentTarget as HTMLElement;
  const r = el.getBoundingClientRect();
  const relY = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
  const intent = intentFromColumnGap(rowId, insertIndex, relY);
  wb.setDropPreview(intent);
}

function onGapDrop(rowId: string, insertIndex: number, e: DragEvent) {
  e.preventDefault();
  const el = e.currentTarget as HTMLElement;
  const r = el.getBoundingClientRect();
  const relY = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
  const intent = intentFromColumnGap(rowId, insertIndex, relY);
  const tabId = e.dataTransfer?.getData("application/x-paper-diff-tab");
  const colId = e.dataTransfer?.getData("application/x-paper-diff-column");
  if (tabId) wb.applyDrop(tabId, intent);
  else if (colId) wb.moveColumn(colId, intent);
  else {
    const tool = e.dataTransfer?.getData("application/x-paper-diff-tool");
    if (tool) {
      const tab = wb.openTool(tool as never, null);
      if (tab) {
        wb.detachTab(tab.id);
        wb.applyDrop(tab.id, intent);
      }
    }
  }
  wb.setDropPreview(null);
}

function onRowGapDragOver(index: number, e: DragEvent) {
  e.preventDefault();
  wb.setDropPreview({ type: "between-rows", index });
}

function onRowGapDrop(index: number, e: DragEvent) {
  e.preventDefault();
  const intent: DropIntent = { type: "between-rows", index };
  const tabId = e.dataTransfer?.getData("application/x-paper-diff-tab");
  const colId = e.dataTransfer?.getData("application/x-paper-diff-column");
  if (tabId) wb.applyDrop(tabId, intent);
  else if (colId) wb.moveColumn(colId, intent);
  wb.setDropPreview(null);
}

function highlightFor(colId: string) {
  const p = dropPreview.value;
  if (!p) return null;
  if (
    (p.type === "split-left" ||
      p.type === "split-right" ||
      p.type === "split-above" ||
      p.type === "split-below" ||
      p.type === "tab-append" ||
      p.type === "tab-insert") &&
    p.columnId === colId
  ) {
    return p;
  }
  return null;
}

/** Resize adjacent columns by dragging vertical gap */
function onColSashDown(rowId: string, leftColId: string, rightColId: string, e: MouseEvent) {
  e.preventDefault();
  e.stopPropagation();
  const row = rows.value.find((r) => r.id === rowId);
  if (!row) return;
  const left = columns.value[leftColId];
  const right = columns.value[rightColId];
  if (!left || !right) return;
  const startX = e.clientX;
  const left0 = left.size;
  const right0 = right.size;
  const sum = left0 + right0;

  function onMove(ev: MouseEvent) {
    const dx = ev.clientX - startX;
    // approx: 1 flex unit ≈ 200px heuristic scaled by sum
    const delta = dx / 200;
    let nl = Math.max(0.35, left0 + delta);
    let nr = Math.max(0.35, sum - nl);
    nl = sum - nr;
    wb.setColumnSize(leftColId, nl);
    wb.setColumnSize(rightColId, nr);
  }
  function onUp() {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    wb.persist();
  }
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}

function onRowSashDown(upperRowId: string, lowerRowId: string, e: MouseEvent) {
  e.preventDefault();
  e.stopPropagation();
  const upper = rows.value.find((r) => r.id === upperRowId);
  const lower = rows.value.find((r) => r.id === lowerRowId);
  if (!upper || !lower) return;
  const startY = e.clientY;
  const u0 = upper.size;
  const l0 = lower.size;
  const sum = u0 + l0;
  function onMove(ev: MouseEvent) {
    const dy = ev.clientY - startY;
    const delta = dy / 160;
    let nu = Math.max(0.35, u0 + delta);
    let nl = Math.max(0.35, sum - nu);
    nu = sum - nl;
    wb.setRowSize(upperRowId, nu);
    wb.setRowSize(lowerRowId, nl);
  }
  function onUp() {
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerup", onUp);
    wb.persist();
  }
  window.addEventListener("pointermove", onMove);
  window.addEventListener("pointerup", onUp);
}
</script>

<template>
  <div class="wb-grid">
    <template v-for="(row, ri) in rows" :key="row.id">
      <div
        v-if="ri > 0"
        class="wb-row-gap"
        :class="{
          active:
            dropPreview?.type === 'between-rows' &&
            dropPreview.index === ri,
        }"
        @dragover="onRowGapDragOver(ri, $event)"
        @drop="onRowGapDrop(ri, $event)"
        @pointerdown="
          onRowSashDown(rows[ri - 1].id, row.id, $event)
        "
      />
      <div class="wb-row" :style="{ flex: `${row.size} 1 0` }">
        <template v-for="(colId, ci) in row.columnIds" :key="colId">
          <div
            v-if="ci > 0"
            class="wb-col-gap"
            :class="{
              active:
                (dropPreview?.type === 'between-columns' &&
                  dropPreview.rowId === row.id &&
                  dropPreview.index === ci) ||
                (dropPreview?.type === 'row-above-pair' &&
                  dropPreview.rowId === row.id) ||
                (dropPreview?.type === 'row-below-pair' &&
                  dropPreview.rowId === row.id),
            }"
            @dragover="onGapDragOver(row.id, ci, $event)"
            @drop="onGapDrop(row.id, ci, $event)"
            @pointerdown="
              onColSashDown(
                row.id,
                row.columnIds[ci - 1],
                colId,
                $event
              )
            "
          />
          <WorkbenchColumn
            v-if="columns[colId]"
            :column="columns[colId]"
            :highlight="highlightFor(colId)"
            @file-drop="(tabId, path) => emit('fileDrop', tabId, path)"
            @invalid-drop="(msg) => emit('invalidDrop', msg)"
          />
        </template>
      </div>
    </template>
    <div
      class="wb-row-gap end"
      :class="{
        active:
          dropPreview?.type === 'between-rows' &&
          dropPreview.index === rows.length,
      }"
      @dragover="onRowGapDragOver(rows.length, $event)"
      @drop="onRowGapDrop(rows.length, $event)"
    />
  </div>
</template>

<style scoped>
.wb-grid {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  gap: 0;
}
.wb-row {
  display: flex;
  flex-direction: row;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  gap: 0;
}
.wb-col-gap {
  flex: 0 0 5px;
  background: transparent;
  cursor: col-resize;
  position: relative;
  z-index: 3;
}
.wb-col-gap:hover,
.wb-col-gap.active {
  background: color-mix(in srgb, var(--accent) 55%, transparent);
}
.wb-row-gap {
  flex: 0 0 5px;
  background: transparent;
  cursor: row-resize;
  z-index: 3;
}
.wb-row-gap:hover,
.wb-row-gap.active {
  background: color-mix(in srgb, var(--accent) 55%, transparent);
}
.wb-row-gap.end {
  flex: 0 0 4px;
}
</style>

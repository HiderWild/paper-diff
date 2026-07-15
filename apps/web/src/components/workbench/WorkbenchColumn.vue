<script setup lang="ts">
import { computed, ref } from "vue";
import { useI18n } from "vue-i18n";
import {
  intentFromColumnPoint,
  useWorkbenchStore,
  type Column,
  type DropIntent,
  type ToolKind,
  toolAcceptsPath,
} from "../../stores/workbench";
import ToolBody from "./ToolBody.vue";

const props = defineProps<{
  column: Column;
  highlight: DropIntent | null;
}>();

const emit = defineEmits<{
  fileDrop: [tabId: string, path: string];
  invalidDrop: [message: string];
}>();

const { t } = useI18n();
const wb = useWorkbenchStore();
const rootEl = ref<HTMLElement | null>(null);

const tabList = computed(() =>
  props.column.tabIds.map((id) => wb.tabs[id]).filter(Boolean)
);

const activeTab = computed(() => {
  const id = props.column.activeTabId || props.column.tabIds[0];
  return id ? wb.tabs[id] : null;
});

function tabLabel(tab: { kind: ToolKind; path: string | null; title?: string }) {
  const kind = t(`tools.${tab.kind}`);
  if (tab.kind === "output") return t("tools.output");
  if (tab.path) {
    const base = tab.path.split("/").pop() || tab.path;
    return base;
  }
  return `${kind}`;
}

function onTabDragStart(tabId: string, e: DragEvent) {
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("application/x-paper-diff-tab", tabId);
    e.dataTransfer.setData("text/plain", `tab:${tabId}`);
  }
}

function onColumnChromeDragStart(e: DragEvent) {
  // Only allow when dragging from empty tab-bar gutter
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData(
      "application/x-paper-diff-column",
      props.column.id
    );
    e.dataTransfer.setData("text/plain", `col:${props.column.id}`);
  }
}

function relativePoint(e: DragEvent) {
  const el = rootEl.value;
  if (!el) return { relX: 0.5, relY: 0.5 };
  const r = el.getBoundingClientRect();
  return {
    relX: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
    relY: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
  };
}

function onDragOver(e: DragEvent) {
  e.preventDefault();
  const { relX, relY } = relativePoint(e);
  // tab bar zone?
  const target = e.target as HTMLElement | null;
  const inTabBar = !!target?.closest?.(".wb-tabbar");
  let tabIndex: number | undefined;
  if (inTabBar) {
    const tabs = Array.from(
      rootEl.value?.querySelectorAll(".wb-tab") || []
    ) as HTMLElement[];
    tabIndex = tabs.length;
    for (let i = 0; i < tabs.length; i++) {
      const tr = tabs[i].getBoundingClientRect();
      if (e.clientX < tr.left + tr.width / 2) {
        tabIndex = i;
        break;
      }
    }
  }
  const intent = intentFromColumnPoint(props.column.id, relX, relY, {
    inTabBar,
    tabIndex,
  });
  wb.setDropPreview(intent);
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
}

function onDrop(e: DragEvent) {
  e.preventDefault();
  e.stopPropagation();
  const intent = wb.dropPreview || {
    type: "tab-append" as const,
    columnId: props.column.id,
  };

  const tool = e.dataTransfer?.getData(
    "application/x-paper-diff-tool"
  ) as ToolKind;
  if (tool) {
    // new empty tool
    if (intent.type === "tab-insert") {
      wb.addTabToColumn(props.column.id, tool, null, intent.index);
    } else if (intent.type === "tab-append") {
      wb.addTabToColumn(props.column.id, tool, null);
    } else {
      const tab = wb.openTool(tool, null);
      if (tab) {
        wb.detachTab(tab.id);
        wb.applyDrop(tab.id, intent);
      }
    }
    wb.setDropPreview(null);
    return;
  }

  const colId = e.dataTransfer?.getData("application/x-paper-diff-column");
  if (colId && colId !== props.column.id) {
    wb.moveColumn(colId, intent);
    wb.setDropPreview(null);
    return;
  }

  const tabId = e.dataTransfer?.getData("application/x-paper-diff-tab");
  if (tabId) {
    wb.applyDrop(tabId, intent);
    return;
  }

  const path =
    e.dataTransfer?.getData("application/x-paper-diff-path") ||
    e.dataTransfer?.getData("text/plain");
  if (path && !path.startsWith("tab:") && !path.startsWith("col:") && !path.startsWith("tool:")) {
    const tab = activeTab.value;
    if (!tab || tab.kind === "output") {
      emit(
        "invalidDrop",
        t("tools.unsupportedFile", {
          tool: t("tools.output"),
          file: path,
        })
      );
      wb.setDropPreview(null);
      return;
    }
    if (!toolAcceptsPath(tab.kind, path)) {
      emit(
        "invalidDrop",
        t("tools.unsupportedFile", {
          tool: t(`tools.${tab.kind}`),
          file: path,
        })
      );
      wb.setDropPreview(null);
      return;
    }
    emit("fileDrop", tab.id, path);
  }
  wb.setDropPreview(null);
}

function onDragLeave(e: DragEvent) {
  const related = e.relatedTarget as Node | null;
  if (rootEl.value && related && rootEl.value.contains(related)) return;
  wb.setDropPreview(null);
}

const edgeHint = computed(() => {
  const p = props.highlight;
  if (!p) return null;
  if (p.type === "split-left" && p.columnId === props.column.id) return "left";
  if (p.type === "split-right" && p.columnId === props.column.id) return "right";
  if (p.type === "split-above" && p.columnId === props.column.id) return "top";
  if (p.type === "split-below" && p.columnId === props.column.id) return "bottom";
  if (
    (p.type === "tab-append" || p.type === "tab-insert") &&
    p.columnId === props.column.id
  )
    return "center";
  return null;
});
</script>

<template>
  <section
    ref="rootEl"
    class="wb-column"
    :class="{ focused: tabList.some((t) => t.id === wb.focusedTabId) }"
    :style="{ flex: `${column.size} 1 0` }"
    @dragover="onDragOver"
    @drop="onDrop"
    @dragleave="onDragLeave"
  >
    <div
      class="wb-tabbar"
      draggable="true"
      :title="t('workbench.dragColumn')"
      @dragstart="onColumnChromeDragStart"
    >
      <button
        v-for="tab in tabList"
        :key="tab.id"
        type="button"
        class="wb-tab"
        :class="{
          active: tab.id === column.activeTabId,
          focused: tab.id === wb.focusedTabId,
        }"
        draggable="true"
        @click="wb.focusTab(tab.id)"
        @dragstart.stop="onTabDragStart(tab.id, $event)"
      >
        <span class="wb-tab-label">{{ tabLabel(tab) }}</span>
        <span
          class="wb-tab-close"
          role="button"
          :title="t('tools.close')"
          @click.stop="wb.closeTab(tab.id)"
          >×</span
        >
      </button>
      <span class="wb-tabbar-gutter" aria-hidden="true" />
    </div>
    <div class="wb-body" :class="{ 'edge-hint': edgeHint }" :data-edge="edgeHint || undefined">
      <ToolBody v-if="activeTab" :tab="activeTab" />
      <div v-else class="empty">{{ t("workbench.emptyColumn") }}</div>
    </div>
  </section>
</template>

<style scoped>
.wb-column {
  display: flex;
  flex-direction: column;
  min-width: 120px;
  min-height: 80px;
  border: 1px solid var(--border);
  background: var(--panel);
  overflow: hidden;
  position: relative;
}
.wb-column.focused {
  border-color: color-mix(in srgb, var(--accent) 70%, var(--border));
}
.wb-tabbar {
  display: flex;
  align-items: stretch;
  gap: 1px;
  background: var(--panel-header);
  border-bottom: 1px solid var(--border);
  min-height: 1.85rem;
  flex-shrink: 0;
  overflow-x: auto;
  cursor: grab;
}
.wb-tabbar-gutter {
  flex: 1 1 auto;
  min-width: 1.5rem;
}
.wb-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  max-width: 10rem;
  padding: 0.2rem 0.4rem 0.2rem 0.55rem;
  background: transparent;
  color: var(--muted);
  border: none;
  border-radius: 0;
  border-right: 1px solid var(--border);
  font-size: 0.75rem;
  cursor: pointer;
  flex: 0 1 auto;
}
.wb-tab.active {
  background: var(--panel);
  color: var(--text);
}
.wb-tab.focused {
  box-shadow: inset 0 -2px 0 var(--accent);
}
.wb-tab-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wb-tab-close {
  opacity: 0.55;
  font-size: 0.9rem;
  line-height: 1;
  padding: 0 0.15rem;
  border-radius: 3px;
}
.wb-tab-close:hover {
  opacity: 1;
  background: color-mix(in srgb, var(--danger) 30%, transparent);
}
.wb-body {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}
.wb-body.edge-hint::after {
  content: "";
  position: absolute;
  pointer-events: none;
  background: color-mix(in srgb, var(--accent) 35%, transparent);
  z-index: 5;
}
.wb-body[data-edge="left"]::after {
  inset: 0 auto 0 0;
  width: 18%;
}
.wb-body[data-edge="right"]::after {
  inset: 0 0 0 auto;
  width: 18%;
}
.wb-body[data-edge="top"]::after {
  inset: 0 0 auto 0;
  height: 18%;
}
.wb-body[data-edge="bottom"]::after {
  inset: auto 0 0 0;
  height: 18%;
}
.wb-body[data-edge="center"]::after {
  inset: 8px;
  border: 2px dashed var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  border-radius: 6px;
}
.empty {
  color: var(--muted);
  padding: 1rem;
  font-size: 0.85rem;
}
</style>

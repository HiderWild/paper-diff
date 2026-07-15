<script setup lang="ts">
import { onBeforeUnmount, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { ToolKind } from "../stores/workbench";

const { t } = useI18n();

/** Compact fixed-size icons — no overflowing text glyphs like "PDF". */
const tools: Array<{ kind: ToolKind; labelKey: string }> = [
  { kind: "comparer", labelKey: "tools.comparer" },
  { kind: "editor", labelKey: "tools.editor" },
  { kind: "pdf", labelKey: "tools.pdf" },
  { kind: "word", labelKey: "tools.word" },
  { kind: "output", labelKey: "tools.output" },
];

const emit = defineEmits<{
  open: [kind: ToolKind];
  dragStart: [kind: ToolKind, e: DragEvent];
}>();

const tip = ref<{ kind: ToolKind; x: number; y: number; text: string } | null>(
  null
);
let tipTimer: ReturnType<typeof setTimeout> | null = null;

function clearTipTimer() {
  if (tipTimer != null) {
    clearTimeout(tipTimer);
    tipTimer = null;
  }
}

function onEnter(kind: ToolKind, e: MouseEvent) {
  clearTipTimer();
  const el = e.currentTarget as HTMLElement;
  tipTimer = setTimeout(() => {
    const r = el.getBoundingClientRect();
    tip.value = {
      kind,
      x: r.left + r.width / 2,
      y: r.bottom + 6,
      text: t(tools.find((x) => x.kind === kind)!.labelKey),
    };
  }, 1000);
}

function onLeave() {
  clearTipTimer();
  tip.value = null;
}

function onDragStart(kind: ToolKind, e: DragEvent) {
  onLeave();
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "copyMove";
    e.dataTransfer.setData("text/plain", `tool:${kind}`);
    e.dataTransfer.setData("application/x-paper-diff-tool", kind);
  }
  emit("dragStart", kind, e);
}

onBeforeUnmount(() => clearTipTimer());
</script>

<template>
  <div class="tool-strip" role="toolbar" :aria-label="t('tools.strip')">
    <button
      v-for="tool in tools"
      :key="tool.kind"
      type="button"
      class="tool-icon"
      :aria-label="t(tool.labelKey)"
      draggable="true"
      @click="emit('open', tool.kind)"
      @dragstart="onDragStart(tool.kind, $event)"
      @mouseenter="onEnter(tool.kind, $event)"
      @mouseleave="onLeave"
      @focus="onEnter(tool.kind, $event as unknown as MouseEvent)"
      @blur="onLeave"
    >
      <!-- Comparer: two panes with arrows -->
      <svg
        v-if="tool.kind === 'comparer'"
        class="glyph-svg"
        viewBox="0 0 16 16"
        aria-hidden="true"
      >
        <rect
          x="1.5"
          y="2"
          width="5.5"
          height="12"
          rx="1"
          fill="none"
          stroke="currentColor"
          stroke-width="1.4"
        />
        <rect
          x="9"
          y="2"
          width="5.5"
          height="12"
          rx="1"
          fill="none"
          stroke="currentColor"
          stroke-width="1.4"
        />
        <path
          d="M5.2 8h5.6M9.2 6.2 11 8 9.2 9.8M6.8 6.2 5 8 6.8 9.8"
          fill="none"
          stroke="currentColor"
          stroke-width="1.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <!-- Editor: pencil -->
      <svg
        v-else-if="tool.kind === 'editor'"
        class="glyph-svg"
        viewBox="0 0 16 16"
        aria-hidden="true"
      >
        <path
          d="M11.5 1.8 14.2 4.5 5.8 12.9 2.5 13.5l.6-3.3z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.3"
          stroke-linejoin="round"
        />
        <path
          d="M10 3.3 12.7 6"
          stroke="currentColor"
          stroke-width="1.3"
        />
      </svg>
      <!-- PDF document -->
      <svg
        v-else-if="tool.kind === 'pdf'"
        class="glyph-svg"
        viewBox="0 0 16 16"
        aria-hidden="true"
      >
        <path
          d="M4 1.5h5.2L13 5.3V14a.8.8 0 0 1-.8.8H4a.8.8 0 0 1-.8-.8V2.3A.8.8 0 0 1 4 1.5z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.3"
          stroke-linejoin="round"
        />
        <path
          d="M9.2 1.7V5h3.5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.3"
          stroke-linejoin="round"
        />
        <text
          x="8"
          y="11.2"
          text-anchor="middle"
          font-size="4.2"
          font-weight="700"
          fill="currentColor"
          font-family="system-ui,sans-serif"
        >
          PDF
        </text>
      </svg>
      <!-- Word -->
      <svg
        v-else-if="tool.kind === 'word'"
        class="glyph-svg"
        viewBox="0 0 16 16"
        aria-hidden="true"
      >
        <path
          d="M4 1.5h5.2L13 5.3V14a.8.8 0 0 1-.8.8H4a.8.8 0 0 1-.8-.8V2.3A.8.8 0 0 1 4 1.5z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.3"
          stroke-linejoin="round"
        />
        <path
          d="M9.2 1.7V5h3.5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.3"
          stroke-linejoin="round"
        />
        <text
          x="8"
          y="11.2"
          text-anchor="middle"
          font-size="5"
          font-weight="700"
          fill="currentColor"
          font-family="system-ui,sans-serif"
        >
          W
        </text>
      </svg>
      <!-- Output / terminal lines -->
      <svg
        v-else
        class="glyph-svg"
        viewBox="0 0 16 16"
        aria-hidden="true"
      >
        <rect
          x="1.5"
          y="2"
          width="13"
          height="12"
          rx="1.2"
          fill="none"
          stroke="currentColor"
          stroke-width="1.3"
        />
        <path
          d="M4 6.2 6.2 8 4 9.8M7.5 10.5h4.5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.3"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <Teleport to="body">
      <div
        v-if="tip"
        class="tool-float-tip"
        role="tooltip"
        :style="{ left: tip.x + 'px', top: tip.y + 'px' }"
      >
        {{ tip.text }}
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.tool-strip {
  display: flex;
  align-items: center;
  gap: 0.2rem;
  padding: 0 0.25rem;
  border-left: 1px solid var(--border);
  border-right: 1px solid var(--border);
  margin: 0 0.25rem;
}
.tool-icon {
  width: 1.85rem;
  height: 1.75rem;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: var(--muted);
  border: 1px solid transparent;
  border-radius: 4px;
  /* Clickable control → pointing hand (not open palm / grab) */
  cursor: pointer;
  overflow: hidden;
}
.tool-icon:hover {
  background: color-mix(in srgb, var(--accent) 18%, var(--panel));
  color: var(--text);
  border-color: var(--border);
  cursor: pointer;
}
.tool-icon:active {
  cursor: pointer;
}
/* Actual drag-in-progress only: optional grabbing after dragstart */
.tool-icon.dragging {
  cursor: grabbing;
}
.glyph-svg {
  width: 1rem;
  height: 1rem;
  display: block;
  pointer-events: none;
  flex-shrink: 0;
}
</style>

<style>
/* Teleported tip — not scoped */
.tool-float-tip {
  position: fixed;
  z-index: 200;
  transform: translateX(-50%);
  padding: 0.3rem 0.55rem;
  border-radius: 6px;
  font-size: 0.75rem;
  line-height: 1.3;
  white-space: nowrap;
  pointer-events: none;
  background: #1e293b;
  color: #f8fafc;
  border: 1px solid var(--border, #334155);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);
}
:root[data-theme="light"] .tool-float-tip {
  background: #0f172a;
  color: #f8fafc;
}
</style>

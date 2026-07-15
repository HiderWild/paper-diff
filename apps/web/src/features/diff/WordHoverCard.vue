<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref } from "vue";
import { useI18n } from "vue-i18n";
import type { WordCardModel } from "./wordHover";

const props = defineProps<{
  model: WordCardModel;
  x: number;
  y: number;
}>();

const emit = defineEmits<{
  apply: [];
  dismiss: [];
  pointerEnter: [];
  pointerLeave: [];
}>();

const { t } = useI18n();
const root = ref<HTMLElement | null>(null);
const applyBtn = ref<HTMLButtonElement | null>(null);

type Mode = "replace" | "insert" | "delete";

const mode = computed<Mode>(() => {
  if (props.model.isInsert) return "insert";
  if (props.model.isDelete) return "delete";
  return "replace";
});

function clip(s: string, n = 160): string {
  if (s.length <= n) return s;
  return s.slice(0, n) + "…";
}

function titleForKind() {
  if (mode.value === "insert") return t("hoverAccept.titleInsert");
  if (mode.value === "delete") return t("hoverAccept.titleDelete");
  return props.model.kind === "sentence"
    ? t("hoverAccept.titleSentence")
    : t("hoverAccept.title");
}

function applyLabel() {
  if (mode.value === "insert") return t("hoverAccept.applyInsert");
  if (mode.value === "delete") return t("hoverAccept.applyDelete");
  return props.model.kind === "sentence"
    ? t("hoverAccept.applySentence")
    : t("hoverAccept.apply");
}

function workDisplay(): { text: string; empty: boolean } {
  if (mode.value === "insert") {
    return { text: t("hoverAccept.workEmptyInsert"), empty: true };
  }
  const raw = props.model.workText;
  if (!raw) {
    return { text: t("hoverAccept.workEmpty"), empty: true };
  }
  return { text: clip(raw), empty: false };
}

function compareDisplay(): { text: string; empty: boolean } {
  if (mode.value === "delete") {
    return { text: t("hoverAccept.compareEmptyDelete"), empty: true };
  }
  const raw = props.model.compareText;
  if (!raw) {
    return { text: t("hoverAccept.compareEmpty"), empty: true };
  }
  return { text: clip(raw), empty: false };
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.preventDefault();
    e.stopPropagation();
    emit("dismiss");
    return;
  }
  if (e.key === "Enter" && !e.isComposing) {
    const t0 = e.target as HTMLElement | null;
    if (root.value?.contains(t0) || t0 === document.body) {
      e.preventDefault();
      emit("apply");
    }
  }
}

onMounted(async () => {
  window.addEventListener("keydown", onKey, true);
  await nextTick();
  applyBtn.value?.focus();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey, true);
});
</script>

<template>
  <div
    ref="root"
    class="word-hover-card float-tip"
    :class="'mode-' + mode"
    role="dialog"
    :aria-label="titleForKind()"
    :style="{ left: x + 'px', top: y + 'px' }"
    tabindex="-1"
    @pointerdown.stop
    @pointerenter="emit('pointerEnter')"
    @pointerleave="emit('pointerLeave')"
    @wheel.stop
  >
    <div class="card-head">
      <div class="card-title">
        <span class="mode-badge" :class="mode">{{
          mode === "insert"
            ? t("hoverAccept.badgeInsert")
            : mode === "delete"
              ? t("hoverAccept.badgeDelete")
              : t("hoverAccept.badgeReplace")
        }}</span>
        <!-- insert/delete: badge alone is enough; replace keeps kind title -->
        <span v-if="mode === 'replace'" class="kind-title">{{
          titleForKind()
        }}</span>
      </div>
      <button
        ref="applyBtn"
        type="button"
        class="mini primary apply-btn"
        :class="{ danger: mode === 'delete' }"
        :title="applyLabel() + ' (Enter)'"
        @click="emit('apply')"
      >
        {{ applyLabel() }}
      </button>
    </div>

    <!-- Insert / delete: one-line caption + snippet -->
    <template v-if="mode === 'insert'">
      <p class="one-line">
        {{ t("hoverAccept.insertBrief") }}
        <code class="inline-snip compare">{{ compareDisplay().text }}</code>
      </p>
    </template>

    <template v-else-if="mode === 'delete'">
      <p class="one-line">
        {{ t("hoverAccept.deleteBrief") }}
        <code class="inline-snip work">{{ workDisplay().text }}</code>
      </p>
    </template>

    <!-- Replace: side-by-side -->
    <template v-else>
      <div class="pair">
        <div class="side">
          <div class="label">{{ t("hoverAccept.work") }}</div>
          <code
            class="snip"
            :class="{ empty: workDisplay().empty, work: !workDisplay().empty }"
            >{{ workDisplay().text }}</code
          >
        </div>
        <div class="arrow" aria-hidden="true">←</div>
        <div class="side">
          <div class="label">{{ t("hoverAccept.compare") }}</div>
          <code
            class="snip"
            :class="{
              empty: compareDisplay().empty,
              compare: !compareDisplay().empty,
            }"
            >{{ compareDisplay().text }}</code
          >
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.word-hover-card {
  position: fixed;
  z-index: 220;
  width: max-content;
  min-width: 11rem;
  max-width: min(66rem, 92vw);
  padding: 0.4rem 0.5rem 0.45rem;
  border-radius: 8px;
  background: var(--panel, #1a2332);
  color: var(--text, #e7ecf3);
  border: 1px solid var(--border, #2d3a4d);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
  font-size: 0.85rem;
  transform: translate(-50%, 8px);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.55rem;
  margin-bottom: 0.3rem;
  min-height: 1.45rem;
}
.card-title {
  font-weight: 600;
  font-size: 0.78rem;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
  min-width: 0;
  flex: 1 1 auto;
}
.kind-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.apply-btn {
  flex: 0 0 auto;
  margin-left: auto;
  padding: 0.18rem 0.5rem;
  font-size: 0.72rem;
  line-height: 1.2;
}
.mode-badge {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  text-transform: none;
}
.mode-badge.insert {
  background: color-mix(in srgb, var(--green, #22c55e) 28%, var(--panel));
  color: var(--green, #22c55e);
}
.mode-badge.delete {
  background: color-mix(in srgb, var(--danger, #f87171) 28%, var(--panel));
  color: var(--danger, #f87171);
}
.mode-badge.replace {
  background: color-mix(in srgb, var(--accent, #3b82f6) 28%, var(--panel));
  color: var(--accent, #3b82f6);
}
.lead {
  margin: 0 0 0.35rem;
  font-size: 0.78rem;
  line-height: 1.35;
  color: var(--text);
}
.pair {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 0.35rem;
  align-items: start;
}
.one-line {
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.35;
  color: var(--muted);
  max-width: 36rem;
  padding-right: 0.1rem;
}
.inline-snip {
  display: inline;
  font-size: 0.8rem;
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  background: var(--surface-deep, #0b0f14);
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
.inline-snip.work {
  border-left: 2px solid var(--danger, #f87171);
}
.inline-snip.compare {
  border-left: 2px solid var(--green, #22c55e);
}
.label {
  font-size: 0.68rem;
  color: var(--muted);
  margin-bottom: 0.15rem;
}
.snip {
  display: block;
  font-size: 0.78rem;
  padding: 0.25rem 0.35rem;
  border-radius: 4px;
  background: var(--surface-deep, #0b0f14);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 4.5rem;
  overflow: auto;
  min-height: 1.4rem;
}
.snip.work {
  border-left: 2px solid var(--danger, #f87171);
}
.snip.compare {
  border-left: 2px solid var(--green, #22c55e);
}
/* Empty / missing side: italic muted explanation, not a mysterious symbol */
.snip.empty {
  border-left: 2px dashed var(--muted);
  color: var(--muted);
  font-style: italic;
  font-family: inherit;
  background: color-mix(in srgb, var(--muted) 8%, var(--surface-deep, #0b0f14));
}
.arrow {
  align-self: center;
  color: var(--accent);
  font-size: 1rem;
  padding-top: 0.9rem;
}
.primary {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}
.primary.danger {
  background: var(--danger, #ef4444);
}
.muted {
  color: var(--muted);
}
</style>

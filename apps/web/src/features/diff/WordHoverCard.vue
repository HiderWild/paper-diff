<script setup lang="ts">
import { nextTick, onMounted, onBeforeUnmount, ref } from "vue";
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
  /** Pointer entered the card — parent should cancel leave-dismiss timers */
  pointerEnter: [];
  pointerLeave: [];
}>();

const { t } = useI18n();
const root = ref<HTMLElement | null>(null);
const applyBtn = ref<HTMLButtonElement | null>(null);

function clip(s: string, n = 160): string {
  if (!s) return "∅";
  if (s.length <= n) return s;
  return s.slice(0, n) + "…";
}

function titleForKind() {
  return props.model.kind === "sentence"
    ? t("hoverAccept.titleSentence")
    : t("hoverAccept.title");
}

function applyLabel() {
  return props.model.kind === "sentence"
    ? t("hoverAccept.applySentence")
    : t("hoverAccept.apply");
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.preventDefault();
    e.stopPropagation();
    emit("dismiss");
    return;
  }
  if (e.key === "Enter" && !e.isComposing) {
    // Apply when focus is on card or apply button
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
    role="dialog"
    :aria-label="titleForKind()"
    :style="{ left: x + 'px', top: y + 'px' }"
    tabindex="-1"
    @pointerdown.stop
    @pointerenter="emit('pointerEnter')"
    @pointerleave="emit('pointerLeave')"
    @wheel.stop
  >
    <div class="card-title">{{ titleForKind() }}</div>
    <div class="pair">
      <div class="side">
        <div class="label">{{ t("hoverAccept.work") }}</div>
        <code class="snip work" :title="model.workText">{{
          clip(model.workText)
        }}</code>
      </div>
      <div class="arrow" aria-hidden="true">←</div>
      <div class="side">
        <div class="label">{{ t("hoverAccept.compare") }}</div>
        <code class="snip compare" :title="model.compareText">{{
          clip(model.compareText)
        }}</code>
      </div>
    </div>
    <p v-if="model.isInsert" class="hint muted">
      {{ t("hoverAccept.insertHint") }}
    </p>
    <p v-else-if="model.isDelete" class="hint muted">
      {{ t("hoverAccept.deleteHint") }}
    </p>
    <div class="actions">
      <button type="button" class="secondary mini" @click="emit('dismiss')">
        {{ t("hoverAccept.dismiss") }}
      </button>
      <button
        ref="applyBtn"
        type="button"
        class="mini primary"
        @click="emit('apply')"
      >
        {{ applyLabel() }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.word-hover-card {
  position: fixed;
  z-index: 220;
  min-width: 14rem;
  max-width: min(22rem, 90vw);
  padding: 0.55rem 0.65rem 0.5rem;
  border-radius: 8px;
  background: var(--panel, #1a2332);
  color: var(--text, #e7ecf3);
  border: 1px solid var(--border, #2d3a4d);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
  font-size: 0.85rem;
  transform: translate(-50%, 8px);
}
.card-title {
  font-weight: 600;
  font-size: 0.8rem;
  margin-bottom: 0.4rem;
  color: var(--muted);
}
.pair {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 0.35rem;
  align-items: start;
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
}
.snip.work {
  border-left: 2px solid var(--danger, #f87171);
}
.snip.compare {
  border-left: 2px solid var(--green, #22c55e);
}
.arrow {
  align-self: center;
  color: var(--accent);
  font-size: 1rem;
  padding-top: 0.9rem;
}
.hint {
  margin: 0.35rem 0 0;
  font-size: 0.72rem;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.35rem;
  margin-top: 0.45rem;
}
.primary {
  background: var(--accent);
  color: #fff;
}
.muted {
  color: var(--muted);
}
</style>

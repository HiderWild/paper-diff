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
    <div class="card-title">
      <span class="mode-badge" :class="mode">{{
        mode === "insert"
          ? t("hoverAccept.badgeInsert")
          : mode === "delete"
            ? t("hoverAccept.badgeDelete")
            : t("hoverAccept.badgeReplace")
      }}</span>
      {{ titleForKind() }}
    </div>

    <!-- Insert: emphasize what will be added from compare -->
    <template v-if="mode === 'insert'">
      <p class="lead">{{ t("hoverAccept.insertLead") }}</p>
      <div class="single-snip compare">
        <div class="label">{{ t("hoverAccept.compare") }}</div>
        <code class="snip filled">{{ compareDisplay().text }}</code>
      </div>
      <p class="hint muted">{{ t("hoverAccept.insertHint") }}</p>
    </template>

    <!-- Delete: emphasize what will be removed from work -->
    <template v-else-if="mode === 'delete'">
      <p class="lead">{{ t("hoverAccept.deleteLead") }}</p>
      <div class="single-snip work">
        <div class="label">{{ t("hoverAccept.work") }}</div>
        <code class="snip filled">{{ workDisplay().text }}</code>
      </div>
      <p class="hint muted">{{ t("hoverAccept.deleteHint") }}</p>
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

    <div class="actions">
      <button type="button" class="secondary mini" @click="emit('dismiss')">
        {{ t("hoverAccept.dismiss") }}
      </button>
      <button
        ref="applyBtn"
        type="button"
        class="mini primary"
        :class="{ danger: mode === 'delete' }"
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
  /* Fit short phrases; allow up to ~3× previous 22rem cap before forced wrap */
  width: max-content;
  min-width: 12rem;
  max-width: min(66rem, 92vw);
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
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
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
.single-snip {
  margin-bottom: 0.15rem;
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
.snip.filled {
  border-left-width: 2px;
}
.single-snip.work .snip.filled {
  border-left-color: var(--danger, #f87171);
}
.single-snip.compare .snip.filled {
  border-left-color: var(--green, #22c55e);
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
.hint {
  margin: 0.35rem 0 0;
  font-size: 0.72rem;
  line-height: 1.35;
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
.primary.danger {
  background: var(--danger, #ef4444);
}
.muted {
  color: var(--muted);
}
</style>

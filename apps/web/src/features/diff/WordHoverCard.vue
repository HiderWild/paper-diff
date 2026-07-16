<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import type { WordCardModel } from "./wordHover";
import type { TexContext } from "./texSentenceContext";
import { EMPTY_TEX_CONTEXT } from "./texSentenceContext";
import { renderTexSentence } from "./renderTexSentence";
import { highlightChangedInRendered } from "./highlightChangedInRendered";

const props = withDefaults(
  defineProps<{
    model: WordCardModel;
    x: number;
    y: number;
    /** below: top edge at y; above: bottom edge at y (hug highlight top) */
    placement?: "below" | "above";
    /** TeX context for rendered sentence view (citations/labels from .aux) */
    texCtx?: TexContext;
    /** Word-level changed texts to highlight in rendered view (work side) */
    workChangedTexts?: string[];
    /** Word-level changed texts to highlight in rendered view (compare side) */
    compareChangedTexts?: string[];
  }>(),
  { placement: "below" }
);

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

// --- Rendered TeX sentence view (sentence replace only) ---
const viewMode = ref<"source" | "render">("render");
// Reset to render whenever the model changes (new unit hovered)
watch(
  () => props.model,
  () => {
    viewMode.value = "render";
  }
);

const effectiveCtx = computed<TexContext>(
  () => props.texCtx ?? EMPTY_TEX_CONTEXT
);

const isSentenceReplace = computed(
  () => mode.value === "replace" && props.model.kind === "sentence"
);

const showNotCompiledBanner = computed(
  () =>
    isSentenceReplace.value &&
    viewMode.value === "render" &&
    !effectiveCtx.value.compiled
);

function renderedWorkHtml(): string {
  if (!isSentenceReplace.value || viewMode.value !== "render") return "";
  const raw = props.model.workText;
  if (!raw) return "";
  const { html } = renderTexSentence(raw, effectiveCtx.value);
  return highlightChangedInRendered(html, props.workChangedTexts ?? []);
}

function renderedCompareHtml(): string {
  if (!isSentenceReplace.value || viewMode.value !== "render") return "";
  const raw = props.model.compareText;
  if (!raw) return "";
  const { html } = renderTexSentence(raw, effectiveCtx.value);
  return highlightChangedInRendered(html, props.compareChangedTexts ?? []);
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
    class="word-hover-card"
    :class="[
      'mode-' + mode,
      mode !== 'replace' ? 'compact' : 'replace-mode',
      'place-' + placement,
    ]"
    role="dialog"
    :aria-label="titleForKind()"
    :style="{ left: x + 'px', top: y + 'px' }"
    tabindex="-1"
    @pointerdown.stop
    @pointerenter="emit('pointerEnter')"
    @pointerleave="emit('pointerLeave')"
    @wheel.stop
  >
    <!-- Insert / delete: ONE horizontal strip — badge | text | apply -->
    <template v-if="mode === 'insert' || mode === 'delete'">
      <span class="mode-badge" :class="mode">{{
        mode === "insert"
          ? t("hoverAccept.badgeInsert")
          : t("hoverAccept.badgeDelete")
      }}</span>
      <span class="one-line">
        {{
          mode === "insert"
            ? t("hoverAccept.insertBrief")
            : t("hoverAccept.deleteBrief")
        }}
        <code
          class="inline-snip"
          :class="mode === 'insert' ? 'compare' : 'work'"
          >{{
            mode === "insert" ? compareDisplay().text : workDisplay().text
          }}</code
        >
      </span>
      <button
        ref="applyBtn"
        type="button"
        class="apply-btn"
        :class="{ danger: mode === 'delete' }"
        :title="applyLabel() + ' (Enter)'"
        @click.stop="emit('apply')"
      >
        {{ applyLabel() }}
      </button>
    </template>

    <!-- Replace: header + independent-width sides (short side hugs content) -->
    <template v-else>
      <div class="replace-head">
        <span class="mode-badge replace">{{
          t("hoverAccept.badgeReplace")
        }}</span>
        <span class="kind-title">{{ titleForKind() }}</span>
        <span
          v-if="model.displayExpanded"
          class="ctx-hint muted"
          :title="t('hoverAccept.expandedHint')"
          >+</span
        >
        <span v-if="isSentenceReplace" class="view-toggle">
          <button
            type="button"
            class="toggle-btn"
            :class="{ active: viewMode === 'source' }"
            @click.stop="viewMode = 'source'"
          >
            {{ t("hoverAccept.viewSource") }}
          </button>
          <button
            type="button"
            class="toggle-btn"
            :class="{ active: viewMode === 'render' }"
            @click.stop="viewMode = 'render'"
          >
            {{ t("hoverAccept.viewRender") }}
          </button>
        </span>
        <button
          ref="applyBtn"
          type="button"
          class="apply-btn"
          :title="applyLabel() + ' (Enter)'"
          @click.stop="emit('apply')"
        >
          {{ applyLabel() }}
        </button>
      </div>
      <div v-if="showNotCompiledBanner" class="not-compiled-banner">
        {{ t("hoverAccept.notCompiledWarn") }}
      </div>
      <div class="pair independent">
        <div class="side shrink-wrap">
          <div class="label">{{ t("hoverAccept.work") }}</div>
          <template v-if="isSentenceReplace && viewMode === 'render'">
            <div
              class="snip rendered work"
              :class="{ empty: workDisplay().empty }"
              v-html="renderedWorkHtml()"
            ></div>
          </template>
          <template v-else>
            <code
              class="snip"
              :class="{ empty: workDisplay().empty, work: !workDisplay().empty }"
              >{{ workDisplay().text }}</code
            >
          </template>
        </div>
        <div class="arrow" aria-hidden="true">←</div>
        <div class="side shrink-wrap">
          <div class="label">{{ t("hoverAccept.compare") }}</div>
          <template v-if="isSentenceReplace && viewMode === 'render'">
            <div
              class="snip rendered compare"
              :class="{ empty: compareDisplay().empty }"
              v-html="renderedCompareHtml()"
            ></div>
          </template>
          <template v-else>
            <code
              class="snip"
              :class="{
                empty: compareDisplay().empty,
                compare: !compareDisplay().empty,
              }"
              >{{ compareDisplay().text }}</code
            >
          </template>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.word-hover-card {
  position: fixed;
  z-index: 220;
  box-sizing: border-box;
  width: max-content;
  max-width: min(40rem, 92vw);
  padding: 0.35rem 0.45rem;
  border-radius: 8px;
  background: var(--panel, #1a2332);
  color: var(--text, #e7ecf3);
  border: 1px solid var(--border, #2d3a4d);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
  font-size: 0.85rem;
  /* x = highlight horizontal center */
  transform: translateX(-50%);
}
/* below: card top sits on highlight bottom (y); above: card bottom sits on highlight top (y) */
.word-hover-card.place-above {
  transform: translate(-50%, -100%);
}

/* insert/delete: single horizontal track, no separate layers */
.word-hover-card.compact {
  display: inline-flex;
  flex-direction: row;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
}

.word-hover-card.replace-mode {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
  /* sentence text can be long — grow with content, don't force wide empty sides */
  width: max-content;
  max-width: min(40rem, 92vw);
}
.word-hover-card.replace-mode.mode-replace {
  /* same rules; sentence/word both use replace template */
}

.replace-head {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 0.4rem;
  min-width: 0;
}

.kind-title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.75rem;
  color: var(--muted);
}

.apply-btn {
  flex: 0 0 auto;
  margin: 0 0 0 auto;
  padding: 0.18rem 0.5rem;
  font-size: 0.72rem;
  line-height: 1.2;
  font-weight: 600;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  background: var(--accent, #3b82f6);
  color: #fff;
  white-space: nowrap;
}
/* in compact row, push apply to the end of the same line */
.word-hover-card.compact .apply-btn {
  margin-left: 0.15rem;
}
.apply-btn.danger {
  background: var(--danger, #ef4444);
}
.apply-btn:hover {
  filter: brightness(1.08);
}

.mode-badge {
  font-size: 0.65rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  padding: 0.1rem 0.35rem;
  border-radius: 3px;
  text-transform: none;
  flex-shrink: 0;
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

.one-line {
  margin: 0;
  flex: 1 1 auto;
  min-width: 0;
  font-size: 0.78rem;
  line-height: 1.35;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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

/* Independent columns: short side hugs content; long side grows within max */
.pair {
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 0.4rem;
  width: max-content;
  max-width: min(40rem, 90vw);
}
.pair .side.shrink-wrap {
  flex: 0 1 auto;
  width: max-content;
  max-width: min(22rem, 48vw);
  min-width: 0;
}
.pair .side.shrink-wrap .snip {
  display: inline-block;
  width: max-content;
  max-width: min(22rem, 48vw);
  vertical-align: top;
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
  max-height: 5.5rem;
  overflow: auto;
  min-height: 1.2rem;
  box-sizing: border-box;
}
.snip.work {
  border-left: 2px solid var(--danger, #f87171);
}
.snip.compare {
  border-left: 2px solid var(--green, #22c55e);
}
.snip.empty {
  border-left: 2px dashed var(--muted);
  color: var(--muted);
  font-style: italic;
  font-family: inherit;
  background: color-mix(in srgb, var(--muted) 8%, var(--surface-deep, #0b0f14));
  width: auto;
}
.arrow {
  flex: 0 0 auto;
  align-self: center;
  color: var(--accent);
  font-size: 1rem;
  padding-top: 0.75rem;
}
.ctx-hint {
  font-size: 0.7rem;
  opacity: 0.75;
}
.muted {
  color: var(--muted);
}

/* --- Rendered TeX sentence view toggle + banner --- */
.view-toggle {
  display: inline-flex;
  gap: 0;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--border, #2d3a4d);
  flex-shrink: 0;
}
.toggle-btn {
  padding: 0.1rem 0.4rem;
  font-size: 0.68rem;
  border: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  line-height: 1.3;
}
.toggle-btn.active {
  background: var(--accent, #3b82f6);
  color: #fff;
}
.toggle-btn:hover:not(.active) {
  color: var(--text);
}

.not-compiled-banner {
  font-size: 0.68rem;
  padding: 0.2rem 0.4rem;
  border-radius: 3px;
  background: color-mix(in srgb, #fbbf24 18%, var(--panel));
  color: #fbbf24;
  border: 1px solid color-mix(in srgb, #fbbf24 30%, transparent);
}

/* Rendered sentence view — inline TeX rendering, not monospace */
.snip.rendered {
  font-family: inherit;
  font-size: 0.82rem;
  line-height: 1.5;
  white-space: normal;
  word-break: break-word;
  max-height: 12rem;
  overflow: auto;
}
.snip.rendered :deep(.katex) {
  font-size: 0.95em;
}
.snip.rendered :deep(.pd-tex-math) {
  white-space: nowrap;
}
.snip.rendered :deep(.pd-tex-unknown) {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.85em;
  color: var(--muted);
}
.snip.rendered :deep(.pd-tex-fn) {
  font-size: 0.75em;
  color: var(--muted);
  margin-top: 0.3rem;
  padding-left: 0.5rem;
  border-left: 2px solid var(--border);
}
.snip.rendered :deep(.pd-diff-changed) {
  background: color-mix(in srgb, #fde047 45%, transparent);
  color: inherit;
  border-radius: 2px;
  padding: 0 1px;
}
</style>

<script setup lang="ts">
/**
 * Full-tab image/SVG viewer aligned with PdfPane:
 * - fit-contain baseline, then user zoom (max 800%)
 * - content block centered; equal overflow when larger than host
 * - Ctrl/Cmd+scroll zoom; Ctrl/Cmd+drag pan
 * - no checkerboard / no leftover unscaled frame
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  path: string;
  workUrl: string;
  zoneUrl?: string | null;
}>();

const { t } = useI18n();

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 8; // 800%

const host = ref<HTMLDivElement | null>(null);
const content = ref<HTMLDivElement | null>(null);
const workImg = ref<HTMLImageElement | null>(null);
const zoneImg = ref<HTMLImageElement | null>(null);

const zoom = ref(1);
const zoomPct = computed(() => Math.round(zoom.value * 100));
const naturalW = ref(0);
const naturalH = ref(0);
const displayW = ref(0);
const displayH = ref(0);
const ctrlHeld = ref(false);
const panning = ref(false);
const overflow = ref(false);
const error = ref("");

const canPanCursor = computed(
  () => ctrlHeld.value && overflow.value && !panning.value
);
const isSvg = computed(() => /\.svg$/i.test(props.path || ""));
const dual = computed(() => !!props.zoneUrl);

function clampZoom(z: number) {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
}

function centerOverflow() {
  const el = host.value;
  if (!el) return;
  const maxL = el.scrollWidth - el.clientWidth;
  const maxT = el.scrollHeight - el.clientHeight;
  if (maxL > 0) el.scrollLeft = maxL / 2;
  else el.scrollLeft = 0;
  if (maxT > 0) el.scrollTop = maxT / 2;
  else el.scrollTop = 0;
}

function refreshOverflow() {
  const el = host.value;
  if (!el) {
    overflow.value = false;
    return;
  }
  overflow.value =
    el.scrollWidth > el.clientWidth + 1 ||
    el.scrollHeight > el.clientHeight + 1;
}

/** Fit-width/height baseline (contain), then multiply by user zoom. */
function layoutImage(preserveScroll = false) {
  const el = host.value;
  if (!el || !naturalW.value || !naturalH.value) return;
  const prevL = el.scrollLeft;
  const prevT = el.scrollTop;
  // Usable area under sticky toolbar
  const toolbarH = 36;
  const pad = 16;
  const availW = Math.max(40, el.clientWidth - pad * 2);
  // For dual, each pane gets half minus gap
  const gap = dual.value ? 12 : 0;
  const paneW = dual.value ? (availW - gap) / 2 : availW;
  const availH = Math.max(40, el.clientHeight - toolbarH - pad * 2);

  const fit = Math.min(paneW / naturalW.value, availH / naturalH.value, 1);
  const s = fit * zoom.value;
  displayW.value = Math.max(1, Math.round(naturalW.value * s));
  displayH.value = Math.max(1, Math.round(naturalH.value * s));
  zoomPctLocal(zoom.value);

  void nextTick(() => {
    if (preserveScroll) {
      el.scrollLeft = prevL;
      el.scrollTop = prevT;
    } else {
      centerOverflow();
    }
    refreshOverflow();
  });
}

function zoomPctLocal(z: number) {
  // kept for symmetry; zoomPct is computed from zoom
  void z;
}

function onWorkLoad() {
  const img = workImg.value;
  if (!img) return;
  naturalW.value = img.naturalWidth || img.width;
  naturalH.value = img.naturalHeight || img.height;
  error.value = "";
  layoutImage(false);
}

function onWorkError() {
  error.value = t("preview.imageLoadError");
}

function zoomBy(factor: number) {
  zoom.value = clampZoom(zoom.value * factor);
  layoutImage(true);
}

function zoomReset() {
  zoom.value = 1;
  layoutImage(false);
}

function onWheel(e: WheelEvent) {
  if (!(e.ctrlKey || e.metaKey)) return;
  e.preventDefault();
  e.stopPropagation();
  const factor = e.deltaY > 0 ? 0.9 : 1.1;
  const next = clampZoom(zoom.value * factor);
  if (Math.abs(next - zoom.value) < 0.001) return;
  zoom.value = next;
  layoutImage(true);
}

// —— Ctrl-drag pan (mirror PdfPane) ——
let panStartX = 0;
let panStartY = 0;
let panScrollL = 0;
let panScrollT = 0;
let panPointerId: number | null = null;

function canPan() {
  const el = host.value;
  if (!el) return false;
  return (
    el.scrollWidth > el.clientWidth + 1 ||
    el.scrollHeight > el.clientHeight + 1
  );
}

function onPointerDown(e: PointerEvent) {
  if (!(e.ctrlKey || e.metaKey)) return;
  if (!canPan()) return;
  if (e.button !== 0) return;
  e.preventDefault();
  const el = host.value;
  if (!el) return;
  panning.value = true;
  panStartX = e.clientX;
  panStartY = e.clientY;
  panScrollL = el.scrollLeft;
  panScrollT = el.scrollTop;
  panPointerId = e.pointerId;
  try {
    el.setPointerCapture(e.pointerId);
  } catch {
    /* ignore */
  }
}

function onPointerMove(e: PointerEvent) {
  if (!panning.value || !host.value) return;
  if (panPointerId != null && e.pointerId !== panPointerId) return;
  if (!(e.ctrlKey || e.metaKey)) {
    endPan();
    return;
  }
  e.preventDefault();
  const el = host.value;
  const maxL = Math.max(0, el.scrollWidth - el.clientWidth);
  const maxT = Math.max(0, el.scrollHeight - el.clientHeight);
  const dx = e.clientX - panStartX;
  const dy = e.clientY - panStartY;
  el.scrollLeft = Math.min(maxL, Math.max(0, panScrollL - dx));
  el.scrollTop = Math.min(maxT, Math.max(0, panScrollT - dy));
}

function endPan() {
  if (!panning.value) return;
  panning.value = false;
  const el = host.value;
  if (el && panPointerId != null) {
    try {
      el.releasePointerCapture(panPointerId);
    } catch {
      /* ignore */
    }
  }
  panPointerId = null;
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === "Control" || e.key === "Meta") ctrlHeld.value = true;
}
function onKeyUp(e: KeyboardEvent) {
  if (e.key === "Control" || e.key === "Meta") {
    ctrlHeld.value = false;
    endPan();
  }
}
function onBlur() {
  ctrlHeld.value = false;
  endPan();
}

let ro: ResizeObserver | null = null;

watch(
  () => [props.workUrl, props.zoneUrl, props.path] as const,
  () => {
    zoom.value = 1;
    naturalW.value = 0;
    naturalH.value = 0;
    displayW.value = 0;
    displayH.value = 0;
    error.value = "";
  },
  { immediate: true }
);

watch(dual, () => {
  if (naturalW.value) layoutImage(false);
});

if (typeof window !== "undefined") {
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  window.addEventListener("blur", onBlur);
}

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeyDown);
  window.removeEventListener("keyup", onKeyUp);
  window.removeEventListener("blur", onBlur);
  ro?.disconnect();
});

// Resize host → re-fit at current zoom
watch(host, (el) => {
  ro?.disconnect();
  if (!el || typeof ResizeObserver === "undefined") return;
  ro = new ResizeObserver(() => {
    if (naturalW.value) layoutImage(true);
  });
  ro.observe(el);
});
</script>

<template>
  <div
    ref="host"
    class="img-host"
    :class="{ 'can-pan': canPanCursor, panning }"
    @wheel="onWheel"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="endPan"
    @pointercancel="endPan"
    @lostpointercapture="endPan"
    @scroll.passive="refreshOverflow"
  >
    <div class="img-toolbar" @pointerdown.stop>
      <span class="path muted" :title="path">{{ path }}</span>
      <span v-if="isSvg" class="badge muted">SVG</span>
      <button type="button" class="mini secondary" @click="zoomBy(0.9)">−</button>
      <span class="zoom-label">{{ zoomPct }}%</span>
      <button type="button" class="mini secondary" @click="zoomBy(1.1)">+</button>
      <button type="button" class="mini secondary" @click="zoomReset">
        {{ t("pdf.zoomReset") }}
      </button>
      <span class="hint muted">{{ t("pdf.zoomHint") }}</span>
      <span class="hint muted">{{ t("pdf.panHint") }}</span>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <!-- Centered content block (like pdf-pages): grows with zoom, equal overflow -->
    <div
      ref="content"
      class="img-stage"
      :class="{ dual }"
    >
      <div class="pane">
        <img
          ref="workImg"
          class="zoom-img"
          :src="workUrl"
          :alt="path"
          :width="displayW || undefined"
          :height="displayH || undefined"
          :style="
            displayW
              ? { width: displayW + 'px', height: displayH + 'px' }
              : undefined
          "
          draggable="false"
          @load="onWorkLoad"
          @error="onWorkError"
        />
      </div>
      <div v-if="zoneUrl" class="pane">
        <img
          ref="zoneImg"
          class="zoom-img"
          :src="zoneUrl"
          :alt="path"
          :width="displayW || undefined"
          :height="displayH || undefined"
          :style="
            displayW
              ? { width: displayW + 'px', height: displayH + 'px' }
              : undefined
          "
          draggable="false"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.img-host {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  overflow: auto;
  display: flex;
  flex-direction: column;
  background: var(--surface-deep, #0b0f14);
  padding: 0 0 0.5rem;
  gap: 0;
  overscroll-behavior: contain;
}
.img-host.can-pan {
  cursor: grab;
}
.img-host.panning {
  cursor: grabbing;
  user-select: none;
}
.img-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  left: 0;
  right: 0;
  z-index: 2;
  background: var(--panel-header, #121a24);
  border-bottom: 1px solid var(--border, #2d3a4d);
  margin: 0;
  padding: 0.35rem 0.5rem;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  font-size: 0.75rem;
}
.path {
  margin: 0 0.25rem 0 0;
  max-width: 14rem;
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
.zoom-label {
  min-width: 3rem;
  text-align: center;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}
.hint {
  font-size: 0.7rem;
  margin-left: 0.35rem;
}
.img-stage {
  /* Center in host; when wider/taller than viewport, overflow is scrollable & centered on load */
  flex: 0 0 auto;
  margin: 0.5rem auto 0;
  padding: 0 0.5rem;
  box-sizing: content-box;
  width: max-content;
  min-width: min(100%, max-content);
  display: flex;
  flex-direction: row;
  gap: 0.75rem;
  align-items: flex-start;
  justify-content: center;
  background: transparent;
}
.img-stage.dual {
  /* two panes side by side as one centered block */
}
.pane {
  background: transparent;
  border: none;
  padding: 0;
  margin: 0;
  line-height: 0;
}
.zoom-img {
  display: block;
  /* natural intrinsic size is overridden by width/height when laid out */
  max-width: none;
  height: auto;
  user-select: none;
  background: transparent;
  /* No checkerboard — empty tab area is the host background only */
  image-rendering: auto;
}
.error {
  color: var(--danger);
  padding: 0.5rem;
  font-size: 0.85rem;
}
</style>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker;

const { t } = useI18n();
const props = defineProps<{ url: string | null }>();
const host = ref<HTMLDivElement | null>(null);
const container = ref<HTMLDivElement | null>(null);
const error = ref("");
const loading = ref(false);
const containerHasPages = ref(false);
/** User zoom vs fit-width baseline */
const zoom = ref(1);
const zoomPct = ref(100);
/** Ctrl/Meta held over host → pan cursor when overflow */
const ctrlHeld = ref(false);
const panning = ref(false);
const overflow = ref(false);

const canPanCursor = computed(
  () => ctrlHeld.value && overflow.value && !panning.value
);

let loadingTask: pdfjs.PDFDocumentLoadingTask | null = null;
let pdfDoc: PDFDocumentProxy | null = null;
let renderGen = 0;
let pagesData: ArrayBuffer | null = null;

/** Center scroll so overflow is equal on both sides (horizontal + vertical). */
function centerOverflow() {
  const el = host.value;
  if (!el) return;
  const maxL = el.scrollWidth - el.clientWidth;
  const maxT = el.scrollHeight - el.clientHeight;
  if (maxL > 0) el.scrollLeft = maxL / 2;
  else el.scrollLeft = 0;
  if (maxT > 0) el.scrollTop = maxT / 2;
  // keep top when only slight vertical overflow is normal page stack
}

function clampScroll() {
  const el = host.value;
  if (!el) return;
  const maxL = Math.max(0, el.scrollWidth - el.clientWidth);
  const maxT = Math.max(0, el.scrollHeight - el.clientHeight);
  el.scrollLeft = Math.min(maxL, Math.max(0, el.scrollLeft));
  el.scrollTop = Math.min(maxT, Math.max(0, el.scrollTop));
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

function canPan(): boolean {
  refreshOverflow();
  return overflow.value;
}

function fitScaleForPage(
  page: Awaited<ReturnType<PDFDocumentProxy["getPage"]>>
) {
  const base = page.getViewport({ scale: 1 });
  // Use host width (tab viewport), not growing content width
  const hostW = host.value?.clientWidth || 720;
  return Math.min(1.6, Math.max(0.5, (hostW - 24) / base.width));
}

async function paintPages(opts?: { preserveScroll?: boolean }) {
  if (!pdfDoc || !container.value) return;
  const gen = renderGen;
  const hostEl = host.value;
  const prevCenterX =
    hostEl && hostEl.scrollWidth > hostEl.clientWidth
      ? (hostEl.scrollLeft + hostEl.clientWidth / 2) / hostEl.scrollWidth
      : 0.5;
  const prevCenterY =
    hostEl && hostEl.scrollHeight > hostEl.clientHeight
      ? (hostEl.scrollTop + hostEl.clientHeight / 2) / hostEl.scrollHeight
      : 0;

  const wrap = document.createElement("div");
  wrap.className = "pdf-pages-inner";

  const maxPages = Math.min(pdfDoc.numPages, 40);
  for (let i = 1; i <= maxPages; i++) {
    if (gen !== renderGen || !pdfDoc) return;
    const page = await pdfDoc.getPage(i);
    const fit = fitScaleForPage(page);
    const scale = fit * zoom.value;
    const viewport = page.getViewport({ scale });
    const maxEdge = 4096;
    const renderScale =
      Math.max(viewport.width, viewport.height) > maxEdge
        ? scale * (maxEdge / Math.max(viewport.width, viewport.height))
        : scale;
    const renderVp = page.getViewport({ scale: renderScale });
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) continue;
    canvas.width = Math.floor(renderVp.width);
    canvas.height = Math.floor(renderVp.height);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;
    canvas.style.maxWidth = "none";
    canvas.style.flex = "0 0 auto";
    canvas.style.display = "block";
    wrap.appendChild(canvas);
    await page.render({ canvasContext: ctx, viewport: renderVp }).promise;
  }
  if (gen !== renderGen || !container.value) return;
  container.value.innerHTML = "";
  container.value.appendChild(wrap);
  zoomPct.value = Math.round(zoom.value * 100);
  containerHasPages.value = wrap.childElementCount > 0;

  await nextTick();
  if (!hostEl) return;
  if (opts?.preserveScroll) {
    const maxL = Math.max(0, hostEl.scrollWidth - hostEl.clientWidth);
    const maxT = Math.max(0, hostEl.scrollHeight - hostEl.clientHeight);
    hostEl.scrollLeft = Math.min(
      maxL,
      Math.max(0, prevCenterX * hostEl.scrollWidth - hostEl.clientWidth / 2)
    );
    hostEl.scrollTop = Math.min(
      maxT,
      Math.max(0, prevCenterY * hostEl.scrollHeight - hostEl.clientHeight / 2)
    );
  } else {
    centerOverflow();
  }
  clampScroll();
  refreshOverflow();
}

async function loadUrl(url: string) {
  const gen = ++renderGen;
  error.value = "";
  loading.value = true;
  zoom.value = 1;
  pdfDoc = null;
  pagesData = null;
  containerHasPages.value = false;
  await nextTick();
  if (!container.value) {
    loading.value = false;
    error.value = t("pdf.noContainer");
    return;
  }
  try {
    try {
      loadingTask?.destroy();
    } catch {
      /* ignore */
    }
    loadingTask = null;

    const res = await fetch(url, { credentials: "same-origin" });
    if (gen !== renderGen) return;
    if (!res.ok) {
      throw new Error(
        `HTTP ${res.status}: ${await res.text().catch(() => res.statusText)}`
      );
    }
    const data = await res.arrayBuffer();
    if (gen !== renderGen) return;
    pagesData = data;

    loadingTask = pdfjs.getDocument({ data: data.slice(0) });
    pdfDoc = await loadingTask.promise;
    if (gen !== renderGen) return;
    if (container.value) container.value.innerHTML = "";
    await paintPages({ preserveScroll: false });
  } catch (e) {
    if (gen === renderGen) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  } finally {
    if (gen === renderGen) loading.value = false;
  }
}

async function rezoom() {
  if (!pdfDoc || !pagesData) return;
  renderGen++;
  await paintPages({ preserveScroll: true });
}

function onWheel(e: WheelEvent) {
  // Ctrl/Cmd + wheel = zoom (pinch often sets ctrlKey)
  if (!(e.ctrlKey || e.metaKey)) return;
  e.preventDefault();
  e.stopPropagation();
  const factor = e.deltaY > 0 ? 0.9 : 1.1;
  const next = Math.min(4, Math.max(0.25, zoom.value * factor));
  if (Math.abs(next - zoom.value) < 0.001) return;
  zoom.value = next;
  void rezoom();
}

function zoomBy(factor: number) {
  zoom.value = Math.min(4, Math.max(0.25, zoom.value * factor));
  void rezoom();
}

function zoomReset() {
  zoom.value = 1;
  void rezoom();
}

// —— Ctrl-drag pan (only when content overflows) ——
let panStartX = 0;
let panStartY = 0;
let panScrollL = 0;
let panScrollT = 0;
let panPointerId: number | null = null;

function onPointerDown(e: PointerEvent) {
  if (!(e.ctrlKey || e.metaKey)) return;
  if (!canPan()) return;
  // Only primary button
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
    endPan(e);
    return;
  }
  e.preventDefault();
  const el = host.value;
  const maxL = Math.max(0, el.scrollWidth - el.clientWidth);
  const maxT = Math.max(0, el.scrollHeight - el.clientHeight);
  // Drag content with pointer: move right → content moves right → scrollLeft decreases
  const dx = e.clientX - panStartX;
  const dy = e.clientY - panStartY;
  el.scrollLeft = Math.min(maxL, Math.max(0, panScrollL - dx));
  el.scrollTop = Math.min(maxT, Math.max(0, panScrollT - dy));
}

function endPan(e?: PointerEvent) {
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
  clampScroll();
  void e;
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

watch(
  () => props.url,
  (u) => {
    if (u) void loadUrl(u);
    else {
      renderGen++;
      pdfDoc = null;
      pagesData = null;
      if (container.value) container.value.innerHTML = "";
      error.value = "";
      loading.value = false;
      zoom.value = 1;
      zoomPct.value = 100;
      containerHasPages.value = false;
    }
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  renderGen++;
  pdfDoc = null;
  window.removeEventListener("keydown", onKeyDown);
  window.removeEventListener("keyup", onKeyUp);
  window.removeEventListener("blur", onBlur);
  try {
    loadingTask?.destroy();
  } catch {
    /* ignore */
  }
});

// track Ctrl for cursor affordance
if (typeof window !== "undefined") {
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("keyup", onKeyUp);
  window.addEventListener("blur", onBlur);
}
</script>

<template>
  <div
    ref="host"
    class="pdf-host"
    :class="{
      'can-pan': canPanCursor,
      panning: panning,
    }"
    @wheel="onWheel"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="endPan"
    @pointercancel="endPan"
    @lostpointercapture="endPan()"
    @scroll.passive="refreshOverflow"
  >
    <div class="pdf-toolbar" @pointerdown.stop>
      <button type="button" class="mini secondary" @click="zoomBy(0.9)">−</button>
      <span class="zoom-label">{{ zoomPct }}%</span>
      <button type="button" class="mini secondary" @click="zoomBy(1.1)">+</button>
      <button type="button" class="mini secondary" @click="zoomReset">
        {{ t("pdf.zoomReset") }}
      </button>
      <span class="hint muted">{{ t("pdf.zoomHint") }}</span>
      <span class="hint muted">{{ t("pdf.panHint") }}</span>
    </div>
    <div v-if="!url" class="status-empty">{{ t("pdf.empty") }}</div>
    <div v-if="loading && !containerHasPages" class="status-empty">
      {{ t("preview.loading") }}
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <div ref="container" class="pdf-pages" />
  </div>
</template>

<style scoped>
.pdf-host {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  overflow: auto;
  display: flex;
  flex-direction: column;
  background: var(--surface-deep, #0b0f14);
  padding: 0.35rem 0.5rem 0.5rem;
  gap: 0.35rem;
  /* symmetric scroll: content can extend both sides via centered layout */
  overscroll-behavior: contain;
}
.pdf-host.can-pan {
  cursor: grab;
}
.pdf-host.panning {
  cursor: grabbing;
  user-select: none;
}
.pdf-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  left: 0;
  z-index: 2;
  background: color-mix(in srgb, var(--panel-header) 92%, transparent);
  padding: 0.25rem 0;
  backdrop-filter: blur(4px);
  width: 100%;
  box-sizing: border-box;
}
.zoom-label {
  min-width: 3rem;
  text-align: center;
  font-size: 0.75rem;
  color: var(--text);
}
.hint {
  font-size: 0.7rem;
  margin-left: 0.35rem;
}
.pdf-pages {
  /* Center block in host; when wider/taller than host, overflow is equal L/R & centered */
  flex: 0 0 auto;
  margin: 0 auto;
  width: max-content;
  min-width: min(100%, max-content);
}
.pdf-pages :deep(.pdf-pages-inner) {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  width: max-content;
}
.pdf-pages :deep(canvas) {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
  background: #fff;
  max-width: none !important;
  /* keep intrinsic style width/height from JS — never force 100% */
  display: block;
}
.status-empty {
  color: var(--muted);
  padding: 0.5rem 0.25rem;
  font-size: 0.9rem;
}
.error {
  color: var(--danger);
  font-size: 0.85rem;
  padding: 0.35rem;
  white-space: pre-wrap;
}
.muted {
  color: var(--muted);
}
</style>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
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
/** True after at least one successful paint of current document */
const containerHasPages = ref(false);
/** User zoom multiplier (1 = fit-width baseline * 1) */
const zoom = ref(1);
const zoomPct = ref(100);

let loadingTask: pdfjs.PDFDocumentLoadingTask | null = null;
let pdfDoc: PDFDocumentProxy | null = null;
let renderGen = 0;
let pagesData: ArrayBuffer | null = null;

function fitScaleForPage(
  page: Awaited<ReturnType<PDFDocumentProxy["getPage"]>>
) {
  const base = page.getViewport({ scale: 1 });
  const hostW = container.value?.clientWidth || host.value?.clientWidth || 720;
  return Math.min(1.6, Math.max(0.5, (hostW - 24) / base.width));
}

async function paintPages() {
  if (!pdfDoc || !container.value) return;
  const gen = renderGen;
  // Build off-DOM then swap to avoid flicker / "loading" jump
  const frag = document.createDocumentFragment();
  const maxPages = Math.min(pdfDoc.numPages, 40);
  for (let i = 1; i <= maxPages; i++) {
    if (gen !== renderGen || !pdfDoc) return;
    const page = await pdfDoc.getPage(i);
    const fit = fitScaleForPage(page);
    const scale = fit * zoom.value;
    const viewport = page.getViewport({ scale });
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) continue;
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    frag.appendChild(canvas);
    await page.render({ canvasContext: ctx, viewport }).promise;
  }
  if (gen !== renderGen || !container.value) return;
  container.value.innerHTML = "";
  container.value.appendChild(frag);
  zoomPct.value = Math.round(zoom.value * 100);
  containerHasPages.value = container.value.childElementCount > 0;
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
  // Keep previous canvases until first new page paints? For URL change, clear after fetch.
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
    await paintPages();
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
  // Silent: never toggle loading banner (avoids layout jump)
  renderGen++;
  await paintPages();
}

function onWheel(e: WheelEvent) {
  // Ctrl/Cmd + wheel (trackpad pinch often sets ctrlKey on browsers)
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
    }
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  renderGen++;
  pdfDoc = null;
  try {
    loadingTask?.destroy();
  } catch {
    /* ignore */
  }
});
</script>

<template>
  <div ref="host" class="pdf-host" @wheel="onWheel">
    <div class="pdf-toolbar">
      <button type="button" class="mini secondary" @click="zoomBy(0.9)">−</button>
      <span class="zoom-label">{{ zoomPct }}%</span>
      <button type="button" class="mini secondary" @click="zoomBy(1.1)">+</button>
      <button type="button" class="mini secondary" @click="zoomReset">
        {{ t("pdf.zoomReset") }}
      </button>
      <span class="hint muted">{{ t("pdf.zoomHint") }}</span>
    </div>
    <div v-if="!url" class="status-empty">{{ t("pdf.empty") }}</div>
    <!-- Only show loading on initial open when nothing is painted yet -->
    <div
      v-if="loading && !containerHasPages"
      class="status-empty"
    >
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
}
.pdf-toolbar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 2;
  background: color-mix(in srgb, var(--panel-header) 92%, transparent);
  padding: 0.25rem 0;
  backdrop-filter: blur(4px);
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
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  flex: 1 1 auto;
}
.pdf-pages :deep(canvas) {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
  background: #fff;
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

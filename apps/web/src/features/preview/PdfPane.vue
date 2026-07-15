<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import * as pdfjs from "pdfjs-dist";
import pdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker;

const { t } = useI18n();
const props = defineProps<{ url: string | null }>();
const container = ref<HTMLDivElement | null>(null);
const error = ref("");
const loading = ref(false);
let loadingTask: pdfjs.PDFDocumentLoadingTask | null = null;
let renderGen = 0;

async function render(url: string) {
  const gen = ++renderGen;
  error.value = "";
  loading.value = true;
  await nextTick();
  if (!container.value) {
    loading.value = false;
    error.value = t("pdf.noContainer");
    return;
  }
  container.value.innerHTML = "";
  try {
    try {
      loadingTask?.destroy();
    } catch {
      /* ignore */
    }
    loadingTask = null;

    // Fetch into memory so pdf.js always gets ArrayBuffer (works with relative /api URLs)
    const res = await fetch(url, { credentials: "same-origin" });
    if (gen !== renderGen) return;
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${await res.text().catch(() => res.statusText)}`);
    }
    const data = await res.arrayBuffer();
    if (gen !== renderGen) return;

    loadingTask = pdfjs.getDocument({ data });
    const pdf = await loadingTask.promise;
    if (gen !== renderGen) return;

    const maxPages = Math.min(pdf.numPages, 40);
    for (let i = 1; i <= maxPages; i++) {
      if (gen !== renderGen || !container.value) return;
      const page = await pdf.getPage(i);
      const base = page.getViewport({ scale: 1 });
      const hostW = container.value.clientWidth || 720;
      const scale = Math.min(1.5, Math.max(0.8, (hostW - 16) / base.width));
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      if (!ctx) continue;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      canvas.style.maxWidth = "100%";
      canvas.style.height = "auto";
      container.value.appendChild(canvas);
      await page.render({ canvasContext: ctx, viewport }).promise;
    }
  } catch (e) {
    if (gen === renderGen) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  } finally {
    if (gen === renderGen) loading.value = false;
  }
}

watch(
  () => props.url,
  (u) => {
    if (u) void render(u);
    else {
      renderGen++;
      if (container.value) container.value.innerHTML = "";
      error.value = "";
      loading.value = false;
    }
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  renderGen++;
  try {
    loadingTask?.destroy();
  } catch {
    /* ignore */
  }
});
</script>

<template>
  <div class="pdf-host">
    <div v-if="!url" class="status-empty">{{ t("pdf.empty") }}</div>
    <div v-if="loading" class="status-empty">{{ t("preview.loading") }}</div>
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
  padding: 0.5rem;
  gap: 0.5rem;
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
</style>

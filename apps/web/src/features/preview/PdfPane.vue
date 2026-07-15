<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import * as pdfjs from "pdfjs-dist";
// @ts-expect-error worker url
import pdfWorker from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjs.GlobalWorkerOptions.workerSrc = pdfWorker;

const props = defineProps<{ url: string | null }>();
const container = ref<HTMLDivElement | null>(null);
const error = ref("");
let loadingTask: pdfjs.PDFDocumentLoadingTask | null = null;

async function render(url: string) {
  error.value = "";
  if (!container.value) return;
  container.value.innerHTML = "";
  try {
    loadingTask?.destroy();
    loadingTask = pdfjs.getDocument(url);
    const pdf = await loadingTask.promise;
    for (let i = 1; i <= Math.min(pdf.numPages, 30); i++) {
      const page = await pdf.getPage(i);
      const viewport = page.getViewport({ scale: 1.2 });
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      if (!ctx) continue;
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      container.value.appendChild(canvas);
      await page.render({ canvasContext: ctx, viewport }).promise;
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  }
}

watch(
  () => props.url,
  (u) => {
    if (u) void render(u);
    else if (container.value) container.value.innerHTML = "";
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  loadingTask?.destroy();
});
</script>

<template>
  <div class="pdf-host">
    <div v-if="!url" class="status-empty">No PDF yet — run Compile</div>
    <div v-if="error" class="error">{{ error }}</div>
    <div ref="container" />
  </div>
</template>

<style scoped>
.status-empty {
  color: var(--muted);
  padding: 1rem;
  font-size: 0.9rem;
}
</style>

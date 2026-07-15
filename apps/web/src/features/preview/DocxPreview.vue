<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { renderAsync } from "docx-preview";

const { t } = useI18n();
const props = defineProps<{
  url: string | null;
  /** legacy .doc not supported by pure frontend render */
  legacyDoc?: boolean;
}>();

const host = ref<HTMLDivElement | null>(null);
const scaleWrap = ref<HTMLDivElement | null>(null);
const error = ref("");
const loading = ref(false);
const hasContent = ref(false);
/** User zoom multiplier — CSS transform only (silent; never toggles loading). */
const zoom = ref(1);
const zoomPct = computed(() => Math.round(zoom.value * 100));
let abort: AbortController | null = null;

function applyZoomStyle() {
  if (!scaleWrap.value) return;
  const z = zoom.value;
  scaleWrap.value.style.transform = `scale(${z})`;
  scaleWrap.value.style.transformOrigin = "top left";
  // Expand layout box so scroll area matches scaled content
  scaleWrap.value.style.width = z !== 1 ? `${100 / z}%` : "100%";
}

async function render(url: string) {
  error.value = "";
  loading.value = true;
  hasContent.value = false;
  if (!host.value) {
    loading.value = false;
    return;
  }
  abort?.abort();
  abort = new AbortController();
  try {
    const res = await fetch(url, { signal: abort.signal });
    if (!res.ok) {
      const body = (await res.text()).slice(0, 280);
      // 415/404 often mean bad path (e.g. mojibake Chinese zip names) or wrong type
      throw new Error(
        res.status === 404
          ? t("preview.docxNotFound")
          : res.status === 415
            ? t("preview.docxUnsupported")
            : `HTTP ${res.status}${body ? `: ${body}` : ""}`
      );
    }
    const buf = await res.arrayBuffer();
    if (buf.byteLength < 4) {
      throw new Error(t("preview.docxEmpty"));
    }
    // Clear only after bytes ready to reduce flash
    host.value.innerHTML = "";
    await renderAsync(buf, host.value, undefined, {
      className: "docx-preview-body",
      inWrapper: true,
      ignoreWidth: false,
      ignoreHeight: false,
      breakPages: true,
      renderHeaders: true,
      renderFooters: true,
      renderFootnotes: true,
      renderEndnotes: true,
    });
    hasContent.value = true;
  } catch (e) {
    if ((e as Error)?.name === "AbortError") return;
    error.value = e instanceof Error ? e.message : String(e);
    hasContent.value = false;
  } finally {
    loading.value = false;
  }
}

function onWheel(e: WheelEvent) {
  // Ctrl/Cmd + wheel (trackpad pinch often sets ctrlKey on browsers)
  if (!(e.ctrlKey || e.metaKey)) return;
  e.preventDefault();
  e.stopPropagation();
  const factor = e.deltaY > 0 ? 0.9 : 1.1;
  // Max 800% (= ×8), same as PDF / image preview
  const next = Math.min(8, Math.max(0.25, zoom.value * factor));
  if (Math.abs(next - zoom.value) < 0.001) return;
  zoom.value = next;
  applyZoomStyle();
}

function zoomBy(factor: number) {
  zoom.value = Math.min(8, Math.max(0.25, zoom.value * factor));
  applyZoomStyle();
}

function zoomReset() {
  zoom.value = 1;
  applyZoomStyle();
}

watch(
  () => props.url,
  (u) => {
    zoom.value = 1;
    applyZoomStyle();
    if (props.legacyDoc) {
      error.value = t("preview.docLegacyUnsupported");
      hasContent.value = false;
      if (host.value) host.value.innerHTML = "";
      return;
    }
    if (u) void render(u);
    else {
      hasContent.value = false;
      if (host.value) host.value.innerHTML = "";
    }
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  abort?.abort();
});
</script>

<template>
  <div class="docx-host" @wheel="onWheel">
    <div class="docx-toolbar">
      <button type="button" class="mini secondary" @click="zoomBy(0.9)">−</button>
      <span class="zoom-label">{{ zoomPct }}%</span>
      <button type="button" class="mini secondary" @click="zoomBy(1.1)">+</button>
      <button type="button" class="mini secondary" @click="zoomReset">
        {{ t("pdf.zoomReset") }}
      </button>
      <span class="hint muted">{{ t("pdf.zoomHint") }}</span>
    </div>
    <div v-if="legacyDoc" class="status-empty">
      {{ t("preview.docLegacyUnsupported") }}
    </div>
    <!-- Only show loading on initial open when nothing is painted yet (never on zoom) -->
    <div
      v-else-if="loading && !hasContent"
      class="status-empty"
    >
      {{ t("preview.loading") }}
    </div>
    <div v-if="error && !legacyDoc" class="error">{{ error }}</div>
    <div class="docx-scroll">
      <div ref="scaleWrap" class="docx-scale">
        <div ref="host" class="docx-render" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.docx-host {
  height: 100%;
  min-height: 0;
  overflow: auto;
  /* Viewer chrome (PDF-like); empty until pages render — not a "broken" state alone */
  background: #525659;
  display: flex;
  flex-direction: column;
}
.docx-toolbar {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 2;
  background: color-mix(in srgb, #3a3f44 92%, transparent);
  padding: 0.25rem 0.5rem;
  backdrop-filter: blur(4px);
}
.zoom-label {
  min-width: 3rem;
  text-align: center;
  font-size: 0.75rem;
  color: #e2e8f0;
}
.hint {
  font-size: 0.7rem;
  margin-left: 0.35rem;
}
.docx-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 1rem;
}
.docx-scale {
  transform-origin: top left;
  width: 100%;
}
.docx-render {
  min-height: 0;
}
.status-empty {
  color: #e2e8f0;
  padding: 1rem;
  font-size: 0.9rem;
}
.error {
  color: #fecaca;
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
}
.muted {
  color: #94a3b8;
}
:deep(.docx-preview-body) {
  background: #fff;
  color: #111;
  margin: 0 auto 1rem;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.35);
}
</style>

<script setup lang="ts">
/**
 * Image / SVG preview with Ctrl+scroll zoom (max 800%), pan via scrollbars.
 */
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";

const props = defineProps<{
  path: string;
  workUrl: string;
  zoneUrl?: string | null;
}>();

const { t } = useI18n();

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 8; // 800%

const zoom = ref(1);
const zoomPct = computed(() => Math.round(zoom.value * 100));
const host = ref<HTMLDivElement | null>(null);

function clampZoom(z: number) {
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
}

function zoomBy(factor: number) {
  zoom.value = clampZoom(zoom.value * factor);
}

function zoomReset() {
  zoom.value = 1;
}

function onWheel(e: WheelEvent) {
  if (!(e.ctrlKey || e.metaKey)) return;
  e.preventDefault();
  e.stopPropagation();
  const factor = e.deltaY > 0 ? 0.9 : 1.1;
  zoom.value = clampZoom(zoom.value * factor);
}

watch(
  () => [props.workUrl, props.zoneUrl, props.path] as const,
  () => {
    zoom.value = 1;
  },
  { immediate: true }
);

const isSvg = computed(() => /\.svg$/i.test(props.path || ""));
</script>

<template>
  <div class="image-preview">
    <div class="toolbar">
      <span class="path muted" :title="path">{{ path }}</span>
      <span v-if="isSvg" class="badge muted">SVG</span>
      <button type="button" class="mini secondary" @click="zoomBy(0.9)">−</button>
      <span class="zoom-label">{{ zoomPct }}%</span>
      <button type="button" class="mini secondary" @click="zoomBy(1.1)">+</button>
      <button type="button" class="mini secondary" @click="zoomReset">
        {{ t("pdf.zoomReset") }}
      </button>
      <span class="hint muted">{{ t("pdf.zoomHint") }}</span>
    </div>
    <div
      ref="host"
      class="viewport"
      @wheel="onWheel"
    >
      <div class="cols" :class="{ single: !zoneUrl }">
        <figure>
          <figcaption>{{ t("preview.workImage") }}</figcaption>
          <div class="img-frame">
            <img
              class="zoom-img"
              :src="workUrl"
              :alt="path"
              :style="{ transform: `scale(${zoom})` }"
              draggable="false"
            />
          </div>
        </figure>
        <figure v-if="zoneUrl">
          <figcaption>{{ t("preview.zoneImage") }}</figcaption>
          <div class="img-frame">
            <img
              class="zoom-img"
              :src="zoneUrl"
              :alt="path"
              :style="{ transform: `scale(${zoom})` }"
              draggable="false"
            />
          </div>
        </figure>
      </div>
    </div>
  </div>
</template>

<style scoped>
.image-preview {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  padding: 0.25rem 0.45rem;
  border-bottom: 1px solid var(--border);
  background: var(--panel-header);
  flex-shrink: 0;
  font-size: 0.75rem;
}
.path {
  margin: 0;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 0.25rem;
}
.badge {
  font-size: 0.65rem;
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0.05rem 0.3rem;
}
.zoom-label {
  min-width: 2.8rem;
  text-align: center;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}
.hint {
  margin-left: 0.25rem;
}
.viewport {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
  padding: 0.5rem;
}
.cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  min-height: 0;
  align-items: start;
}
.cols.single {
  grid-template-columns: 1fr;
}
figure {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  min-width: 0;
  background: #0b0f14;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.5rem;
  overflow: auto;
}
figcaption {
  font-size: 0.72rem;
  color: var(--muted);
  flex-shrink: 0;
}
.img-frame {
  overflow: visible;
  display: flex;
  justify-content: flex-start;
  align-items: flex-start;
  min-height: 4rem;
  background: repeating-conic-gradient(#1a2332 0% 25%, #0f1419 0% 50%) 50% /
    16px 16px;
}
.zoom-img {
  max-width: 100%;
  height: auto;
  object-fit: contain;
  transform-origin: top left;
  transition: none;
  user-select: none;
  /* SVG: keep crisp when scaled via CSS */
  image-rendering: auto;
}
</style>

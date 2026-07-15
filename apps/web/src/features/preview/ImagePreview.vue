<script setup lang="ts">
import { useI18n } from "vue-i18n";

defineProps<{
  path: string;
  workUrl: string;
  zoneUrl?: string | null;
}>();

const { t } = useI18n();
</script>

<template>
  <div class="image-preview">
    <p class="path muted">{{ path }}</p>
    <div class="cols" :class="{ single: !zoneUrl }">
      <figure>
        <figcaption>{{ t("preview.workImage") }}</figcaption>
        <img :src="workUrl" :alt="path" />
      </figure>
      <figure v-if="zoneUrl">
        <figcaption>{{ t("preview.zoneImage") }}</figcaption>
        <img :src="zoneUrl" :alt="path" />
      </figure>
    </div>
  </div>
</template>

<style scoped>
.image-preview {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.75rem;
  min-height: 0;
  overflow: auto;
  height: 100%;
}
.path {
  margin: 0;
  font-size: 0.8rem;
}
.cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  min-height: 0;
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
}
figcaption {
  font-size: 0.72rem;
  color: var(--muted);
}
img {
  max-width: 100%;
  max-height: 70vh;
  object-fit: contain;
  background: repeating-conic-gradient(#1a2332 0% 25%, #0f1419 0% 50%) 50% /
    16px 16px;
}
</style>

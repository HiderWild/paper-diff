<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { renderAsync } from "docx-preview";

const { t } = useI18n();
const props = defineProps<{
  url: string | null;
  /** legacy .doc not supported by pure frontend render */
  legacyDoc?: boolean;
}>();

const host = ref<HTMLDivElement | null>(null);
const error = ref("");
const loading = ref(false);
let abort: AbortController | null = null;

async function render(url: string) {
  error.value = "";
  loading.value = true;
  if (!host.value) {
    loading.value = false;
    return;
  }
  host.value.innerHTML = "";
  abort?.abort();
  abort = new AbortController();
  try {
    const res = await fetch(url, { signal: abort.signal });
    if (!res.ok) throw new Error(await res.text());
    const buf = await res.arrayBuffer();
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
  } catch (e) {
    if ((e as Error)?.name === "AbortError") return;
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.url,
  (u) => {
    if (props.legacyDoc) {
      error.value = t("preview.docLegacyUnsupported");
      if (host.value) host.value.innerHTML = "";
      return;
    }
    if (u) void render(u);
    else if (host.value) host.value.innerHTML = "";
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  abort?.abort();
});
</script>

<template>
  <div class="docx-host">
    <div v-if="legacyDoc" class="status-empty">
      {{ t("preview.docLegacyUnsupported") }}
    </div>
    <div v-else-if="loading" class="status-empty">{{ t("preview.loading") }}</div>
    <div v-if="error && !legacyDoc" class="error">{{ error }}</div>
    <div ref="host" class="docx-scroll" />
  </div>
</template>

<style scoped>
.docx-host {
  height: 100%;
  min-height: 0;
  overflow: auto;
  background: #525659;
}
.docx-scroll {
  min-height: 100%;
  padding: 1rem;
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
:deep(.docx-preview-body) {
  background: #fff;
  color: #111;
  margin: 0 auto 1rem;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.35);
}
</style>

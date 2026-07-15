<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { marked } from "marked";

const props = defineProps<{
  content: string;
  path?: string;
  /** When true, allow toggling to source (parent hosts Monaco source) */
  showToggle?: boolean;
}>();

const emit = defineEmits<{
  "update:mode": [mode: "preview" | "source"];
}>();

const { t } = useI18n();
const mode = ref<"preview" | "source">("preview");

const html = computed(() => {
  try {
    marked.setOptions({ gfm: true, breaks: false });
    return marked.parse(props.content || "") as string;
  } catch (e) {
    return `<pre class="err">${e instanceof Error ? e.message : String(e)}</pre>`;
  }
});

watch(mode, (m) => emit("update:mode", m));
</script>

<template>
  <div class="md-host">
    <div v-if="showToggle !== false" class="md-toolbar">
      <span v-if="path" class="path muted" :title="path">{{ path }}</span>
      <div class="seg">
        <button
          type="button"
          class="mini secondary"
          :class="{ active: mode === 'preview' }"
          @click="mode = 'preview'"
        >
          {{ t("viewer.mdPreview") }}
        </button>
        <button
          type="button"
          class="mini secondary"
          :class="{ active: mode === 'source' }"
          @click="mode = 'source'"
        >
          {{ t("viewer.mdSource") }}
        </button>
      </div>
    </div>
    <div v-show="mode === 'preview'" class="md-scroll">
      <article class="md-body" v-html="html" />
    </div>
    <div v-show="mode === 'source'" class="md-source-slot">
      <slot name="source" />
    </div>
  </div>
</template>

<style scoped>
.md-host {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel);
}
.md-toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid var(--border);
  background: var(--panel-header);
  flex-shrink: 0;
  font-size: 0.75rem;
}
.path {
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.seg {
  margin-left: auto;
  display: flex;
  gap: 0.25rem;
}
.seg .active {
  border-color: var(--accent);
  color: var(--text);
}
.md-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 1rem 1.25rem 2rem;
}
.md-source-slot {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.md-body {
  max-width: 48rem;
  margin: 0 auto;
  color: var(--text);
  line-height: 1.55;
  font-size: 0.92rem;
}
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3) {
  margin: 1.1em 0 0.45em;
  line-height: 1.25;
}
.md-body :deep(p) {
  margin: 0.6em 0;
}
.md-body :deep(pre) {
  background: var(--surface-deep);
  padding: 0.65rem 0.75rem;
  border-radius: 6px;
  overflow: auto;
  font-size: 0.82rem;
}
.md-body :deep(code) {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.88em;
}
.md-body :deep(p code),
.md-body :deep(li code) {
  background: var(--surface-deep);
  padding: 0.1em 0.3em;
  border-radius: 3px;
}
.md-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.75em 0;
  font-size: 0.85rem;
}
.md-body :deep(th),
.md-body :deep(td) {
  border: 1px solid var(--border);
  padding: 0.35rem 0.5rem;
}
.md-body :deep(blockquote) {
  margin: 0.6em 0;
  padding-left: 0.85rem;
  border-left: 3px solid var(--accent);
  color: var(--muted);
}
.md-body :deep(a) {
  color: var(--accent);
}
.muted {
  color: var(--muted);
}
</style>

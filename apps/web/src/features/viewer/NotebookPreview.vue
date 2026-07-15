<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { marked } from "marked";
import {
  parseNotebook,
  stripAnsi,
  type NotebookCell,
  type NotebookOutput,
} from "./parseNotebook";

const props = defineProps<{
  content: string;
  path?: string;
}>();

const emit = defineEmits<{
  "update:mode": [mode: "notebook" | "source"];
}>();

const { t } = useI18n();
const mode = ref<"notebook" | "source">("notebook");

const notebook = computed(() => parseNotebook(props.content || ""));

function mdHtml(src: string): string {
  try {
    marked.setOptions({ gfm: true, breaks: false });
    return marked.parse(src || "") as string;
  } catch (e) {
    return `<pre>${e instanceof Error ? e.message : String(e)}</pre>`;
  }
}

function cellLang(c: NotebookCell): string {
  return (c.language || "python").toLowerCase();
}

function outputImageSrc(o: NotebookOutput): string | null {
  if (o.type !== "display" && o.type !== "execute_result") return null;
  if (o.imagePng) return `data:image/png;base64,${o.imagePng}`;
  if (o.imageJpeg) return `data:image/jpeg;base64,${o.imageJpeg}`;
  return null;
}

watch(mode, (m) => emit("update:mode", m));
</script>

<template>
  <div class="nb-host">
    <div class="nb-toolbar">
      <span v-if="path" class="path muted" :title="path">{{ path }}</span>
      <span class="badge muted">
        {{
          t("viewer.notebookMeta", {
            n: notebook.cells.length,
            lang: notebook.language || "?",
          })
        }}
      </span>
      <div class="seg">
        <button
          type="button"
          class="mini secondary"
          :class="{ active: mode === 'notebook' }"
          @click="mode = 'notebook'"
        >
          {{ t("viewer.notebookView") }}
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

    <div v-show="mode === 'notebook'" class="nb-scroll">
      <p v-if="notebook.error" class="empty error">
        {{ t("viewer.notebookParseError") }}: {{ notebook.error }}
      </p>
      <p v-else-if="!notebook.cells.length" class="empty muted">
        {{ t("viewer.notebookEmpty") }}
      </p>
      <article
        v-for="cell in notebook.cells"
        :key="cell.id || cell.index"
        class="cell"
        :class="cell.kind"
      >
        <div class="cell-gutter">
          <span v-if="cell.kind === 'code'" class="exec">
            [{{ cell.executionCount ?? " " }}]
          </span>
          <span v-else class="kind-tag">{{ cell.kind }}</span>
        </div>
        <div class="cell-body">
          <div
            v-if="cell.kind === 'markdown'"
            class="md-body"
            v-html="mdHtml(cell.source)"
          />
          <pre v-else class="code" :data-lang="cellLang(cell)"><code>{{
            cell.source
          }}</code></pre>

          <div
            v-if="cell.kind === 'code' && cell.outputs.length"
            class="outputs"
          >
            <div
              v-for="(o, oi) in cell.outputs"
              :key="oi"
              class="out"
              :class="o.type"
            >
              <pre v-if="o.type === 'stream'" class="stream" :class="o.name">{{
                o.text
              }}</pre>
              <pre v-else-if="o.type === 'error'" class="err">
{{ o.ename }}: {{ o.evalue }}
{{ o.traceback.map(stripAnsi).join("\n") }}</pre
              >
              <template v-else>
                <img
                  v-if="outputImageSrc(o)"
                  class="out-img"
                  :src="outputImageSrc(o)!"
                  alt="cell output"
                />
                <div
                  v-else-if="o.html"
                  class="out-html"
                  v-html="o.html"
                />
                <pre v-else-if="o.text" class="stream">{{ o.text }}</pre>
                <pre v-else class="muted tiny">
{{ t("viewer.notebookMime", { keys: o.dataKeys.join(", ") }) }}</pre
                >
              </template>
            </div>
          </div>
        </div>
      </article>
    </div>

    <div v-show="mode === 'source'" class="source-slot">
      <slot name="source" />
    </div>
  </div>
</template>

<style scoped>
.nb-host {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel);
}
.nb-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
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
.badge {
  font-size: 0.65rem;
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0.05rem 0.3rem;
}
.seg {
  margin-left: auto;
  display: flex;
  gap: 0.25rem;
}
.seg .active {
  border-color: var(--accent);
}
.nb-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 0.75rem 1rem 2rem;
}
.cell {
  display: flex;
  gap: 0.5rem;
  margin: 0 0 0.85rem;
  max-width: 56rem;
}
.cell-gutter {
  flex: 0 0 2.4rem;
  text-align: right;
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.72rem;
  color: var(--muted);
  padding-top: 0.35rem;
  user-select: none;
}
.kind-tag {
  text-transform: uppercase;
  font-size: 0.6rem;
  letter-spacing: 0.04em;
}
.cell-body {
  flex: 1 1 auto;
  min-width: 0;
}
.code {
  margin: 0;
  padding: 0.55rem 0.7rem;
  background: var(--surface-deep);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: auto;
  font-size: 0.82rem;
  line-height: 1.45;
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
.outputs {
  margin-top: 0.35rem;
  border-left: 2px solid color-mix(in srgb, var(--accent) 45%, var(--border));
  padding-left: 0.55rem;
}
.stream,
.err {
  margin: 0.15rem 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.8rem;
  font-family: ui-monospace, Menlo, Consolas, monospace;
}
.err {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 8%, transparent);
  padding: 0.35rem 0.45rem;
  border-radius: 4px;
}
.stream.stderr {
  color: var(--danger);
}
.out-img {
  max-width: 100%;
  height: auto;
  display: block;
  margin: 0.25rem 0;
  border-radius: 4px;
}
.out-html {
  overflow: auto;
  font-size: 0.85rem;
}
.md-body {
  color: var(--text);
  line-height: 1.55;
  font-size: 0.9rem;
}
.md-body :deep(h1),
.md-body :deep(h2),
.md-body :deep(h3) {
  margin: 0.6em 0 0.35em;
}
.md-body :deep(p) {
  margin: 0.4em 0;
}
.md-body :deep(pre) {
  background: var(--surface-deep);
  padding: 0.5rem 0.65rem;
  border-radius: 6px;
  overflow: auto;
}
.md-body :deep(code) {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 0.88em;
}
.source-slot {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.empty {
  padding: 1rem;
  font-size: 0.85rem;
}
.empty.error {
  color: var(--danger);
}
.muted {
  color: var(--muted);
}
.tiny {
  font-size: 0.72rem;
}
</style>

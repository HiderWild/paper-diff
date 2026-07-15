<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import MonacoDiff from "./features/diff/MonacoDiff.vue";
import PdfPane from "./features/preview/PdfPane.vue";
import { useProjectStore } from "./stores/project";

const store = useProjectStore();
const {
  projectId,
  files,
  currentPath,
  pair,
  units,
  status,
  error,
  logText,
  pdfHref,
  busy,
  autoCompile,
  lastCompileErrors,
} = storeToRefs(store);

const unitFilter = ref<"all" | "sentence" | "word" | "hunk">("sentence");
const visibleUnits = computed(() => {
  if (unitFilter.value === "all") return units.value;
  return units.value.filter((u) => u.granularity === unitFilter.value);
});

const baseInput = ref<HTMLInputElement | null>(null);
const revisedInput = ref<HTMLInputElement | null>(null);
const gitRepo = ref("");
const gitBaseRef = ref("");
const gitRevisedRef = ref("");
const gitSubdir = ref("");
const diffRef = ref<InstanceType<typeof MonacoDiff> | null>(null);

watch(
  () => pair.value?.merged.content,
  (c) => {
    if (c != null) diffRef.value?.setLeftContent(c);
  }
);

async function onUpload() {
  const baseFile = baseInput.value?.files?.[0];
  const revFile = revisedInput.value?.files?.[0];
  if (!baseFile || !revFile) {
    store.error = "Select base.zip and revised.zip";
    return;
  }
  await store.doUpload(baseFile, revFile);
}

async function onGitImport() {
  if (!gitRepo.value || !gitBaseRef.value || !gitRevisedRef.value) {
    store.error = "Fill repo path/url and both refs";
    return;
  }
  await store.doGitImport({
    repo_url: gitRepo.value,
    base_ref: gitBaseRef.value,
    revised_ref: gitRevisedRef.value,
    subdir: gitSubdir.value || undefined,
  });
}

async function onAccept(unit: (typeof units.value)[0]) {
  const content = await store.doAccept(unit);
  if (content != null) diffRef.value?.setLeftContent(content);
}

async function onAcceptAll() {
  const content = await store.doAcceptAll();
  if (content != null) diffRef.value?.setLeftContent(content);
}

async function onUndo() {
  const content = await store.doUndo();
  if (content != null) diffRef.value?.setLeftContent(content);
}

function onExport() {
  const u = store.exportUrl();
  if (u) window.open(u, "_blank");
}

function onReport() {
  const u = store.reportUrl();
  if (u) window.open(u, "_blank");
}

function jumpError(err: {
  file?: string | null;
  line?: number | null;
  message: string;
}) {
  if (err.file) {
    const path = err.file.replace(/^\.\//, "").replace(/\\/g, "/");
    const match =
      files.value.find((f) => f.path === path) ||
      files.value.find((f) => path.endsWith(f.path));
    if (match) {
      void store.openFile(match.path).then(() => {
        if (err.line) setTimeout(() => diffRef.value?.revealLine(err.line!), 250);
      });
      return;
    }
  }
  if (err.line) diffRef.value?.revealLine(err.line);
}

function fileActions(path: string, status: string) {
  if (status === "added") return [{ label: "Add→merged", action: "add" as const }];
  if (status === "removed")
    return [{ label: "Delete from merged", action: "delete" as const }];
  if (status === "modified")
    return [{ label: "Replace all", action: "replace_all" as const }];
  return [];
}
</script>

<template>
  <div class="layout">
    <header class="toolbar">
      <span class="title">paper-diff</span>
      <label>
        base
        <input ref="baseInput" type="file" accept=".zip" />
      </label>
      <label>
        revised
        <input ref="revisedInput" type="file" accept=".zip" />
      </label>
      <button :disabled="busy" @click="onUpload">Import zips</button>
      <input
        v-model="gitRepo"
        placeholder="git repo path or URL"
        style="min-width: 10rem"
      />
      <input v-model="gitBaseRef" placeholder="base ref" style="width: 6rem" />
      <input
        v-model="gitRevisedRef"
        placeholder="revised ref"
        style="width: 6rem"
      />
      <input v-model="gitSubdir" placeholder="subdir" style="width: 4rem" />
      <button class="secondary" :disabled="busy" @click="onGitImport">
        Import git
      </button>
      <button class="secondary" :disabled="busy || !pair" @click="onAcceptAll">
        Accept file
      </button>
      <button class="secondary" :disabled="busy || !projectId" @click="onUndo">
        Undo
      </button>
      <button
        :disabled="busy || !projectId"
        @click="store.doCompile('latexmk')"
      >
        Compile
      </button>
      <button
        class="secondary"
        :disabled="busy || !projectId"
        @click="store.doCompile('latexdiff')"
      >
        latexdiff PDF
      </button>
      <button class="secondary" :disabled="!projectId" @click="onExport">
        Export merged
      </button>
      <button class="secondary" :disabled="!projectId" @click="onReport">
        Accept report
      </button>
      <label class="status" style="margin-left: 0.5rem">
        <input v-model="autoCompile" type="checkbox" />
        auto-compile
      </label>
      <select v-model="unitFilter">
        <option value="sentence">sentences</option>
        <option value="word">words</option>
        <option value="hunk">hunks</option>
        <option value="all">all units</option>
      </select>
      <span class="status">{{ status }}</span>
    </header>
    <p v-if="error" class="error" style="padding: 0 0.8rem">{{ error }}</p>
    <div class="main">
      <aside class="panel">
        <div class="panel-header">Files</div>
        <div class="file-list">
          <div v-for="f in files" :key="f.path" class="file-row">
            <button
              class="file-item"
              :class="{ active: f.path === currentPath }"
              @click="store.openFile(f.path)"
            >
              <span class="badge" :class="f.status">{{ f.status }}</span>
              <span>{{ f.path }}</span>
            </button>
            <div class="file-ops">
              <button
                v-for="a in fileActions(f.path, f.status)"
                :key="a.action"
                class="secondary mini"
                :disabled="busy"
                @click="store.doAcceptFile(f.path, a.action)"
              >
                {{ a.label }}
              </button>
            </div>
          </div>
        </div>
        <div v-if="lastCompileErrors.length" class="err-list">
          <div class="panel-header">Compile errors</div>
          <button
            v-for="(e, i) in lastCompileErrors"
            :key="i"
            class="file-item err-item"
            @click="jumpError(e)"
          >
            {{ e.file || "?" }}:{{ e.line || "?" }} — {{ e.message }}
          </button>
        </div>
      </aside>
      <section class="panel">
        <div class="panel-header">Diff — left: merged · right: revised</div>
        <div class="unit-bar">
          <button
            v-for="u in visibleUnits"
            :key="u.id"
            class="unit-chip"
            :class="u.granularity"
            :title="`${u.leftText} → ${u.rightText}`"
            :disabled="busy"
            @click="onAccept(u)"
          >
            Accept {{ u.granularity }}
          </button>
          <span v-if="!visibleUnits.length" style="color: var(--muted)">
            No units (open a modified file)
          </span>
        </div>
        <MonacoDiff
          v-if="pair"
          ref="diffRef"
          :key="currentPath || 'x'"
          :path="currentPath || ''"
          :left="pair.merged.content"
          :right="pair.revised.content"
          @units="store.units = $event"
        />
      </section>
      <section class="panel">
        <div class="panel-header">PDF preview</div>
        <PdfPane :url="pdfHref" />
        <div class="log-box">{{ logText || "Compile log…" }}</div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.file-row {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  margin-bottom: 0.25rem;
}
.file-ops {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  padding-left: 0.5rem;
}
button.mini {
  font-size: 0.7rem;
  padding: 0.15rem 0.4rem;
}
.err-list {
  border-top: 1px solid var(--border);
  max-height: 180px;
  overflow: auto;
}
.err-item {
  color: var(--danger);
  font-size: 0.75rem;
  white-space: normal;
}
</style>

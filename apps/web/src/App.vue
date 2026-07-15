<script setup lang="ts">
import { computed, ref } from "vue";
import MonacoDiff from "./features/diff/MonacoDiff.vue";
import PdfPane from "./features/preview/PdfPane.vue";
import type { DiffUnit } from "./features/diff/sentenceMapper";
import {
  acceptAll,
  acceptOps,
  compileProject,
  createProject,
  exportMergedUrl,
  getCompileJob,
  getCompileLog,
  getDiffIndex,
  getFilePair,
  importGit,
  pdfUrl,
  undo,
  uploadVersions,
  type DiffIndexFile,
  type FilePair,
} from "./shared/api";

const projectId = ref<string | null>(null);
const files = ref<DiffIndexFile[]>([]);
const currentPath = ref<string | null>(null);
const pair = ref<FilePair | null>(null);
const units = ref<DiffUnit[]>([]);
const status = ref("Ready");
const error = ref("");
const logText = ref("");
const pdfHref = ref<string | null>(null);
const diffRef = ref<InstanceType<typeof MonacoDiff> | null>(null);
const busy = ref(false);

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


async function ensureProject() {
  if (!projectId.value) {
    const p = await createProject();
    projectId.value = p.id;
  }
  return projectId.value!;
}

async function onUpload() {
  error.value = "";
  busy.value = true;
  try {
    const baseFile = baseInput.value?.files?.[0];
    const revFile = revisedInput.value?.files?.[0];
    if (!baseFile || !revFile) {
      error.value = "Select base.zip and revised.zip";
      return;
    }
    const id = await ensureProject();
    status.value = "Uploading…";
    await uploadVersions(id, baseFile, revFile);
    status.value = `Project ${id}`;
    await refreshIndex();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function onGitImport() {
  error.value = "";
  busy.value = true;
  try {
    if (!gitRepo.value || !gitBaseRef.value || !gitRevisedRef.value) {
      error.value = "Fill repo path/url and both refs";
      return;
    }
    const id = await ensureProject();
    status.value = "Importing from git…";
    await importGit(id, {
      repo_url: gitRepo.value,
      base_ref: gitBaseRef.value,
      revised_ref: gitRevisedRef.value,
      subdir: gitSubdir.value || undefined,
    });
    status.value = `Project ${id} (git)`;
    await refreshIndex();
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}


async function refreshIndex() {
  if (!projectId.value) return;
  const idx = await getDiffIndex(projectId.value);
  files.value = idx.files.filter((f) => f.kind === "text" || f.status !== "same");
  const first =
    files.value.find((f) => f.status === "modified") || files.value[0];
  if (first) await openFile(first.path);
}

async function openFile(path: string) {
  if (!projectId.value) return;
  currentPath.value = path;
  pair.value = await getFilePair(projectId.value, path);
  units.value = [];
  status.value = path;
}

async function onAccept(unit: DiffUnit) {
  if (!projectId.value || !pair.value || !currentPath.value) return;
  busy.value = true;
  error.value = "";
  try {
    const res = await acceptOps(projectId.value, [
      {
        op_id: unit.id,
        file: currentPath.value,
        granularity: unit.granularity,
        left_range: unit.left,
        right_range: unit.right,
        expected_merged_revision: pair.value.merged.revision,
      },
    ]);
    pair.value = {
      ...pair.value,
      merged: {
        content: res.merged.content,
        sha256: res.merged.sha256,
        revision: res.merged.revision,
      },
    };
    diffRef.value?.setLeftContent(res.merged.content);
    status.value = `Accepted ${unit.granularity} → rev ${res.merged.revision}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function onAcceptAll() {
  if (!projectId.value || !pair.value || !currentPath.value) return;
  busy.value = true;
  try {
    const res = await acceptAll(
      projectId.value,
      currentPath.value,
      pair.value.merged.revision
    );
    pair.value = {
      ...pair.value,
      merged: {
        ...pair.value.merged,
        content: res.merged.content,
        revision: res.merged.revision,
      },
    };
    diffRef.value?.setLeftContent(res.merged.content);
    status.value = `Accepted all → rev ${res.merged.revision}`;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function onUndo() {
  if (!projectId.value) return;
  busy.value = true;
  try {
    const res = await undo(projectId.value, 1);
    if (pair.value && res.file === currentPath.value) {
      pair.value = {
        ...pair.value,
        merged: {
          ...pair.value.merged,
          content: res.merged.content,
          revision: res.merged.revision,
        },
      };
      diffRef.value?.setLeftContent(res.merged.content);
    }
    status.value = "Undo ok";
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

async function onCompile() {
  if (!projectId.value) return;
  busy.value = true;
  error.value = "";
  logText.value = "Compiling…\n";
  try {
    const { job_id } = await compileProject(projectId.value);
    const job = await getCompileJob(projectId.value, job_id);
    logText.value += `status=${job.status}\n`;
    if (job.message) logText.value += job.message + "\n";
    if (job.errors?.length) {
      logText.value += job.errors.map((e) => e.message).join("\n") + "\n";
    }
    try {
      logText.value += await getCompileLog(projectId.value, job_id);
    } catch {
      /* log optional */
    }
    if (job.status === "succeeded") {
      pdfHref.value = pdfUrl(projectId.value, job_id) + `&t=${Date.now()}`;
      status.value = "Compile OK";
    } else {
      status.value = "Compile failed";
      error.value = job.message || "compile failed";
    }

  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}

function onExport() {
  if (!projectId.value) return;
  window.open(exportMergedUrl(projectId.value), "_blank");
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
        style="min-width: 12rem"
      />
      <input v-model="gitBaseRef" placeholder="base ref" style="width: 7rem" />
      <input
        v-model="gitRevisedRef"
        placeholder="revised ref"
        style="width: 7rem"
      />
      <input v-model="gitSubdir" placeholder="subdir" style="width: 5rem" />
      <button class="secondary" :disabled="busy" @click="onGitImport">
        Import git
      </button>
      <button class="secondary" :disabled="busy || !pair" @click="onAcceptAll">
        Accept file
      </button>

      <button class="secondary" :disabled="busy || !projectId" @click="onUndo">
        Undo
      </button>
      <button :disabled="busy || !projectId" @click="onCompile">Compile</button>
      <button class="secondary" :disabled="!projectId" @click="onExport">
        Export merged
      </button>
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
          <button
            v-for="f in files"
            :key="f.path"
            class="file-item"
            :class="{ active: f.path === currentPath }"
            @click="openFile(f.path)"
          >
            <span class="badge" :class="f.status">{{ f.status }}</span>
            <span>{{ f.path }}</span>
          </button>
        </div>
      </aside>
      <section class="panel">
        <div class="panel-header">
          Diff — left: merged · right: revised
        </div>
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
          <span v-if="!visibleUnits.length" style="color: var(--muted)"
            >No units (open a modified file)</span
          >
        </div>
        <MonacoDiff
          v-if="pair"
          ref="diffRef"
          :key="currentPath || 'x'"
          :path="currentPath || ''"
          :left="pair.merged.content"
          :right="pair.revised.content"
          @units="units = $event"
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

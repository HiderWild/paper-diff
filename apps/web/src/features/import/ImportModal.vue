<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import {
  defaultImportName,
  listZipEntryPaths,
  pathsFromFileList,
} from "./zipList";
import type { DryRunImportResult } from "../../shared/api";

export type ImportMethod = "zip" | "folder" | "files";
export type ImportTarget = "project" | "zone";

const props = defineProps<{
  open: boolean;
  target: ImportTarget;
  busy?: boolean;
  /** Optional server dry-run for project supplement (zone uses local preview only). */
  serverDryRun?: DryRunImportResult | null;
}>();

const emit = defineEmits<{
  close: [];
  confirm: [
    payload: {
      target: ImportTarget;
      method: ImportMethod;
      name: string;
      files: File[];
      paths: string[];
      zip?: File | null;
      advanced?: "dual" | "git" | "supplement" | null;
      baseZip?: File | null;
      revisedZip?: File | null;
      git?: {
        repo_url: string;
        base_ref: string;
        revised_ref: string;
        subdir?: string;
      };
    },
  ];
  analyze: [paths: string[]];
}>();

const { t } = useI18n();

const method = ref<ImportMethod>("zip");
/** standard | advanced-dual | advanced-git | supplement */
const modeExtra = ref<"standard" | "dual" | "git" | "supplement">("standard");
const name = ref(defaultImportName());
const zipFile = ref<File | null>(null);
const baseZip = ref<File | null>(null);
const revisedZip = ref<File | null>(null);
const fileList = ref<File[]>([]);
const paths = ref<string[]>([]);
const analyzing = ref(false);
const localError = ref("");
const previewReady = ref(false);
const showAdvanced = ref(false);
const gitRepo = ref("");
const gitBase = ref("main");
const gitRevised = ref("HEAD");
const gitSubdir = ref("");

const zipInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);
const filesInput = ref<HTMLInputElement | null>(null);

const title = computed(() =>
  props.target === "project"
    ? t("importModal.projectTitle")
    : t("importModal.zoneTitle")
);

const canConfirm = computed(() => {
  if (analyzing.value || props.busy || !name.value.trim()) return false;
  if (modeExtra.value === "git") {
    return !!(gitRepo.value && gitBase.value && gitRevised.value);
  }
  if (modeExtra.value === "dual") {
    return !!(baseZip.value && revisedZip.value);
  }
  return (
    previewReady.value && (paths.value.length > 0 || !!zipFile.value)
  );
});

const isFullProjectZip = computed(
  () =>
    props.target === "project" &&
    modeExtra.value === "standard" &&
    method.value === "zip" &&
    !!zipFile.value
);

const displayPaths = computed(() => paths.value.slice(0, 80));
const extraCount = computed(() =>
  Math.max(0, paths.value.length - displayPaths.value.length)
);

const conflictCount = computed(
  () => props.serverDryRun?.conflicts?.length ?? 0
);
const newCount = computed(() => {
  if (props.serverDryRun) return props.serverDryRun.new_files?.length ?? 0;
  return paths.value.length;
});

watch(
  () => props.open,
  (v) => {
    if (v) reset();
  }
);

function reset() {
  method.value = "zip";
  modeExtra.value =
    props.target === "zone" ? "standard" : "standard";
  name.value = defaultImportName();
  zipFile.value = null;
  baseZip.value = null;
  revisedZip.value = null;
  fileList.value = [];
  paths.value = [];
  analyzing.value = false;
  localError.value = "";
  previewReady.value = false;
  showAdvanced.value = false;
  gitRepo.value = "";
  gitBase.value = "main";
  gitRevised.value = "HEAD";
  gitSubdir.value = "";
  if (zipInput.value) zipInput.value.value = "";
  if (folderInput.value) folderInput.value.value = "";
  if (filesInput.value) filesInput.value.value = "";
}

function selectMethod(m: ImportMethod) {
  method.value = m;
  zipFile.value = null;
  fileList.value = [];
  paths.value = [];
  previewReady.value = false;
  localError.value = "";
}

async function onZipChange(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0] || null;
  zipFile.value = f;
  fileList.value = f ? [f] : [];
  paths.value = [];
  previewReady.value = false;
  localError.value = "";
  if (!f) return;
  analyzing.value = true;
  try {
    const listed = await listZipEntryPaths(f);
    paths.value = listed;
    previewReady.value = true;
    emit("analyze", listed);
  } catch (err) {
    localError.value = err instanceof Error ? err.message : String(err);
  } finally {
    analyzing.value = false;
  }
}

async function onFolderOrFiles(e: Event, m: "folder" | "files") {
  const list = (e.target as HTMLInputElement).files;
  if (!list?.length) return;
  zipFile.value = null;
  fileList.value = Array.from(list);
  paths.value = pathsFromFileList(list, m);
  previewReady.value = true;
  localError.value = "";
  emit("analyze", paths.value);
}

function confirm() {
  if (!canConfirm.value) return;
  if (isFullProjectZip.value) {
    const ok = window.confirm(t("importModal.replaceWarning"));
    if (!ok) return;
  }
  emit("confirm", {
    target:
      modeExtra.value === "supplement" ? "project" : props.target,
    method: method.value,
    name: name.value.trim(),
    files: fileList.value,
    paths: paths.value,
    zip: zipFile.value,
    advanced:
      modeExtra.value === "standard" ? null : modeExtra.value,
    baseZip: baseZip.value,
    revisedZip: revisedZip.value,
    git:
      modeExtra.value === "git"
        ? {
            repo_url: gitRepo.value,
            base_ref: gitBase.value,
            revised_ref: gitRevised.value,
            subdir: gitSubdir.value || undefined,
          }
        : undefined,
  });
}

function onBaseZip(e: Event) {
  baseZip.value = (e.target as HTMLInputElement).files?.[0] || null;
}
function onRevisedZip(e: Event) {
  revisedZip.value = (e.target as HTMLInputElement).files?.[0] || null;
}
</script>

<template>
  <div v-if="open" class="modal-overlay" @click.self="emit('close')">
    <div class="modal" role="dialog" :aria-label="title">
      <header class="modal-head">
        <h3>{{ title }}</h3>
        <button type="button" class="icon-x secondary mini" @click="emit('close')">
          ×
        </button>
      </header>

      <label class="field">
        <span>{{ t("importModal.name") }}</span>
        <input v-model="name" type="text" maxlength="80" autocomplete="off" />
      </label>

      <div v-if="target === 'zone' || target === 'project'" class="mode-extra">
        <button
          v-if="target === 'zone' || true"
          type="button"
          class="method-chip"
          :class="{ active: modeExtra === 'standard' }"
          @click="modeExtra = 'standard'"
        >
          {{ target === "project" ? t("importModal.modeProject") : t("importModal.modeZone") }}
        </button>
        <button
          v-if="target === 'zone' || target === 'project'"
          type="button"
          class="method-chip"
          :class="{ active: modeExtra === 'supplement' }"
          :disabled="target === 'project' && false"
          @click="modeExtra = 'supplement'; method = 'files'"
        >
          {{ t("importModal.modeSupplement") }}
        </button>
      </div>

      <div class="method-row" role="radiogroup" v-if="modeExtra === 'standard' || modeExtra === 'supplement'">
        <button
          type="button"
          class="method-chip"
          :class="{ active: method === 'zip' }"
          @click="selectMethod('zip')"
        >
          {{ t("importModal.methodZip") }}
        </button>
        <button
          type="button"
          class="method-chip"
          :class="{ active: method === 'folder' }"
          @click="selectMethod('folder')"
        >
          {{ t("importModal.methodFolder") }}
        </button>
        <button
          type="button"
          class="method-chip"
          :class="{ active: method === 'files' }"
          @click="selectMethod('files')"
        >
          {{ t("importModal.methodFiles") }}
        </button>
      </div>

      <div class="pick-area">
        <template v-if="method === 'zip'">
          <input
            ref="zipInput"
            type="file"
            accept=".zip,application/zip"
            @change="onZipChange"
          />
          <p v-if="zipFile" class="muted pick-name">{{ zipFile.name }}</p>
        </template>
        <template v-else-if="method === 'folder'">
          <input
            ref="folderInput"
            type="file"
            webkitdirectory
            multiple
            @change="onFolderOrFiles($event, 'folder')"
          />
        </template>
        <template v-else>
          <input
            ref="filesInput"
            type="file"
            multiple
            @change="onFolderOrFiles($event, 'files')"
          />
        </template>
      </div>

      <p v-if="analyzing" class="muted">{{ t("importModal.analyzing") }}</p>
      <p v-if="localError" class="error">{{ localError }}</p>
      <p v-if="isFullProjectZip" class="warn">
        {{ t("importModal.replaceHint") }}
      </p>
      <p v-if="target === 'zone' && modeExtra === 'standard'" class="muted">
        {{ t("importModal.zoneHint") }}
      </p>

      <section v-if="previewReady" class="preview">
        <h4>{{ t("importModal.preview") }}</h4>
        <p class="summary">
          {{
            t("importModal.previewSummary", {
              total: paths.length,
              fresh: newCount,
              conflicts: conflictCount,
            })
          }}
        </p>
        <ul v-if="displayPaths.length" class="path-list">
          <li v-for="p in displayPaths" :key="p">
            <code>{{ p }}</code>
          </li>
        </ul>
        <p v-if="extraCount" class="muted">
          {{ t("importModal.morePaths", { n: extraCount }) }}
        </p>
        <p
          v-if="serverDryRun?.conflict"
          class="warn"
        >
          {{ t("importModal.conflictNote") }}
        </p>
      </section>

      <button
        type="button"
        class="secondary mini adv-toggle"
        @click="showAdvanced = !showAdvanced"
      >
        {{ t("importModal.advanced") }}
      </button>
      <div v-if="showAdvanced" class="advanced-box">
        <button
          type="button"
          class="method-chip"
          :class="{ active: modeExtra === 'dual' }"
          @click="modeExtra = 'dual'"
        >
          {{ t("importModal.advancedDual") }}
        </button>
        <button
          type="button"
          class="method-chip"
          :class="{ active: modeExtra === 'git' }"
          @click="modeExtra = 'git'"
        >
          {{ t("importModal.advancedGit") }}
        </button>
        <div v-if="modeExtra === 'dual'" class="adv-fields">
          <label class="field">
            {{ t("toolbar.base") }}
            <input type="file" accept=".zip" @change="onBaseZip" />
          </label>
          <label class="field">
            {{ t("toolbar.revised") }}
            <input type="file" accept=".zip" @change="onRevisedZip" />
          </label>
        </div>
        <div v-if="modeExtra === 'git'" class="adv-fields">
          <label class="field">
            {{ t("toolbar.gitRepoPlaceholder") }}
            <input v-model="gitRepo" type="text" />
          </label>
          <label class="field">
            {{ t("toolbar.baseRefPlaceholder") }}
            <input v-model="gitBase" type="text" />
          </label>
          <label class="field">
            {{ t("toolbar.revisedRefPlaceholder") }}
            <input v-model="gitRevised" type="text" />
          </label>
          <label class="field">
            {{ t("toolbar.subdirPlaceholder") }}
            <input v-model="gitSubdir" type="text" />
          </label>
          <p class="hint">{{ t("importModal.gitLocalHint") }}</p>
        </div>
      </div>

      <footer class="modal-actions">
        <button type="button" class="secondary" @click="emit('close')">
          {{ t("importModal.cancel") }}
        </button>
        <button
          type="button"
          :disabled="!canConfirm"
          @click="confirm"
        >
          {{ t("importModal.confirm") }}
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
}
.modal {
  background: var(--panel, #0f172a);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 1rem 1.1rem;
  width: min(520px, 96vw);
  max-height: 88vh;
  overflow: auto;
  color: var(--text);
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}
.modal-head h3 {
  margin: 0;
  font-size: 1.05rem;
}
.icon-x {
  width: 1.75rem;
  height: 1.75rem;
  padding: 0;
  font-size: 1.1rem;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  font-size: 0.85rem;
  margin-bottom: 0.75rem;
}
.field input {
  background: var(--input-bg, #1e293b);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.4rem 0.5rem;
}
.method-row {
  display: flex;
  gap: 0.4rem;
  margin-bottom: 0.75rem;
  flex-wrap: wrap;
}
.method-chip {
  flex: 1 1 auto;
  min-width: 5rem;
  background: var(--secondary-btn, #334155);
  color: var(--text);
  border: 1px solid transparent;
  padding: 0.4rem 0.5rem;
  font-size: 0.8rem;
}
.method-chip.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 28%, transparent);
}
.pick-area {
  margin-bottom: 0.75rem;
}
.pick-area input[type="file"] {
  font-size: 0.8rem;
  max-width: 100%;
}
.pick-name {
  margin: 0.35rem 0 0;
  font-size: 0.8rem;
}
.preview {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.6rem 0.75rem;
  margin-bottom: 0.75rem;
  background: var(--bg);
}
.preview h4 {
  margin: 0 0 0.35rem;
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
}
.summary {
  margin: 0 0 0.5rem;
  font-size: 0.85rem;
}
.path-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 9rem;
  overflow: auto;
  font-size: 0.75rem;
}
.path-list li {
  padding: 0.15rem 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
}
.path-list code {
  word-break: break-all;
}
.warn {
  color: #fbbf24;
  font-size: 0.8rem;
  margin: 0.4rem 0 0;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.75rem;
}
.error {
  color: var(--danger);
  font-size: 0.85rem;
}
.mode-extra {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
}
.adv-toggle {
  margin: 0.5rem 0;
}
.advanced-box {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.6rem;
  margin-bottom: 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.adv-fields {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.hint {
  font-size: 0.75rem;
  color: var(--muted);
  margin: 0;
}
</style>

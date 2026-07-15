<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import { useI18n } from "vue-i18n";
import MonacoDiff from "./features/diff/MonacoDiff.vue";
import PdfPane from "./features/preview/PdfPane.vue";
import FileTree from "./features/tree/FileTree.vue";
import { setLocale, type AppLocale } from "./i18n";
import { useLayoutStore } from "./stores/layout";
import { useProjectStore } from "./stores/project";

const { t, locale } = useI18n();
const store = useProjectStore();
const layout = useLayoutStore();
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
  rootFile,
  rootRecommended,
  rootCandidates,
  compareSummary,
  gitInfo,
  gitStatusText,
  zones,
  activeZoneId,
  gitCommits,
} = storeToRefs(store);

const {
  filesWidth,
  pdfWidth,
  bottomHeight,
  showFiles,
  showPdf,
  showBottom,
  showDotFiles,
  activity,
} = storeToRefs(layout);

const unitFilter = ref<"all" | "sentence" | "word" | "hunk">("sentence");
const visibleUnits = computed(() => {
  if (unitFilter.value === "all") return units.value;
  return units.value.filter((u) => u.granularity === unitFilter.value);
});

const workInput = ref<HTMLInputElement | null>(null);
const baseInput = ref<HTMLInputElement | null>(null);
const revisedInput = ref<HTMLInputElement | null>(null);
const zoneZipInput = ref<HTMLInputElement | null>(null);
const zoneFolderInput = ref<HTMLInputElement | null>(null);
const showAdvanced = ref(false);
const gitRepo = ref("");
const gitBaseRef = ref("");
const gitRevisedRef = ref("");
const gitSubdir = ref("");
const gitCommitMsg = ref("");
const diffRef = ref<InstanceType<typeof MonacoDiff> | null>(null);

const rootOptions = computed(() => {
  const paths = new Set<string>();
  for (const c of rootCandidates.value) paths.add(c.path);
  if (rootRecommended.value) paths.add(rootRecommended.value);
  if (rootFile.value) paths.add(rootFile.value);
  for (const f of files.value) {
    if (f.path.toLowerCase().endsWith(".tex")) paths.add(f.path);
  }
  return [...paths].sort();
});

const activeZoneName = computed(() => {
  const z = zones.value.find((x) => x.id === activeZoneId.value);
  return z?.name || "";
});

watch(
  () => pair.value?.merged.content,
  (c) => {
    if (c != null) diffRef.value?.setLeftContent(c);
  }
);

onBeforeUnmount(() => {
  store.stopPolling();
});

async function onImportWork() {
  const f = workInput.value?.files?.[0];
  if (!f) {
    store.error = t("errors.selectWorkZip");
    return;
  }
  await store.doImportWork(f);
  if (workInput.value) workInput.value.value = "";
}

async function onUpload() {
  const baseFile = baseInput.value?.files?.[0];
  const revFile = revisedInput.value?.files?.[0];
  if (!baseFile || !revFile) {
    store.error = t("errors.selectZips");
    return;
  }
  await store.doUpload(baseFile, revFile);
}

async function onGitImport() {
  if (!gitRepo.value || !gitBaseRef.value || !gitRevisedRef.value) {
    store.error = t("errors.fillGit");
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
        if (err.line)
          setTimeout(() => diffRef.value?.revealLine(err.line!), 250);
      });
      return;
    }
  }
  if (err.line) diffRef.value?.revealLine(err.line);
}

function granularityLabel(g: string) {
  if (g === "sentence" || g === "word" || g === "hunk") {
    return t(`units.${g}`);
  }
  return g;
}

function onLocaleChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value as AppLocale;
  setLocale(v);
}

function onRootChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value;
  if (v) void store.doSetRoot(v);
}

function startResize(kind: "files" | "pdf" | "bottom", ev: MouseEvent) {
  ev.preventDefault();
  const startX = ev.clientX;
  const startY = ev.clientY;
  const startFiles = filesWidth.value;
  const startPdf = pdfWidth.value;
  const startBottom = bottomHeight.value;

  function onMove(e: MouseEvent) {
    if (kind === "files") {
      filesWidth.value = Math.min(
        480,
        Math.max(160, startFiles + (e.clientX - startX))
      );
    } else if (kind === "pdf") {
      pdfWidth.value = Math.min(
        640,
        Math.max(200, startPdf - (e.clientX - startX))
      );
    } else {
      bottomHeight.value = Math.min(
        320,
        Math.max(72, startBottom - (e.clientY - startY))
      );
    }
  }
  function onUp() {
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  }
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

async function onGitCommit() {
  const msg = gitCommitMsg.value.trim() || t("git.commitPlaceholder");
  await store.doGitCommit(msg);
}

async function onGitDiscard() {
  if (!confirm(t("git.discardConfirm"))) return;
  await store.doGitDiscard();
}

function openActivity(a: "explorer" | "zones" | "git" | "compile") {
  activity.value = a;
  showFiles.value = true;
  if (a === "git") {
    void store.refreshGitStatus();
    void store.refreshGitLog();
  }
  if (a === "zones") void store.refreshZones();
}

async function onZoneZipSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  const f = input.files?.[0];
  if (!f) return;
  await store.doAddZoneZip(f);
  input.value = "";
}

async function onZoneFolderSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  if (!input.files?.length) return;
  await store.doAddZoneFiles(input.files);
  input.value = "";
}

async function onRenameZone(zoneId: string, current: string) {
  const name = window.prompt(t("zones.namePrompt"), current);
  if (name == null || !name.trim()) return;
  await store.doRenameZone(zoneId, name);
}

async function onDeleteZone(zoneId: string) {
  if (!confirm(t("zones.deleteConfirm"))) return;
  await store.doDeleteZone(zoneId);
}

function formatCommitDate(iso?: string) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}
</script>

<template>
  <div class="layout">
    <header class="toolbar">
      <span class="title">{{ t("app.title") }}</span>
      <label>
        {{ t("toolbar.importProject") }}
        <input ref="workInput" type="file" accept=".zip" />
      </label>
      <button :disabled="busy" @click="onImportWork">
        {{ t("toolbar.importWork") }}
      </button>
      <button
        class="secondary"
        type="button"
        :class="{ 'active-toggle': showAdvanced }"
        @click="showAdvanced = !showAdvanced"
      >
        {{ t("toolbar.advancedDualZip") }}
      </button>
      <template v-if="showAdvanced">
        <label>
          {{ t("toolbar.base") }}
          <input ref="baseInput" type="file" accept=".zip" />
        </label>
        <label>
          {{ t("toolbar.revised") }}
          <input ref="revisedInput" type="file" accept=".zip" />
        </label>
        <button class="secondary" :disabled="busy" @click="onUpload">
          {{ t("toolbar.importZips") }}
        </button>
        <input
          v-model="gitRepo"
          :placeholder="t('toolbar.gitRepoPlaceholder')"
          style="min-width: 8rem"
        />
        <input
          v-model="gitBaseRef"
          :placeholder="t('toolbar.baseRefPlaceholder')"
          style="width: 5rem"
        />
        <input
          v-model="gitRevisedRef"
          :placeholder="t('toolbar.revisedRefPlaceholder')"
          style="width: 5rem"
        />
        <input
          v-model="gitSubdir"
          :placeholder="t('toolbar.subdirPlaceholder')"
          style="width: 4rem"
        />
        <button class="secondary" :disabled="busy" @click="onGitImport">
          {{ t("toolbar.importGit") }}
        </button>
      </template>
      <label class="root-select" :title="t('toolbar.rootSelect')">
        <select
          :value="rootFile || ''"
          :disabled="!projectId"
          @change="onRootChange"
        >
          <option value="" disabled>
            {{ t("toolbar.rootPlaceholder") }}
          </option>
          <option v-for="p in rootOptions" :key="p" :value="p">
            {{ p
            }}{{
              p === rootRecommended
                ? ` ★ ${t("toolbar.rootRecommended")}`
                : ""
            }}
          </option>
        </select>
      </label>
      <button class="secondary" :disabled="busy || !pair" @click="onAcceptAll">
        {{ t("toolbar.acceptFile") }}
      </button>
      <button class="secondary" :disabled="busy || !projectId" @click="onUndo">
        {{ t("toolbar.undo") }}
      </button>
      <button
        :disabled="busy || !projectId || !rootFile"
        @click="store.doCompile('latexmk')"
      >
        {{ t("toolbar.compile") }}
      </button>
      <button
        class="secondary"
        :disabled="busy || !projectId || !rootFile"
        @click="store.doCompile('latexdiff')"
      >
        {{ t("toolbar.latexdiffPdf") }}
      </button>
      <button class="secondary" :disabled="!projectId" @click="onExport">
        {{ t("toolbar.exportWork") }}
      </button>
      <button class="secondary" :disabled="!projectId" @click="onReport">
        {{ t("toolbar.acceptReport") }}
      </button>
      <label class="status-inline">
        <input v-model="autoCompile" type="checkbox" />
        {{ t("toolbar.autoCompile") }}
      </label>
      <select v-model="unitFilter">
        <option value="sentence">{{ t("filter.sentences") }}</option>
        <option value="word">{{ t("filter.words") }}</option>
        <option value="hunk">{{ t("filter.hunks") }}</option>
        <option value="all">{{ t("filter.all") }}</option>
      </select>
      <button
        class="secondary"
        :class="{ 'active-toggle': showFiles }"
        :title="t('toolbar.toggleFiles')"
        @click="layout.toggleFiles()"
      >
        {{ t("toolbar.toggleFiles") }}
      </button>
      <button
        class="secondary"
        :class="{ 'active-toggle': showPdf }"
        :title="t('toolbar.togglePdf')"
        @click="layout.togglePdf()"
      >
        {{ t("toolbar.togglePdf") }}
      </button>
      <button
        class="secondary"
        :class="{ 'active-toggle': showBottom }"
        :title="t('toolbar.toggleBottom')"
        @click="layout.toggleBottom()"
      >
        {{ t("toolbar.toggleBottom") }}
      </button>
      <button class="secondary" @click="layout.reset()">
        {{ t("toolbar.resetLayout") }}
      </button>
      <label class="status-inline" :title="t('lang.switch')">
        <select :value="locale" style="width: auto" @change="onLocaleChange">
          <option value="zh-CN">{{ t("lang.zh") }}</option>
          <option value="en">{{ t("lang.en") }}</option>
        </select>
      </label>
      <span class="status">
        {{ status }}
        <template v-if="activeZoneName"> · {{ activeZoneName }}</template>
        <template v-if="compareSummary">
          · {{ compareSummary.ready }}/{{ compareSummary.total }}
        </template>
      </span>
    </header>

    <p v-if="error" class="error-bar">{{ error }}</p>

    <!-- Flex workbench: activity | [files] | editor | [pdf] -->
    <div class="workbench">
      <nav class="activity-bar" aria-label="activity">
        <button
          type="button"
          :class="{ active: activity === 'explorer' && showFiles }"
          :title="t('panels.explorer')"
          @click="openActivity('explorer')"
        >
          📂
        </button>
        <button
          type="button"
          :class="{ active: activity === 'zones' && showFiles }"
          :title="t('panels.zones')"
          @click="openActivity('zones')"
        >
          ⧉
        </button>
        <button
          type="button"
          :class="{ active: activity === 'git' && showFiles }"
          :title="t('panels.git')"
          @click="openActivity('git')"
        >
          ⎇
        </button>
        <button
          type="button"
          :class="{ active: activity === 'compile' && showFiles }"
          :title="t('panels.compile')"
          @click="openActivity('compile')"
        >
          ⚙
        </button>
      </nav>

      <aside
        v-if="showFiles"
        class="pane files-pane"
        :style="{ width: filesWidth + 'px', flex: '0 0 auto' }"
      >
        <template v-if="activity === 'explorer'">
          <FileTree
            :files="files"
            :current-path="currentPath"
            :show-dot-files="showDotFiles"
            :busy="busy"
            @update:show-dot-files="showDotFiles = $event"
            @open="store.openFile($event)"
            @action="(p, a) => store.doAcceptFile(p, a)"
            @compare-dir="store.doEnqueueDir($event)"
            @hide="layout.toggleFiles()"
          />
          <div v-if="lastCompileErrors.length" class="err-list">
            <div class="panel-header">{{ t("panels.compileErrors") }}</div>
            <button
              v-for="(e, i) in lastCompileErrors"
              :key="i"
              class="err-item"
              type="button"
              @click="jumpError(e)"
            >
              {{ e.file || "?" }}:{{ e.line || "?" }} — {{ e.message }}
            </button>
          </div>
        </template>

        <template v-else-if="activity === 'zones'">
          <div class="panel-header side-header">
            <span>{{ t("panels.zones") }}</span>
            <button
              type="button"
              class="header-hide"
              :title="t('toolbar.toggleFiles')"
              @click="layout.toggleFiles()"
            >
              ◀
            </button>
          </div>
          <div class="side-body">
            <div class="zone-actions">
              <button
                type="button"
                class="secondary mini"
                :disabled="busy || !projectId"
                @click="zoneZipInput?.click()"
              >
                {{ t("zones.fromZip") }}
              </button>
              <button
                type="button"
                class="secondary mini"
                :disabled="busy || !projectId"
                @click="zoneFolderInput?.click()"
              >
                {{ t("zones.fromFolder") }}
              </button>
              <button
                type="button"
                class="secondary mini"
                :disabled="busy || !projectId"
                @click="store.doZoneFromWork()"
              >
                {{ t("zones.fromWork") }}
              </button>
            </div>
            <input
              ref="zoneZipInput"
              type="file"
              accept=".zip"
              hidden
              @change="onZoneZipSelected"
            />
            <input
              ref="zoneFolderInput"
              type="file"
              webkitdirectory
              multiple
              hidden
              @change="onZoneFolderSelected"
            />
            <p v-if="!zones.length" class="muted">{{ t("zones.empty") }}</p>
            <ul class="zone-list">
              <li
                v-for="z in zones"
                :key="z.id"
                class="zone-item"
                :class="{ active: z.id === activeZoneId || z.active }"
              >
                <button
                  type="button"
                  class="zone-main"
                  :disabled="busy"
                  @click="store.doActivateZone(z.id)"
                >
                  <span class="zone-name">{{ z.name }}</span>
                  <span
                    v-if="z.id === activeZoneId || z.active"
                    class="badge modified"
                    >{{ t("zones.active") }}</span
                  >
                  <span v-if="z.file_count != null" class="zone-meta">{{
                    t("zones.fileCount", { n: z.file_count })
                  }}</span>
                </button>
                <div class="zone-ops">
                  <button
                    type="button"
                    class="mini secondary"
                    :disabled="busy"
                    @click="onRenameZone(z.id, z.name)"
                  >
                    {{ t("zones.rename") }}
                  </button>
                  <button
                    type="button"
                    class="mini secondary"
                    :disabled="busy"
                    @click="onDeleteZone(z.id)"
                  >
                    {{ t("zones.delete") }}
                  </button>
                </div>
              </li>
            </ul>
          </div>
        </template>

        <template v-else-if="activity === 'git'">
          <div class="panel-header side-header">
            <span>{{ t("panels.git") }}</span>
            <button
              type="button"
              class="header-hide"
              :title="t('toolbar.toggleFiles')"
              @click="layout.toggleFiles()"
            >
              ◀
            </button>
          </div>
          <div class="side-body">
            <p class="muted">
              {{
                gitInfo?.repo
                  ? `${gitInfo.repo}`
                  : t("git.unbound")
              }}
            </p>
            <p class="muted">{{ gitStatusText }}</p>
            <div class="zone-actions">
              <button
                class="secondary mini"
                type="button"
                :disabled="!projectId"
                @click="
                  () => {
                    store.refreshGitStatus();
                    store.refreshGitLog();
                  }
                "
              >
                {{ t("git.refresh") }}
              </button>
              <button
                class="secondary mini"
                type="button"
                :disabled="busy || !projectId"
                @click="onGitDiscard"
              >
                {{ t("git.discard") }}
              </button>
            </div>
            <label class="block-label">
              {{ t("git.commitMsg") }}
              <input
                v-model="gitCommitMsg"
                :placeholder="t('git.commitPlaceholder')"
              />
            </label>
            <button
              type="button"
              :disabled="busy || !projectId"
              @click="onGitCommit"
            >
              {{ t("git.commitBtn") }}
            </button>
            <div class="panel-header zone-subhead">{{ t("git.log") }}</div>
            <ul v-if="gitCommits.length" class="commit-list">
              <li v-for="c in gitCommits" :key="c.sha" class="commit-item">
                <code class="commit-sha">{{ c.short }}</code>
                <span class="commit-subj">{{ c.subject }}</span>
                <span class="commit-date">{{ formatCommitDate(c.date) }}</span>
              </li>
            </ul>
            <p v-else class="muted">—</p>
          </div>
        </template>

        <template v-else>
          <div class="panel-header side-header">
            <span>{{ t("panels.compile") }}</span>
            <button
              type="button"
              class="header-hide"
              :title="t('toolbar.toggleFiles')"
              @click="layout.toggleFiles()"
            >
              ◀
            </button>
          </div>
          <div class="side-body">
            <p class="muted">
              {{ t("toolbar.rootSelect") }}:
              {{ rootFile || t("toolbar.rootPlaceholder") }}
            </p>
            <button
              type="button"
              :disabled="busy || !projectId || !rootFile"
              @click="store.doCompile('latexmk')"
            >
              {{ t("toolbar.compile") }}
            </button>
            <button
              class="secondary"
              type="button"
              :disabled="busy || !projectId || !rootFile"
              @click="store.doCompile('latexdiff')"
            >
              {{ t("toolbar.latexdiffPdf") }}
            </button>
          </div>
        </template>
      </aside>
      <div
        v-if="showFiles"
        class="sash-v"
        title="resize"
        @mousedown="startResize('files', $event)"
      />

      <!-- Editor (always grows) -->
      <section class="pane editor-pane">
        <div class="panel-header">{{ t("panels.diffHeader") }}</div>
        <div class="unit-bar">
          <button
            v-for="u in visibleUnits"
            :key="u.id"
            class="unit-chip"
            :class="u.granularity"
            type="button"
            :title="`${u.leftText} → ${u.rightText}`"
            :disabled="busy"
            @click="onAccept(u)"
          >
            {{
              t("units.accept", {
                granularity: granularityLabel(u.granularity),
              })
            }}
          </button>
          <span v-if="!visibleUnits.length" class="muted-inline">
            {{ t("units.empty") }}
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
        <div v-else class="empty-editor">{{ t("tree.empty") }}</div>
      </section>

      <div
        v-if="showPdf"
        class="sash-v"
        title="resize"
        @mousedown="startResize('pdf', $event)"
      />

      <section
        v-if="showPdf"
        class="pane pdf-pane"
        :style="{ width: pdfWidth + 'px', flex: '0 0 auto' }"
      >
        <div class="panel-header side-header">
          <span>{{ t("panels.pdfPreview") }}</span>
          <button
            type="button"
            class="header-hide"
            :title="t('toolbar.togglePdf')"
            @click="layout.togglePdf()"
          >
            ▶
          </button>
        </div>
        <PdfPane :url="pdfHref" />
      </section>
    </div>

    <div
      v-if="showBottom"
      class="sash-h"
      title="resize"
      @mousedown="startResize('bottom', $event)"
    />
    <div
      v-if="showBottom"
      class="bottom-panel"
      :style="{ height: bottomHeight + 'px' }"
    >
      <div class="panel-header side-header">
        <span>{{ t("panels.bottomLog") }}</span>
        <button
          type="button"
          class="header-hide"
          :title="t('toolbar.toggleBottom')"
          @click="layout.toggleBottom()"
        >
          ▾
        </button>
      </div>
      <div class="log-box flex-log">
        {{ logText || t("panels.compileLog") }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.toolbar {
  flex-shrink: 0;
}

.error-bar {
  flex-shrink: 0;
  color: var(--danger);
  font-size: 0.85rem;
  padding: 0.25rem 0.8rem;
  margin: 0;
}

/* Primary workbench: horizontal flex, never collapses editor */
.workbench {
  display: flex;
  flex-direction: row;
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}

.activity-bar {
  flex: 0 0 44px;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  padding: 0.4rem 0.2rem;
  background: #0c1219;
  border-right: 1px solid var(--border);
  align-items: center;
  z-index: 2;
}
.activity-bar button {
  width: 2.1rem;
  height: 2.1rem;
  padding: 0;
  background: transparent;
  color: var(--muted);
  font-size: 1rem;
  border-radius: 6px;
}
.activity-bar button.active,
.activity-bar button:hover {
  background: #1e3a5f;
  color: var(--text);
}

.pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  background: var(--bg);
  border-right: 1px solid var(--border);
}
.pane:last-child {
  border-right: none;
}

.files-pane {
  max-width: 50vw;
}

.editor-pane {
  flex: 1 1 auto;
  min-width: 200px;
}

.pdf-pane {
  max-width: 50vw;
}

.sash-v {
  flex: 0 0 5px;
  cursor: col-resize;
  background: var(--border);
  z-index: 1;
}
.sash-v:hover {
  background: var(--accent);
}
.sash-h {
  flex: 0 0 5px;
  cursor: row-resize;
  background: var(--border);
}
.sash-h:hover {
  background: var(--accent);
}

.bottom-panel {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-top: 1px solid var(--border);
  background: #0b0f14;
  overflow: hidden;
}
.flex-log {
  flex: 1;
  max-height: none;
  overflow: auto;
}

.panel-header {
  padding: 0.4rem 0.65rem;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  border-bottom: 1px solid var(--border);
  background: #121a24;
  flex-shrink: 0;
}
.side-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.header-hide {
  background: transparent;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.05rem 0.35rem;
  font-size: 0.7rem;
  line-height: 1.2;
}
.header-hide:hover {
  background: #243044;
  color: var(--text);
}

.side-body {
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow: auto;
}
.muted {
  color: var(--muted);
  font-size: 0.8rem;
  margin: 0;
}
.muted-inline {
  color: var(--muted);
  font-size: 0.8rem;
}
.block-label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.8rem;
  color: var(--muted);
}
.block-label input {
  width: 100%;
}

.status-inline {
  color: var(--muted);
  font-size: 0.85rem;
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
}
.active-toggle {
  outline: 1px solid var(--accent);
}
.root-select select {
  max-width: 12rem;
}
.empty-editor {
  color: var(--muted);
  padding: 1rem;
  font-size: 0.9rem;
}
.err-list {
  border-top: 1px solid var(--border);
  max-height: 140px;
  overflow: auto;
  flex-shrink: 0;
}
.err-item {
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--danger);
  font-size: 0.75rem;
  white-space: normal;
  padding: 0.3rem 0.5rem;
  border: none;
  border-radius: 0;
}
.err-item:hover {
  background: #243044;
}

.zone-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}
.zone-list,
.commit-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.zone-item {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.35rem 0.45rem;
  background: #121a24;
}
.zone-item.active {
  border-color: var(--accent);
}
.zone-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--text);
  padding: 0.15rem 0;
  border: none;
  border-radius: 0;
}
.zone-name {
  font-size: 0.85rem;
  font-weight: 600;
}
.zone-meta {
  font-size: 0.7rem;
  color: var(--muted);
}
.zone-ops {
  display: flex;
  gap: 0.3rem;
  margin-top: 0.25rem;
}
.zone-subhead {
  margin: 0.25rem -0.75rem 0;
}
.commit-item {
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto;
  gap: 0.1rem 0.4rem;
  font-size: 0.75rem;
  padding: 0.3rem 0;
  border-bottom: 1px solid var(--border);
}
.commit-sha {
  color: var(--accent);
  font-size: 0.72rem;
}
.commit-subj {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.commit-date {
  grid-column: 1 / -1;
  color: var(--muted);
  font-size: 0.68rem;
}
</style>

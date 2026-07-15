<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import { useI18n } from "vue-i18n";
import MonacoDiff from "./features/diff/MonacoDiff.vue";
import ConflictImportModal from "./features/import/ConflictImportModal.vue";
import ToastStack from "./components/ToastStack.vue";
import ToolStrip from "./components/ToolStrip.vue";
import WorkViewPane from "./components/WorkViewPane.vue";
import FileTree from "./features/tree/FileTree.vue";
import { setLocale, type AppLocale } from "./i18n";
import { useLayoutStore, type MainPaneId } from "./stores/layout";
import { useProjectStore } from "./stores/project";
import {
  useWorkspaceStore,
  type ToolKind,
} from "./stores/workspace";

const { t, locale } = useI18n();
const store = useProjectStore();
const layout = useLayoutStore();
const workspace = useWorkspaceStore();
const { views: workViews, activeViewId } = storeToRefs(workspace);
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
  compareBaseRef,
  compareRevisedRef,
  gitDiffFiles,
  gitPreviewPair,
  agentResult,
  agentProposal,
  agentChatLog,
  agentProvider,
  binaryPreview,
  imagePreview,
  wordPreview,
  csvPreviewResult,
  uploadProgress,
  sidesSwapped,
  pdfSource,
  pdfTitle,
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
  mainOrder,
  visibleMainOrder,
} = storeToRefs(layout);

const dragPane = ref<MainPaneId | null>(null);
const dropTarget = ref<MainPaneId | null>(null);

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
const supplementInput = ref<HTMLInputElement | null>(null);
const showAdvanced = ref(false);
const conflictOpen = ref(false);
const pendingSupplement = ref<{
  files: File[];
  paths: string[];
} | null>(null);
const dryRunResult = ref<import("./shared/api").DryRunImportResult | null>(
  null
);
const gitRepo = ref("");
const gitBaseRef = ref("");
const gitRevisedRef = ref("");
const gitSubdir = ref("");
const gitCommitMsg = ref("");
const agentInstruction = ref("");
const agentChatInput = ref("");
const commandOpen = ref(false);
const commandQuery = ref("");
const diffRef = ref<InstanceType<typeof MonacoDiff> | null>(null);

const layoutPresets = [
  { id: "default", label: "toolbar.presetDefault" },
  { id: "editorPdf", label: "toolbar.presetEditorPdf" },
  { id: "filesEditor", label: "toolbar.presetFilesEditor" },
] as const;

function applyPreset(id: string) {
  if (!id) return;
  if (id === "default") {
    layout.reset();
  } else if (id === "editorPdf") {
    showFiles.value = false;
    showPdf.value = true;
    mainOrder.value = ["editor", "pdf", "files"];
  } else if (id === "filesEditor") {
    showFiles.value = true;
    showPdf.value = false;
    mainOrder.value = ["files", "editor", "pdf"];
  }
}

const commandItems = computed(() => {
  const q = commandQuery.value.trim().toLowerCase();
  const items = [
    {
      id: "compile",
      label: t("toolbar.compile"),
      run: () => void store.doCompile("latexmk"),
    },
    {
      id: "togglePdf",
      label: t("toolbar.togglePdf"),
      run: () => layout.togglePdf(),
    },
    {
      id: "toggleFiles",
      label: t("toolbar.toggleFiles"),
      run: () => layout.toggleFiles(),
    },
    {
      id: "commit",
      label: t("git.commitBtn"),
      run: () => void onGitCommit(),
    },
    {
      id: "zones",
      label: t("panels.zones"),
      run: () => openActivity("zones"),
    },
    {
      id: "agent",
      label: t("panels.agent"),
      run: () => openActivity("agent"),
    },
  ];
  if (!q) return items;
  return items.filter((i) => i.label.toLowerCase().includes(q));
});

function runCommand(item: { run: () => void }) {
  commandOpen.value = false;
  commandQuery.value = "";
  item.run();
}

function onGlobalKey(e: KeyboardEvent) {
  if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key.toLowerCase() === "p") {
    e.preventDefault();
    commandOpen.value = !commandOpen.value;
  } else if (e.key === "Escape") {
    commandOpen.value = false;
  }
}

const leftContent = computed(() => {
  if (!pair.value) return "";
  return store.pairLeftContent(pair.value);
});
const rightContent = computed(() => {
  if (!pair.value) return "";
  return store.pairRightContent(pair.value);
});
const isCsvFile = computed(
  () => !!currentPath.value && store.isCsvPath(currentPath.value)
);
const providerLabel = computed(() => {
  const p = (agentProvider.value || "").toLowerCase();
  if (p === "http") return t("agent.providerHttp");
  if (p === "off") return t("agent.providerOff");
  if (p === "stub") return t("agent.providerStub");
  return p || t("agent.providerStub");
});

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

const comparerTitle = computed(() => {
  if (gitPreviewPair.value) {
    return t("panels.diffHeaderPreview", {
      base: gitPreviewPair.value.baseRef.slice(0, 7),
      revised: gitPreviewPair.value.revisedRef.slice(0, 7),
    });
  }
  const hasContent = !!(
    pair.value ||
    imagePreview.value ||
    wordPreview.value ||
    binaryPreview.value
  );
  if (!hasContent) return t("panels.comparer");
  const proj = t("panels.sideProject");
  const zoneLabel = activeZoneName.value
    ? `${t("panels.sideZone")}「${activeZoneName.value}」`
    : t("panels.sideZone");
  const left = sidesSwapped.value ? zoneLabel : proj;
  const right = sidesSwapped.value ? proj : zoneLabel;
  return t("panels.diffHeaderWith", { left, right });
});

const pdfPaneTitle = computed(() => {
  if (pdfSource.value === "file" && pdfTitle.value) {
    return t("panels.pdfOfFile", { path: pdfTitle.value });
  }
  if (pdfSource.value === "compile") return t("panels.pdfCompile");
  return t("panels.pdfPreview");
});

watch(leftContent, (c) => {
  if (c != null) diffRef.value?.setLeftContent(c);
});

watch(sidesSwapped, () => {
  // force unit recompute via key on Monaco or content rebind
  if (pair.value) {
    diffRef.value?.setLeftContent(leftContent.value);
  }
});

onMounted(() => {
  void store.refreshAgentProvider();
  void store.restoreLastProject();
  window.addEventListener("keydown", onGlobalKey);
});

onBeforeUnmount(() => {
  store.stopPolling();
  window.removeEventListener("keydown", onGlobalKey);
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

function startResize(
  kind: "files" | "pdf" | "bottom",
  ev: MouseEvent,
  /** which side of the sash the resizable pane is on */
  edge: "left" | "right" = kind === "pdf" ? "right" : "left"
) {
  ev.preventDefault();
  const startX = ev.clientX;
  const startY = ev.clientY;
  const startFiles = filesWidth.value;
  const startPdf = pdfWidth.value;
  const startBottom = bottomHeight.value;

  function onMove(e: MouseEvent) {
    const dx = e.clientX - startX;
    if (kind === "files") {
      const delta = edge === "left" ? dx : -dx;
      filesWidth.value = Math.min(480, Math.max(160, startFiles + delta));
    } else if (kind === "pdf") {
      const delta = edge === "right" ? -dx : dx;
      pdfWidth.value = Math.min(640, Math.max(200, startPdf + delta));
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

function onPaneDragStart(id: MainPaneId, e: DragEvent) {
  dragPane.value = id;
  dropTarget.value = null;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    // Some browsers need a plain-text type for DnD to allow drops.
    e.dataTransfer.setData("text/plain", id);
    e.dataTransfer.setData("text/pane-id", id);
  }
}

function onPaneDragOver(id: MainPaneId, e: DragEvent) {
  // Always preventDefault while a pane drag is active so drop is allowed
  // (even when hovering the same id, which can happen on nested children).
  if (!dragPane.value) return;
  e.preventDefault();
  e.stopPropagation();
  if (dragPane.value !== id) {
    dropTarget.value = id;
  }
  if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
}

function onPaneDrop(id: MainPaneId, e: DragEvent) {
  e.preventDefault();
  e.stopPropagation();
  const fromRaw =
    dragPane.value ||
    e.dataTransfer?.getData("text/pane-id") ||
    e.dataTransfer?.getData("text/plain") ||
    "";
  const from = fromRaw as MainPaneId;
  const valid: MainPaneId[] = ["files", "editor", "pdf"];
  if (from && valid.includes(from) && from !== id && valid.includes(id)) {
    // Swap is symmetric L↔R (insert-before was a no-op for adjacent left→right).
    layout.swapMain(from, id);
  }
  dragPane.value = null;
  dropTarget.value = null;
}

function onPaneDragEnd() {
  dragPane.value = null;
  dropTarget.value = null;
}

function sashResizeFor(leftId: MainPaneId, rightId: MainPaneId): {
  kind: "files" | "pdf";
  edge: "left" | "right";
} | null {
  if (leftId === "files") return { kind: "files", edge: "left" };
  if (rightId === "files") return { kind: "files", edge: "right" };
  if (rightId === "pdf") return { kind: "pdf", edge: "right" };
  if (leftId === "pdf") return { kind: "pdf", edge: "left" };
  return null;
}

function onSashDown(leftId: MainPaneId, rightId: MainPaneId, e: MouseEvent) {
  const conf = sashResizeFor(leftId, rightId);
  if (!conf) return;
  startResize(conf.kind, e, conf.edge);
}

function orderOf(id: MainPaneId): number {
  const i = visibleMainOrder.value.indexOf(id);
  return i < 0 ? 99 : i * 2;
}

function paneStyle(id: MainPaneId): Record<string, string> {
  const o = String(orderOf(id));
  if (id === "files") {
    return { width: filesWidth.value + "px", flex: "0 0 auto", order: o };
  }
  if (id === "pdf") {
    return { width: pdfWidth.value + "px", flex: "0 0 auto", order: o };
  }
  return { flex: "1 1 auto", minWidth: "200px", order: o };
}

function sashOrder(leftId: MainPaneId, rightId: MainPaneId): number {
  // place sash between the two panes' order values
  const a = orderOf(leftId);
  const b = orderOf(rightId);
  return Math.min(a, b) + 1;
}

function paneDropClass(id: MainPaneId): string {
  if (dropTarget.value === id && dragPane.value && dragPane.value !== id) {
    return "pane-drop-target";
  }
  if (dragPane.value === id) return "pane-dragging";
  return "";
}

async function onGitCommit() {
  const msg = gitCommitMsg.value.trim() || t("git.commitPlaceholder");
  await store.doGitCommit(msg);
}

async function onGitDiscard() {
  if (!confirm(t("git.discardConfirm"))) return;
  await store.doGitDiscard();
}

function openActivity(
  a: "explorer" | "zones" | "git" | "compile" | "agent"
) {
  activity.value = a;
  showFiles.value = true;
  if (a === "git") {
    void store.refreshGitStatus();
    void store.refreshGitLog();
  }
  if (a === "zones") void store.refreshZones();
}

async function onZoneFromCommit(ref: string) {
  await store.doGitZoneFromCommit(ref);
}

function onSelectBase(ref: string) {
  store.setCompareBaseRef(ref);
}

function onSelectRevised(ref: string) {
  store.setCompareRevisedRef(ref);
}

async function onGitCompare() {
  await store.doGitDiff();
}

async function onOpenGitDiffFile(path: string) {
  await store.doOpenGitShow(path);
}

async function onAgentAnalyze() {
  await store.doAgentAnalyze();
}

async function onAgentPropose() {
  await store.doAgentPropose(agentInstruction.value);
}

async function onAgentApply() {
  if (!confirm(t("agent.applyConfirm"))) return;
  await store.doAgentApply();
  if (pair.value) diffRef.value?.setLeftContent(leftContent.value);
}

async function onAgentChat() {
  const msg = agentChatInput.value;
  if (!msg.trim()) return;
  agentChatInput.value = "";
  await store.doAgentChat(msg);
}

async function onCsvPreview() {
  await store.doCsvPreview();
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

async function onSupplementFilesSelected(e: Event) {
  const input = e.target as HTMLInputElement;
  const list = input.files;
  if (!list?.length || !projectId.value) {
    input.value = "";
    return;
  }
  const files = Array.from(list);
  const paths = files.map(
    (f) =>
      (f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name
  );
  const dry = await store.dryRunSupplement(paths);
  if (!dry) {
    input.value = "";
    return;
  }
  if (!dry.conflict) {
    await store.doSupplementFiles(files, {
      paths,
      on_conflict: "overwrite",
    });
    input.value = "";
    return;
  }
  pendingSupplement.value = { files, paths };
  dryRunResult.value = dry;
  conflictOpen.value = true;
  input.value = "";
}

async function onConflictConfirm(payload: {
  on_conflict: "overwrite" | "skip" | "rename";
  resolutions: Record<string, string>;
}) {
  const pending = pendingSupplement.value;
  conflictOpen.value = false;
  if (!pending) return;
  await store.doSupplementFiles(pending.files, {
    paths: pending.paths,
    on_conflict: payload.on_conflict,
    resolutions: payload.resolutions,
  });
  pendingSupplement.value = null;
  dryRunResult.value = null;
}

function onConflictCancel() {
  conflictOpen.value = false;
  pendingSupplement.value = null;
  dryRunResult.value = null;
}

function onOpenTool(kind: ToolKind) {
  workspace.addView(kind, null);
  if (kind === "pdf") showPdf.value = true;
}

/** Click in tree: bind into a suitable work view (active if compatible, else new). */
function onTreeOpen(path: string) {
  void store.openFile(path);
  const kind = workspace.fileKindForPath(path);
  let tool: ToolKind =
    kind === "pdf"
      ? "pdf"
      : kind === "word"
        ? "word"
        : "comparer";
  // Prefer active view when it accepts the file
  const active = workViews.value.find((v) => v.id === activeViewId.value);
  if (active && workspace.toolAcceptsPath(active.kind, path)) {
    workspace.bindPath(active.id, path);
    return;
  }
  // Prefer empty view of matching kind
  const empty = workViews.value.find(
    (v) => v.kind === tool && !v.path
  );
  if (empty) {
    workspace.bindPath(empty.id, path);
    return;
  }
  // Prefer any matching kind
  const any = workViews.value.find((v) =>
    workspace.toolAcceptsPath(v.kind, path)
  );
  if (any) {
    workspace.bindPath(any.id, path);
    return;
  }
  // Open a new tool of the right kind
  if (tool === "comparer" && (kind === "image" || kind === "other")) {
    tool = "editor";
  }
  workspace.addView(tool, path);
}

function onToolDropOnView(kind: ToolKind, targetViewId: string) {
  const idx = workViews.value.findIndex((v) => v.id === targetViewId);
  workspace.insertViewAt(kind, idx >= 0 ? idx : workViews.value.length, null);
}

function onFileDropOnView(viewId: string, path: string) {
  const v = workViews.value.find((x) => x.id === viewId);
  if (!v) return;
  const ok = workspace.bindPathWithMessage(
    viewId,
    path,
    t("tools.unsupportedFile", {
      tool: t(`tools.${v.kind}`),
      file: path,
    })
  );
  if (ok) {
    // keep project store path in sync for accept/git features when comparer
    if (v.kind === "comparer" || v.kind === "editor") {
      void store.openFile(path);
    }
  }
}

const dragViewId = ref<string | null>(null);

function onViewTitleDragStart(id: string, e: DragEvent) {
  dragViewId.value = id;
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", `view:${id}`);
    e.dataTransfer.setData("application/x-paper-diff-view", id);
  }
}

function onViewDropReorder(targetId: string, e: DragEvent) {
  e.preventDefault();
  const tool = e.dataTransfer?.getData("application/x-paper-diff-tool") as ToolKind;
  if (tool) {
    onToolDropOnView(tool, targetId);
    return;
  }
  const viewId =
    dragViewId.value ||
    e.dataTransfer?.getData("application/x-paper-diff-view") ||
    "";
  if (viewId && viewId !== targetId) {
    workspace.moveView(viewId, targetId);
  }
  const path =
    e.dataTransfer?.getData("application/x-paper-diff-path") ||
    e.dataTransfer?.getData("text/plain");
  if (path && !path.startsWith("tool:") && !path.startsWith("view:")) {
    onFileDropOnView(targetId, path);
  }
  dragViewId.value = null;
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
      <ToolStrip
        @open="onOpenTool"
        @drag-start="() => undefined"
      />
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
      <input
        ref="supplementInput"
        type="file"
        multiple
        hidden
        @change="onSupplementFilesSelected"
      />
      <button
        class="secondary"
        type="button"
        :disabled="busy || !projectId"
        @click="supplementInput?.click()"
      >
        {{ t("import.addFiles") }}
      </button>
      <select
        class="preset-select"
        :title="t('toolbar.layoutPreset')"
        @change="applyPreset(($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled selected>{{ t("toolbar.layoutPreset") }}</option>
        <option v-for="p in layoutPresets" :key="p.id" :value="p.id">
          {{ t(p.label) }}
        </option>
      </select>
      <button
        class="secondary"
        type="button"
        :title="t('toolbar.commandPalette')"
        @click="commandOpen = true"
      >
        ⌘⇧P
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
      <label class="status-inline" :title="t('lang.switch')">
        <select :value="locale" style="width: auto" @change="onLocaleChange">
          <option value="zh-CN">{{ t("lang.zh") }}</option>
          <option value="en">{{ t("lang.en") }}</option>
        </select>
      </label>
      <span
        v-if="agentProvider"
        class="provider-badge"
        :class="agentProvider"
        :title="t('panels.agent')"
      >
        {{ providerLabel }}
      </span>
      <span class="status">
        {{ status }}
        <template v-if="activeZoneName"> · {{ activeZoneName }}</template>
        <template v-if="compareSummary">
          · {{ compareSummary.ready }}/{{ compareSummary.total }}
        </template>
      </span>
    </header>
    <div
      v-if="uploadProgress != null"
      class="upload-progress"
      role="progressbar"
      :aria-valuenow="uploadProgress"
      aria-valuemin="0"
      aria-valuemax="100"
    >
      <div class="upload-progress-bar" :style="{ width: uploadProgress + '%' }" />
    </div>

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
        <button
          type="button"
          :class="{ active: activity === 'agent' && showFiles }"
          :title="t('panels.agent')"
          @click="openActivity('agent')"
        >
          ✨
        </button>
      </nav>

      <aside
        v-if="showFiles"
        class="pane files-pane"
        :class="paneDropClass('files')"
        :style="paneStyle('files')"
        data-pane="files"
        @dragenter.prevent="onPaneDragOver('files', $event)"
        @dragover.prevent="onPaneDragOver('files', $event)"
        @drop.prevent="onPaneDrop('files', $event)"
        @dragend="onPaneDragEnd"
      >
        <template v-if="activity === 'explorer'">
          <FileTree
            :files="files"
            :current-path="currentPath"
            :show-dot-files="showDotFiles"
            :busy="busy"
            :draggable-title="true"
            @update:show-dot-files="showDotFiles = $event"
            @open="onTreeOpen($event)"
            @action="(p, a) => store.doAcceptFile(p, a)"
            @compare-dir="store.doEnqueueDir($event)"
            @hide="layout.toggleFiles()"
            @title-drag-start="onPaneDragStart('files', $event)"
            @title-drag-end="onPaneDragEnd"
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
          <div
            class="panel-header side-header pane-drag-handle"
            draggable="true"
            :title="t('panels.dragToRearrange')"
            @dragstart="onPaneDragStart('files', $event)"
            @dragend="onPaneDragEnd"
          >
            <span class="drag-grip" aria-hidden="true">⋮⋮</span>
            <span>{{ t("panels.zones") }}</span>
            <button
              type="button"
              class="header-hide"
              :title="t('toolbar.toggleFiles')"
              @click.stop="layout.toggleFiles()"
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
          <div
            class="panel-header side-header pane-drag-handle"
            draggable="true"
            :title="t('panels.dragToRearrange')"
            @dragstart="onPaneDragStart('files', $event)"
            @dragend="onPaneDragEnd"
          >
            <span class="drag-grip" aria-hidden="true">⋮⋮</span>
            <span>{{ t("panels.git") }}</span>
            <button
              type="button"
              class="header-hide"
              :title="t('toolbar.toggleFiles')"
              @click.stop="layout.toggleFiles()"
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
            <div class="compare-refs muted">
              <span
                >{{ t("git.baseLabel") }}:
                <code>{{ compareBaseRef?.slice(0, 7) || "—" }}</code></span
              >
              <span
                >{{ t("git.revisedLabel") }}:
                <code>{{ compareRevisedRef?.slice(0, 7) || "—" }}</code></span
              >
              <button
                type="button"
                class="mini"
                :disabled="busy || !compareBaseRef || !compareRevisedRef"
                @click="onGitCompare"
              >
                {{ t("git.compare") }}
              </button>
              <button
                v-if="gitPreviewPair"
                type="button"
                class="mini secondary"
                @click="store.clearGitPreview()"
              >
                {{ t("git.clearPreview") }}
              </button>
            </div>
            <div class="panel-header zone-subhead">{{ t("git.log") }}</div>
            <ul v-if="gitCommits.length" class="commit-list">
              <li v-for="c in gitCommits" :key="c.sha" class="commit-item">
                <code class="commit-sha">{{ c.short }}</code>
                <span class="commit-subj">{{ c.subject }}</span>
                <span class="commit-date">{{ formatCommitDate(c.date) }}</span>
                <div class="commit-ops">
                  <button
                    type="button"
                    class="mini secondary"
                    :disabled="busy || !projectId"
                    :title="t('git.zoneFromCommit')"
                    @click="onZoneFromCommit(c.sha)"
                  >
                    {{ t("git.zoneFromCommit") }}
                  </button>
                  <button
                    type="button"
                    class="mini secondary"
                    :class="{ 'active-toggle': compareBaseRef === c.sha }"
                    :title="t('git.setBase')"
                    @click="onSelectBase(c.sha)"
                  >
                    {{ t("git.selectA") }}
                  </button>
                  <button
                    type="button"
                    class="mini secondary"
                    :class="{ 'active-toggle': compareRevisedRef === c.sha }"
                    :title="t('git.setRevised')"
                    @click="onSelectRevised(c.sha)"
                  >
                    {{ t("git.selectB") }}
                  </button>
                </div>
              </li>
            </ul>
            <p v-else class="muted">—</p>
            <template v-if="gitDiffFiles.length">
              <div class="panel-header zone-subhead">
                {{ t("git.compareFiles") }}
              </div>
              <ul class="git-diff-list">
                <li v-for="f in gitDiffFiles" :key="f.path">
                  <button
                    type="button"
                    class="git-diff-item"
                    :disabled="busy"
                    @click="onOpenGitDiffFile(f.path)"
                  >
                    <span class="badge" :class="(f.status || '').toLowerCase()">{{
                      f.status || f.xy || "?"
                    }}</span>
                    <span class="git-diff-path">{{ f.path }}</span>
                  </button>
                </li>
              </ul>
            </template>
          </div>
        </template>

        <template v-else-if="activity === 'agent'">
          <div
            class="panel-header side-header pane-drag-handle"
            draggable="true"
            :title="t('panels.dragToRearrange')"
            @dragstart="onPaneDragStart('files', $event)"
            @dragend="onPaneDragEnd"
          >
            <span class="drag-grip" aria-hidden="true">⋮⋮</span>
            <span>{{ t("panels.agent") }}</span>
            <span
              v-if="agentProvider"
              class="provider-badge mini-badge"
              :class="agentProvider"
            >
              {{ providerLabel }}
            </span>
            <button
              type="button"
              class="header-hide"
              :title="t('toolbar.toggleFiles')"
              @click.stop="layout.toggleFiles()"
            >
              ◀
            </button>
          </div>
          <div class="side-body">
            <p v-if="!currentPath" class="muted">
              {{ t("agent.empty") }}
            </p>
            <template v-else>
              <p class="muted">{{ currentPath }}</p>
              <div v-if="pair" class="zone-actions">
                <button
                  type="button"
                  class="mini"
                  :disabled="busy"
                  @click="onAgentAnalyze"
                >
                  {{ t("agent.analyze") }}
                </button>
                <button
                  type="button"
                  class="mini secondary"
                  :disabled="busy"
                  @click="onAgentPropose"
                >
                  {{ t("agent.propose") }}
                </button>
                <button
                  type="button"
                  class="mini secondary"
                  :disabled="busy || !agentProposal?.proposed_content"
                  @click="onAgentApply"
                >
                  {{ t("agent.apply") }}
                </button>
              </div>
              <label v-if="pair" class="block-label">
                {{ t("agent.instruction") }}
                <input
                  v-model="agentInstruction"
                  :placeholder="t('agent.instructionPlaceholder')"
                />
              </label>
            </template>
            <div class="panel-header zone-subhead">{{ t("agent.chatTitle") }}</div>
            <div class="agent-chat-log">
              <div
                v-for="(m, i) in agentChatLog"
                :key="i"
                class="agent-chat-msg"
                :class="m.role"
              >
                <span class="role">{{ m.role }}</span>
                <p>{{ m.text }}</p>
              </div>
              <p v-if="!agentChatLog.length" class="muted">…</p>
            </div>
            <div class="agent-chat-input">
              <input
                v-model="agentChatInput"
                :placeholder="t('agent.chatPlaceholder')"
                :disabled="busy || !projectId"
                @keydown.enter.prevent="onAgentChat"
              />
              <button
                type="button"
                class="mini"
                :disabled="busy || !projectId || !agentChatInput.trim()"
                @click="onAgentChat"
              >
                {{ t("agent.chatSend") }}
              </button>
            </div>
            <div v-if="agentResult" class="agent-block">
              <p v-if="agentResult.status === 'not_configured'" class="muted">
                {{ agentResult.message || t("agent.notConfigured") }}
              </p>
              <template v-else>
                <div class="panel-header zone-subhead">
                  {{ t("agent.summary") }}
                </div>
                <p class="agent-text">{{ agentResult.summary }}</p>
                <div v-if="agentResult.left_strengths?.length">
                  <div class="panel-header zone-subhead">
                    {{ t("agent.leftStrengths") }}
                  </div>
                  <ul class="agent-list">
                    <li
                      v-for="(s, i) in agentResult.left_strengths"
                      :key="'l' + i"
                    >
                      {{ s }}
                    </li>
                  </ul>
                </div>
                <div v-if="agentResult.right_strengths?.length">
                  <div class="panel-header zone-subhead">
                    {{ t("agent.rightStrengths") }}
                  </div>
                  <ul class="agent-list">
                    <li
                      v-for="(s, i) in agentResult.right_strengths"
                      :key="'r' + i"
                    >
                      {{ s }}
                    </li>
                  </ul>
                </div>
                <div v-if="agentResult.risks?.length">
                  <div class="panel-header zone-subhead">
                    {{ t("agent.risks") }}
                  </div>
                  <ul class="agent-list">
                    <li v-for="(s, i) in agentResult.risks" :key="'k' + i">
                      {{ s }}
                    </li>
                  </ul>
                </div>
                <div v-if="agentResult.recommendations?.length">
                  <div class="panel-header zone-subhead">
                    {{ t("agent.recommendations") }}
                  </div>
                  <ul class="agent-list">
                    <li
                      v-for="(s, i) in agentResult.recommendations"
                      :key="'c' + i"
                    >
                      {{ s }}
                    </li>
                  </ul>
                </div>
              </template>
            </div>
            <div v-if="agentProposal?.proposed_content" class="agent-block">
              <div class="panel-header zone-subhead">
                {{ t("agent.rationale") }}
              </div>
              <p class="agent-text">
                {{ agentProposal.rationale || "—" }}
              </p>
              <pre class="agent-draft">{{
                agentProposal.proposed_content.slice(0, 1200)
              }}{{
                agentProposal.proposed_content.length > 1200 ? "…" : ""
              }}</pre>
            </div>
          </div>
        </template>

        <template v-else>
          <div
            class="panel-header side-header pane-drag-handle"
            draggable="true"
            :title="t('panels.dragToRearrange')"
            @dragstart="onPaneDragStart('files', $event)"
            @dragend="onPaneDragEnd"
          >
            <span class="drag-grip" aria-hidden="true">⋮⋮</span>
            <span>{{ t("panels.compile") }}</span>
            <button
              type="button"
              class="header-hide"
              :title="t('toolbar.toggleFiles')"
              @click.stop="layout.toggleFiles()"
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

      <!-- Center work area: multi-view tools (comparer / editor / pdf / word) -->
      <div
        class="work-views-host"
        :style="{ flex: '1 1 auto', minWidth: '200px', order: orderOf('editor') }"
      >
        <div class="work-views-row">
          <WorkViewPane
            v-for="v in workViews"
            :key="v.id"
            :view="v"
            :active="v.id === activeViewId"
            @focus="workspace.focusView(v.id)"
            @close="workspace.closeView(v.id)"
            @title-drag-start="onViewTitleDragStart(v.id, $event)"
            @title-drag-end="dragViewId = null"
            @drop-tool="(kind) => onToolDropOnView(kind, v.id)"
            @drop-file="(path) => onFileDropOnView(v.id, path)"
            @invalid-drop="(msg) => workspace.toast(msg, 'warn')"
            @dragover.prevent
            @drop="onViewDropReorder(v.id, $event)"
          />
        </div>
      </div>
    </div>

    <ToastStack />

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
      <div
        class="panel-header side-header pane-drag-handle"
        :title="t('panels.dragBottomResize')"
        @mousedown="startResize('bottom', $event)"
      >
        <span class="drag-grip" aria-hidden="true">⋯</span>
        <span>{{ t("panels.bottomLog") }}</span>
        <button
          type="button"
          class="header-hide"
          :title="t('toolbar.toggleBottom')"
          @click.stop="layout.toggleBottom()"
        >
          ▾
        </button>
      </div>
      <div class="log-box flex-log">
        {{ logText || t("panels.compileLog") }}
      </div>
    </div>

    <ConflictImportModal
      :open="conflictOpen"
      :dry-run="dryRunResult"
      :file-count="pendingSupplement?.files.length || 0"
      @close="onConflictCancel"
      @cancel="onConflictCancel"
      @confirm="onConflictConfirm"
    />

    <div
      v-if="commandOpen"
      class="cmd-overlay"
      @click.self="commandOpen = false"
    >
      <div class="cmd-panel" role="dialog" aria-label="command palette">
        <input
          v-model="commandQuery"
          class="cmd-input"
          :placeholder="t('toolbar.commandPalette')"
          autofocus
          @keydown.enter.prevent="
            commandItems[0] && runCommand(commandItems[0])
          "
        />
        <ul class="cmd-list">
          <li v-for="item in commandItems" :key="item.id">
            <button type="button" class="cmd-item" @click="runCommand(item)">
              {{ item.label }}
            </button>
          </li>
        </ul>
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
.pane-drag-handle {
  cursor: grab;
  user-select: none;
  gap: 0.35rem;
}
.pane-drag-handle:active {
  cursor: grabbing;
}
.drag-grip {
  color: var(--muted);
  font-size: 0.65rem;
  letter-spacing: -0.1em;
  opacity: 0.7;
}
.pane-drop-target {
  outline: 2px solid #3b82f6;
  outline-offset: -2px;
}
.pane-dragging {
  opacity: 0.55;
}
.work-views-host {
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
}
.work-views-row {
  display: flex;
  flex-direction: row;
  flex: 1 1 auto;
  min-height: 0;
  gap: 2px;
  overflow: hidden;
}
.files-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.files-pane :deep(.file-tree),
.files-pane .side-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
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
  grid-template-rows: auto auto auto;
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
.commit-ops {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  margin-top: 0.15rem;
}
.compare-refs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.75rem;
}
.compare-refs code {
  color: var(--accent);
}
.git-diff-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.git-diff-item {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--text);
  border: none;
  border-radius: 4px;
  padding: 0.2rem 0.25rem;
  font-size: 0.75rem;
}
.git-diff-item:hover {
  background: #243044;
}
.git-diff-path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agent-block {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
.agent-text {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text);
  white-space: pre-wrap;
}
.agent-list {
  margin: 0;
  padding-left: 1.1rem;
  font-size: 0.75rem;
  color: var(--muted);
}
.agent-draft {
  margin: 0;
  max-height: 160px;
  overflow: auto;
  font-size: 0.7rem;
  background: #0b0f14;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.4rem;
  white-space: pre-wrap;
  color: var(--muted);
}
.binary-preview {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  justify-content: center;
  align-items: flex-start;
}
.upload-progress {
  height: 3px;
  background: #1a2332;
  flex-shrink: 0;
}
.upload-progress-bar {
  height: 100%;
  background: var(--accent);
  transition: width 0.15s ease-out;
}
.provider-badge {
  font-size: 0.68rem;
  padding: 0.1rem 0.4rem;
  border-radius: 999px;
  background: #334155;
  color: var(--muted);
  text-transform: lowercase;
}
.provider-badge.stub {
  background: #3b4d1f;
  color: #d9f99d;
}
.provider-badge.off {
  background: #3f1d1d;
  color: #fecaca;
}
.provider-badge.http {
  background: #1e3a5f;
  color: #bfdbfe;
}
.mini-badge {
  margin-left: auto;
  margin-right: 0.25rem;
}
.agent-chat-log {
  max-height: 180px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.25rem 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0.35rem;
}
.agent-chat-msg {
  font-size: 0.75rem;
}
.agent-chat-msg .role {
  color: var(--muted);
  font-size: 0.65rem;
  text-transform: uppercase;
  margin-right: 0.3rem;
}
.agent-chat-msg p {
  margin: 0.1rem 0 0;
  white-space: pre-wrap;
}
.agent-chat-msg.user p {
  color: #93c5fd;
}
.agent-chat-input {
  display: flex;
  gap: 0.3rem;
  margin-bottom: 0.5rem;
}
.cmd-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 50;
  display: flex;
  justify-content: center;
  padding-top: 12vh;
}
.cmd-panel {
  width: min(420px, 92vw);
  background: #0f172a;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
}
.cmd-input {
  width: 100%;
  margin-bottom: 0.4rem;
}
.cmd-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 50vh;
  overflow: auto;
}
.cmd-item {
  width: 100%;
  text-align: left;
  background: transparent;
  color: var(--text);
  padding: 0.4rem 0.5rem;
  border-radius: 4px;
}
.cmd-item:hover {
  background: #1e293b;
}
.preset-select {
  max-width: 8rem;
  font-size: 0.75rem;
}
.upload-bar {
  width: 4rem;
  height: 4px;
  background: #1a2332;
  border-radius: 2px;
  overflow: hidden;
  align-self: center;
}
.upload-fill {
  height: 100%;
  background: var(--accent, #3b82f6);
  transition: width 0.12s ease-out;
}
.agent-chat-input input {
  flex: 1;
  min-width: 0;
  font-size: 0.75rem;
  padding: 0.25rem 0.4rem;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: #0b0f14;
  color: var(--text);
}
.csv-preview-panel {
  flex-shrink: 0;
  max-height: 140px;
  overflow: auto;
  border-bottom: 1px solid var(--border);
  padding: 0.25rem 0.5rem 0.4rem;
  font-size: 0.72rem;
}
.csv-list {
  list-style: none;
  margin: 0.25rem 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}
.csv-list li {
  display: flex;
  gap: 0.35rem;
  align-items: baseline;
  min-width: 0;
}
.csv-snip {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 12rem;
}
.csv-arrow {
  color: var(--muted);
}
</style>

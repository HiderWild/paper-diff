import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  acceptAll,
  acceptFile,
  acceptOps,
  activateZone,
  agentAnalyze,
  agentApply,
  agentChat,
  agentChatStream,
  agentPropose,
  compareFile,
  compileLatexdiff,
  compileProject,
  createProject,
  createZone,
  csvPreview,
  deleteZone,
  enqueueCompare,
  exportWorkUrl,
  getCompileJob,
  getCompileLog,
  getDiffIndex,
  getFilePair,
  getHealth,
  getProject,
  gitCommit,
  gitDiff,
  gitLog,
  gitRestore,
  gitShow,
  gitStatus,
  gitZoneFromCommit,
  importGit,
  importWorkZip,
  importZoneFiles,
  importZoneZip,
  listZones,
  pdfUrl,
  renameZone,
  setRoot,
  undo,
  uploadVersions,
  workFileRawUrl,
  zoneFileRawUrl,
  zoneFromWork,
  type AgentAnalyzeResult,
  type AgentProposeResult,
  type CsvPreviewResult,
  type DiffIndexFile,
  type FilePair,
  type GitCommit,
  type GitDiffFile,
  type LineColRange,
  type ProjectDetail,
  type RootCandidate,
  type Zone,
} from "../shared/api";
import type { DiffUnit } from "../features/diff/sentenceMapper";
import { i18n } from "../i18n";

function t(
  key: string,
  params?: Record<string, string | number>
): string {
  return String(i18n.global.t(key, params ?? {}));
}

export const useProjectStore = defineStore("project", () => {
  const projectId = ref<string | null>(null);
  const files = ref<DiffIndexFile[]>([]);
  const currentPath = ref<string | null>(null);
  const pair = ref<FilePair | null>(null);
  const units = ref<DiffUnit[]>([]);
  const status = ref(t("store.ready"));
  const error = ref("");
  const logText = ref("");
  const pdfHref = ref<string | null>(null);
  const busy = ref(false);
  const autoCompile = ref(false);
  const lastCompileErrors = ref<
    Array<{ file?: string | null; line?: number | null; message: string }>
  >([]);
  const rootFile = ref<string | null>(null);
  const rootRecommended = ref<string | null>(null);
  const rootCandidates = ref<RootCandidate[]>([]);
  const compareSummary = ref<{
    total: number;
    ready: number;
    pending: number;
  } | null>(null);
  const gitInfo = ref<ProjectDetail["git"]>(null);
  const gitStatusText = ref("");
  const zones = ref<Zone[]>([]);
  const activeZoneId = ref<string | null>(null);
  const gitCommits = ref<GitCommit[]>([]);
  const compareBaseRef = ref<string | null>(null);
  const compareRevisedRef = ref<string | null>(null);
  const gitDiffFiles = ref<GitDiffFile[]>([]);
  const gitPreviewPair = ref<{
    left: string;
    right: string;
    path: string;
    baseRef: string;
    revisedRef: string;
  } | null>(null);
  const agentResult = ref<AgentAnalyzeResult | null>(null);
  const agentProposal = ref<AgentProposeResult | null>(null);
  const agentChatLog = ref<
    Array<{ role: "user" | "assistant" | "system"; text: string; at?: string }>
  >([]);
  const agentProvider = ref<string | null>(null);
  const binaryPreview = ref<{ path: string; message: string } | null>(null);
  const imagePreview = ref<{
    path: string;
    workUrl: string;
    zoneUrl?: string | null;
  } | null>(null);
  const csvPreviewResult = ref<CsvPreviewResult | null>(null);
  const uploadProgress = ref<number | null>(null);
  /** Display order: false = left work / right zone; true = swapped */
  const sidesSwapped = ref(false);
  /** PDF pane source */
  const pdfSource = ref<"none" | "file" | "compile">("none");
  const pdfPath = ref<string | null>(null);
  const pdfTitle = ref<string | null>(null);
  let compileDebounce: ReturnType<typeof setTimeout> | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;

  const IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp|svg)$/i;
  const CSV_EXT = /\.(csv|tsv)$/i;
  const PDF_EXT = /\.pdf$/i;

  function isImagePath(path: string) {
    return IMAGE_EXT.test(path);
  }

  function isCsvPath(path: string) {
    return CSV_EXT.test(path);
  }

  function isPdfPath(path: string) {
    return PDF_EXT.test(path);
  }

  function pairLeftContent(p: FilePair): string {
    const w = p.left?.content ?? p.merged.content;
    const z = p.right?.content ?? p.revised.content;
    return sidesSwapped.value ? z : w;
  }

  function pairRightContent(p: FilePair): string {
    const w = p.left?.content ?? p.merged.content;
    const z = p.right?.content ?? p.revised.content;
    return sidesSwapped.value ? w : z;
  }

  function toggleSidesSwapped() {
    sidesSwapped.value = !sidesSwapped.value;
  }

  function bustUrl(url: string) {
    const u = url.replace(/([?&])t=\d+/g, "$1").replace(/[?&]$/, "");
    const sep = u.includes("?") ? "&" : "?";
    return `${u}${sep}t=${Date.now()}`;
  }

  function refreshPdfIfFile(path: string) {
    if (pdfSource.value === "file" && pdfPath.value === path && projectId.value) {
      pdfHref.value = bustUrl(workFileRawUrl(projectId.value, path));
    }
  }

  function noteAgentProvider(provider?: string | null) {
    if (provider) agentProvider.value = provider;
  }

  const modifiedCount = computed(
    () => files.value.filter((f) => f.status === "modified").length
  );

  async function ensureProject() {
    if (!projectId.value) {
      const p = await createProject();
      projectId.value = p.id;
    }
    return projectId.value!;
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(() => {
      void refreshIndex({ quiet: true });
    }, 1500);
  }

  async function applyProjectDetail(detail: ProjectDetail) {
    rootFile.value = detail.root_file ?? null;
    rootRecommended.value = detail.root_recommended ?? null;
    rootCandidates.value = detail.root_candidates || [];
    gitInfo.value = detail.git ?? null;
    activeZoneId.value = detail.active_zone_id ?? null;
    if (detail.zones) zones.value = detail.zones;
  }

  async function refreshProjectMeta() {
    if (!projectId.value) return;
    const detail = await getProject(projectId.value);
    await applyProjectDetail(detail);
  }

  async function refreshZones() {
    if (!projectId.value) return;
    try {
      const res = await listZones(projectId.value);
      zones.value = res.zones || [];
      activeZoneId.value = res.active_zone_id ?? null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function refreshIndex(opts?: { quiet?: boolean }) {
    if (!projectId.value) return;
    try {
      const idx = await getDiffIndex(projectId.value);
      files.value = idx.files;
      if (idx.summary) {
        compareSummary.value = {
          total: idx.summary.total,
          ready: idx.summary.ready,
          pending: idx.summary.pending,
        };
      }
    } catch (e) {
      if (!opts?.quiet) {
        error.value = e instanceof Error ? e.message : String(e);
      }
    }
  }

  async function openFile(path: string) {
    if (!projectId.value) return;
    currentPath.value = path;
    units.value = [];
    binaryPreview.value = null;
    imagePreview.value = null;
    csvPreviewResult.value = null;
    // Non-destructive git two-commit preview takes priority when active
    if (gitPreviewPair.value && gitPreviewPair.value.path === path) {
      pair.value = {
        path,
        encoding: "utf-8",
        base: {
          content: gitPreviewPair.value.left,
          sha256: "",
        },
        revised: {
          content: gitPreviewPair.value.right,
          sha256: "",
        },
        merged: {
          content: gitPreviewPair.value.left,
          sha256: "",
          revision: 0,
        },
      };
      status.value = `${path} · ${gitPreviewPair.value.baseRef}…${gitPreviewPair.value.revisedRef}`;
      return;
    }
    // Opening a different tree path leaves commit preview
    if (gitPreviewPair.value && gitPreviewPair.value.path !== path) {
      gitPreviewPair.value = null;
    }
    if (isPdfPath(path)) {
      pair.value = null;
      imagePreview.value = null;
      binaryPreview.value = null;
      // Open this project PDF in the PDF pane (not necessarily compile artifact)
      pdfSource.value = "file";
      pdfPath.value = path;
      pdfTitle.value = path;
      pdfHref.value = bustUrl(workFileRawUrl(projectId.value, path));
      status.value = path;
      return;
    }
    if (isImagePath(path)) {
      pair.value = null;
      const workUrl = workFileRawUrl(projectId.value, path);
      let zoneUrl: string | null = null;
      if (activeZoneId.value) {
        zoneUrl = zoneFileRawUrl(projectId.value, activeZoneId.value, path);
      }
      imagePreview.value = { path, workUrl, zoneUrl };
      binaryPreview.value = null;
      status.value = path;
      return;
    }
    try {
      void compareFile(projectId.value, path).catch(() => undefined);
      pair.value = await getFilePair(projectId.value, path);
      status.value = path;
      if (isCsvPath(path) && pair.value) {
        void doCsvPreview();
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      // binary / non-text soft landing
      if (/binary|not text|encoding|utf/i.test(msg) || isImagePath(path)) {
        pair.value = null;
        binaryPreview.value = {
          path,
          message: t("preview.binaryNotText"),
        };
        status.value = path;
        error.value = "";
        return;
      }
      error.value = msg;
      pair.value = null;
    }
  }

  function clearGitPreview() {
    const path = gitPreviewPair.value?.path || currentPath.value;
    gitPreviewPair.value = null;
    if (path) void openFile(path);
  }

  async function afterImport(detail: ProjectDetail) {
    await applyProjectDetail(detail);
    await refreshZones();
    await refreshIndex();
    startPolling();
    const first =
      files.value.find((f) => f.status === "modified") ||
      files.value.find((f) => f.kind === "text") ||
      files.value[0];
    if (first) await openFile(first.path);
  }

  async function doImportWork(file: File) {
    error.value = "";
    busy.value = true;
    uploadProgress.value = 0;
    try {
      const id = await ensureProject();
      status.value = t("store.uploading");
      const detail = await importWorkZip(id, file, (pct) => {
        uploadProgress.value = pct;
      });
      uploadProgress.value = 100;
      status.value = t("store.project", { id });
      await afterImport(detail);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
      uploadProgress.value = null;
    }
  }

  async function doUpload(base: File, revised: File) {
    error.value = "";
    busy.value = true;
    try {
      const id = await ensureProject();
      status.value = t("store.uploading");
      const detail = await uploadVersions(id, base, revised);
      status.value = t("store.project", { id });
      await afterImport(detail as ProjectDetail);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doGitImport(body: {
    repo_url: string;
    base_ref: string;
    revised_ref: string;
    subdir?: string;
  }) {
    error.value = "";
    busy.value = true;
    try {
      const id = await ensureProject();
      status.value = t("store.importingGit");
      const detail = await importGit(id, body);
      status.value = t("store.projectGit", { id });
      await afterImport(detail as ProjectDetail);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doAddZoneZip(file: File, name?: string) {
    if (!projectId.value) await ensureProject();
    const id = projectId.value!;
    error.value = "";
    busy.value = true;
    uploadProgress.value = 0;
    try {
      const z = await createZone(id, name);
      await importZoneZip(id, z.id, file, (pct) => {
        uploadProgress.value = pct;
      });
      uploadProgress.value = 100;
      await activateZone(id, z.id);
      await refreshZones();
      await refreshIndex();
      if (currentPath.value) await openFile(currentPath.value);
      status.value = t("zones.activated", { name: z.name });
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
      uploadProgress.value = null;
    }
  }

  async function doAddZoneFiles(fileList: File[] | FileList, name?: string) {
    if (!projectId.value) await ensureProject();
    const id = projectId.value!;
    const filesArr = Array.from(fileList as File[]);
    if (!filesArr.length) return;
    error.value = "";
    busy.value = true;
    try {
      const z = await createZone(id, name);
      const rels = filesArr.map(
        (f) =>
          (f as File & { webkitRelativePath?: string }).webkitRelativePath ||
          f.name
      );
      await importZoneFiles(id, z.id, filesArr, rels);
      await activateZone(id, z.id);
      await refreshZones();
      await refreshIndex();
      if (currentPath.value) await openFile(currentPath.value);
      status.value = t("zones.activated", { name: z.name });
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doZoneFromWork(name?: string) {
    if (!projectId.value) return;
    busy.value = true;
    try {
      const z = await zoneFromWork(projectId.value, name);
      await refreshZones();
      status.value = t("zones.snapshotOk", { name: z.name });
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doActivateZone(zoneId: string | null) {
    if (!projectId.value) return;
    busy.value = true;
    try {
      const res = await activateZone(projectId.value, zoneId);
      zones.value = res.zones || [];
      activeZoneId.value = res.active_zone_id ?? null;
      await refreshIndex();
      if (currentPath.value) await openFile(currentPath.value);
      status.value = zoneId
        ? t("zones.activated", {
            name: zones.value.find((z) => z.id === zoneId)?.name || zoneId,
          })
        : t("zones.deactivated");
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doDeleteZone(zoneId: string) {
    if (!projectId.value) return;
    busy.value = true;
    try {
      await deleteZone(projectId.value, zoneId);
      await refreshZones();
      await refreshIndex();
      if (currentPath.value) await openFile(currentPath.value);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doRenameZone(zoneId: string, name: string) {
    if (!projectId.value || !name.trim()) return;
    try {
      await renameZone(projectId.value, zoneId, name.trim());
      await refreshZones();
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function doSetRoot(path: string) {
    if (!projectId.value || !path) return;
    try {
      const detail = await setRoot(projectId.value, path);
      await applyProjectDetail(detail);
      status.value = t("store.rootSet", { path });
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function doEnqueueDir(prefix: string, includeDot = true) {
    if (!projectId.value) return;
    try {
      await enqueueCompare(projectId.value, {
        prefixes: [prefix],
        include_dot_paths:
          includeDot || prefix.split("/").some((s) => s.startsWith(".")),
        priority: false,
      });
      await refreshIndex({ quiet: true });
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function doAccept(unit: DiffUnit) {
    if (!projectId.value || !pair.value || !currentPath.value) return;
    if (gitPreviewPair.value) return;
    busy.value = true;
    error.value = "";
    try {
      // When sides are swapped in the UI, Monaco units are display-relative;
      // API always expects left=work ranges, right=zone ranges.
      const left_range = (
        sidesSwapped.value ? unit.right : unit.left
      ) as LineColRange;
      const right_range = (
        sidesSwapped.value ? unit.left : unit.right
      ) as LineColRange;
      const res = await acceptOps(projectId.value, [
        {
          op_id: unit.id,
          file: currentPath.value,
          granularity: unit.granularity,
          left_range,
          right_range,
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
      status.value = t("store.accepted", {
        granularity: unit.granularity,
        revision: res.merged.revision,
      });
      scheduleAutoCompile();
      return res.merged.content;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      busy.value = false;
    }
  }

  async function doAcceptAll() {
    if (!projectId.value || !pair.value || !currentPath.value) return null;
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
      status.value = t("store.acceptedAll", {
        revision: res.merged.revision,
      });
      scheduleAutoCompile();
      return res.merged.content;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      busy.value = false;
    }
  }

  async function doAcceptFile(
    path: string,
    action: "add" | "delete" | "replace_all"
  ) {
    if (!projectId.value) return;
    busy.value = true;
    error.value = "";
    try {
      await acceptFile(projectId.value, path, action);
      status.value = t("store.actionPath", { action, path });
      await refreshIndex();
      if (currentPath.value === path && action !== "delete") {
        await openFile(path);
      } else if (action === "delete" && currentPath.value === path) {
        currentPath.value = null;
        pair.value = null;
      }
      scheduleAutoCompile();
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doUndo() {
    if (!projectId.value) return null;
    busy.value = true;
    try {
      const res = await undo(projectId.value, 1);
      if (
        pair.value &&
        res.file === currentPath.value &&
        res.merged.content != null
      ) {
        pair.value = {
          ...pair.value,
          merged: {
            ...pair.value.merged,
            content: res.merged.content,
            revision: res.merged.revision,
          },
        };
      }
      await refreshIndex();
      status.value = t("store.undoOk");
      return res.merged?.content ?? null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      busy.value = false;
    }
  }

  function scheduleAutoCompile() {
    if (!autoCompile.value || !projectId.value || !rootFile.value) return;
    if (compileDebounce) clearTimeout(compileDebounce);
    compileDebounce = setTimeout(() => {
      void doCompile();
    }, 2000);
  }

  async function waitJob(jobId: string) {
    if (!projectId.value) return null;
    const deadline = Date.now() + 180_000;
    while (Date.now() < deadline) {
      const job = await getCompileJob(projectId.value, jobId);
      if (job.status === "succeeded" || job.status === "failed") return job;
      await new Promise((r) => setTimeout(r, 300));
    }
    return null;
  }

  async function doCompile(kind: "latexmk" | "latexdiff" = "latexmk") {
    if (!projectId.value) return;
    if (!rootFile.value) {
      error.value = t("errors.selectRoot");
      return;
    }
    busy.value = true;
    error.value = "";
    logText.value = t("store.compiling", { kind });
    lastCompileErrors.value = [];
    try {
      const start =
        kind === "latexdiff"
          ? await compileLatexdiff(projectId.value, rootFile.value)
          : await compileProject(projectId.value, rootFile.value);
      const job = await waitJob(start.job_id);
      if (!job) {
        error.value = t("store.compileTimeoutError");
        status.value = t("store.compileTimeout");
        return;
      }
      logText.value += `status=${job.status}\n`;
      if (job.message) logText.value += job.message + "\n";
      if (job.errors?.length) {
        lastCompileErrors.value = job.errors;
        logText.value +=
          job.errors
            .map((e) => `${e.file || "?"}:${e.line || "?"} ${e.message}`)
            .join("\n") + "\n";
      }
      try {
        logText.value += await getCompileLog(projectId.value, start.job_id);
      } catch {
        /* optional */
      }
      if (job.status === "succeeded") {
        pdfSource.value = "compile";
        pdfPath.value = null;
        pdfTitle.value = null;
        pdfHref.value =
          pdfUrl(projectId.value, start.job_id) + `&t=${Date.now()}`;
        status.value =
          kind === "latexdiff" ? t("store.latexdiffOk") : t("store.compileOk");
      } else {
        status.value = t("store.compileFailed");
        error.value = job.message || t("store.compileFailedMsg");
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  function exportUrl() {
    return projectId.value ? exportWorkUrl(projectId.value) : null;
  }

  function reportUrl() {
    return projectId.value
      ? `/api/v1/projects/${projectId.value}/export/accept-report.json`
      : null;
  }

  function setProjectId(id: string) {
    projectId.value = id;
    startPolling();
    void refreshProjectMeta();
    void refreshZones();
    void refreshIndex();
  }

  async function refreshGitStatus() {
    if (!projectId.value) return;
    try {
      const s = await gitStatus(projectId.value);
      gitStatusText.value = [
        s.mode || "",
        s.branch,
        s.dirty ? `dirty ${s.files.length}` : "clean",
        s.repo || "",
      ]
        .filter(Boolean)
        .join(" · ");
    } catch (e) {
      gitStatusText.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function refreshGitLog() {
    if (!projectId.value) return;
    try {
      const res = await gitLog(projectId.value, 40);
      gitCommits.value = res.commits || [];
    } catch {
      gitCommits.value = [];
    }
  }

  async function doGitCommit(message: string) {
    if (!projectId.value) return;
    busy.value = true;
    try {
      const res = await gitCommit(projectId.value, message);
      status.value = res.committed
        ? t("store.committed", { sha: res.sha || "" })
        : res.message;
      await refreshGitStatus();
      await refreshGitLog();
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doGitDiscard() {
    if (!projectId.value) return;
    busy.value = true;
    try {
      await gitRestore(projectId.value, { mode: "discard" });
      await refreshGitStatus();
      await refreshIndex();
      if (currentPath.value) await openFile(currentPath.value);
      status.value = t("git.discarded");
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  function setCompareBaseRef(ref: string | null) {
    compareBaseRef.value = ref;
  }

  function setCompareRevisedRef(ref: string | null) {
    compareRevisedRef.value = ref;
  }

  async function doGitZoneFromCommit(ref: string, name?: string) {
    if (!projectId.value || !ref) return;
    busy.value = true;
    error.value = "";
    try {
      const z = await gitZoneFromCommit(projectId.value, ref, name);
      if (!z?.id) throw new Error("zone-from-commit returned no zone id");
      await activateZone(projectId.value, z.id);
      gitPreviewPair.value = null;
      await refreshZones();
      await refreshIndex();
      if (currentPath.value) await openFile(currentPath.value);
      status.value = t("git.zoneFromCommitOk", {
        name: z.name || ref.slice(0, 7),
      });
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doGitDiff(base?: string | null, revised?: string | null) {
    if (!projectId.value) return;
    const b = base ?? compareBaseRef.value;
    const r = revised ?? compareRevisedRef.value;
    if (!b || !r) {
      error.value = t("git.needTwoRefs");
      return;
    }
    busy.value = true;
    error.value = "";
    try {
      compareBaseRef.value = b;
      compareRevisedRef.value = r;
      const res = await gitDiff(projectId.value, b, r);
      gitDiffFiles.value = res.files || [];
      status.value = t("git.compareOk", {
        n: gitDiffFiles.value.length,
        base: b.slice(0, 7),
        revised: r.slice(0, 7),
      });
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      gitDiffFiles.value = [];
    } finally {
      busy.value = false;
    }
  }

  async function doOpenGitShow(path: string) {
    if (!projectId.value) return;
    const b = compareBaseRef.value;
    const r = compareRevisedRef.value;
    if (!b || !r) {
      error.value = t("git.needTwoRefs");
      return;
    }
    busy.value = true;
    error.value = "";
    try {
      const [leftRes, rightRes] = await Promise.all([
        gitShow(projectId.value, b, path).catch(() => null),
        gitShow(projectId.value, r, path).catch(() => null),
      ]);
      if (leftRes?.binary || rightRes?.binary) {
        pair.value = null;
        gitPreviewPair.value = null;
        binaryPreview.value = {
          path,
          message: t("preview.binaryNotText"),
        };
        currentPath.value = path;
        status.value = path;
        return;
      }
      const left = leftRes?.content ?? "";
      const right = rightRes?.content ?? "";
      gitPreviewPair.value = {
        left,
        right,
        path,
        baseRef: b,
        revisedRef: r,
      };
      currentPath.value = path;
      units.value = [];
      binaryPreview.value = null;
      pair.value = {
        path,
        encoding: "utf-8",
        base: { content: left, sha256: "" },
        revised: { content: right, sha256: "" },
        merged: { content: left, sha256: "", revision: 0 },
      };
      status.value = `${path} · ${b.slice(0, 7)}…${r.slice(0, 7)}`;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doAgentAnalyze() {
    if (!projectId.value || !pair.value || !currentPath.value) {
      error.value = t("agent.needFile");
      return;
    }
    busy.value = true;
    error.value = "";
    try {
      const res = await agentAnalyze(projectId.value, {
        path: currentPath.value,
        left_text: pairLeftContent(pair.value),
        right_text: pairRightContent(pair.value),
        units: units.value.map((u) => ({
          id: u.id,
          granularity: u.granularity,
        })),
        zone_id: activeZoneId.value,
      });
      agentResult.value = res;
      noteAgentProvider(res.provider);
      if (res.status === "not_configured") {
        agentProvider.value = "off";
        status.value = t("agent.notConfigured");
      } else {
        status.value = t("agent.analyzeOk");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (/404|not found|not configured/i.test(msg)) {
        agentResult.value = {
          status: "not_configured",
          message: msg,
        };
        agentProvider.value = "off";
        status.value = t("agent.notConfigured");
      } else {
        error.value = msg;
      }
    } finally {
      busy.value = false;
    }
  }

  async function doAgentPropose(instruction = "") {
    if (!projectId.value || !pair.value || !currentPath.value) {
      error.value = t("agent.needFile");
      return;
    }
    busy.value = true;
    error.value = "";
    try {
      const res = await agentPropose(projectId.value, {
        path: currentPath.value,
        left_text: pairLeftContent(pair.value),
        right_text: pairRightContent(pair.value),
        units: units.value.map((u) => ({
          id: u.id,
          granularity: u.granularity,
        })),
        zone_id: activeZoneId.value,
        instruction,
      });
      agentProposal.value = res;
      noteAgentProvider(res.provider);
      if (res.status === "not_configured") {
        agentProvider.value = "off";
        status.value = t("agent.notConfigured");
      } else {
        status.value = t("agent.proposeOk");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (/404|not found|not configured/i.test(msg)) {
        agentProposal.value = {
          status: "not_configured",
          message: msg,
        };
        agentProvider.value = "off";
        status.value = t("agent.notConfigured");
      } else {
        error.value = msg;
      }
    } finally {
      busy.value = false;
    }
  }

  async function doAgentApply() {
    if (
      !projectId.value ||
      !currentPath.value ||
      !agentProposal.value?.proposed_content
    ) {
      error.value = t("agent.needProposal");
      return;
    }
    busy.value = true;
    error.value = "";
    try {
      const rev = pair.value?.merged.revision ?? 0;
      const res = await agentApply(projectId.value, {
        path: currentPath.value,
        content: agentProposal.value.proposed_content,
        expected_revision: rev,
      });
      noteAgentProvider(res.provider);
      if (res.status === "not_configured") {
        agentProvider.value = "off";
        status.value = t("agent.notConfigured");
        return;
      }
      clearGitPreview();
      await refreshIndex();
      await openFile(currentPath.value);
      status.value = t("agent.applyOk", {
        revision: res.revision ?? "",
      });
      agentProposal.value = null;
      scheduleAutoCompile();
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doAgentChat(message: string, selection?: string) {
    if (!projectId.value) {
      error.value = t("agent.needFile");
      return;
    }
    const msg = message.trim();
    if (!msg) return;
    const at = new Date().toISOString();
    agentChatLog.value = [
      ...agentChatLog.value,
      { role: "user", text: msg, at },
    ];
    busy.value = true;
    error.value = "";
    try {
      let streamReply = "";
      const res = await agentChatStream(
        projectId.value,
        {
          message: msg,
          path: currentPath.value || undefined,
          selection,
          zone_id: activeZoneId.value,
        },
        {
          onToken: (tok) => {
            streamReply += tok;
          },
        }
      ).catch(async () => {
        return agentChat(projectId.value!, {
          message: msg,
          path: currentPath.value || undefined,
          selection,
          zone_id: activeZoneId.value,
        });
      });
      noteAgentProvider(res.provider);
      if (res.status === "not_configured") {
        agentProvider.value = "off";
        agentChatLog.value = [
          ...agentChatLog.value,
          {
            role: "system",
            text: res.message || t("agent.notConfigured"),
            at: new Date().toISOString(),
          },
        ];
        status.value = t("agent.notConfigured");
        return;
      }
      const reply = res.reply || streamReply || "";
      agentChatLog.value = [
        ...agentChatLog.value,
        { role: "assistant", text: reply, at: new Date().toISOString() },
      ];
      status.value = t("agent.chatOk");
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
    }
  }

  async function doCsvPreview() {
    if (!projectId.value || !pair.value || !currentPath.value) return;
    if (!isCsvPath(currentPath.value)) {
      csvPreviewResult.value = null;
      return;
    }
    try {
      csvPreviewResult.value = await csvPreview(
        projectId.value,
        pairLeftContent(pair.value),
        pairRightContent(pair.value),
        200
      );
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      csvPreviewResult.value = null;
    }
  }

  async function refreshAgentProvider() {
    try {
      const h = await getHealth();
      if (h.agent_provider) agentProvider.value = h.agent_provider;
    } catch {
      /* ignore */
    }
  }

  return {
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
    csvPreviewResult,
    uploadProgress,
    sidesSwapped,
    pdfSource,
    pdfPath,
    pdfTitle,
    modifiedCount,
    pairLeftContent,
    pairRightContent,
    isCsvPath,
    isPdfPath,
    toggleSidesSwapped,
    refreshPdfIfFile,
    ensureProject,
    refreshIndex,
    refreshProjectMeta,
    refreshZones,
    openFile,
    clearGitPreview,
    doImportWork,
    doUpload,
    doGitImport,
    doAddZoneZip,
    doAddZoneFiles,
    doZoneFromWork,
    doActivateZone,
    doDeleteZone,
    doRenameZone,
    doSetRoot,
    doEnqueueDir,
    doAccept,
    doAcceptAll,
    doAcceptFile,
    doUndo,
    doCompile,
    scheduleAutoCompile,
    exportUrl,
    reportUrl,
    setProjectId,
    refreshGitStatus,
    refreshGitLog,
    doGitCommit,
    doGitDiscard,
    setCompareBaseRef,
    setCompareRevisedRef,
    doGitZoneFromCommit,
    doGitDiff,
    doOpenGitShow,
    doAgentAnalyze,
    doAgentPropose,
    doAgentApply,
    doAgentChat,
    doCsvPreview,
    refreshAgentProvider,
    startPolling,
    stopPolling,
  };
});

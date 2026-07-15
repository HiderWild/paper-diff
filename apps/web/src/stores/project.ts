import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  acceptAll,
  acceptFile,
  acceptOps,
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
  dryRunWorkImport,
  importWorkFilesReplace,
  importWorkZip,
  importZoneFiles,
  importZoneZip,
  listProjects,
  listZones,
  pdfUrl,
  putWorkFile,
  putWorkFileRange,
  renameZone,
  setRoot,
  supplementWorkFiles,
  undo,
  uploadVersions,
  workFileRawUrl,
  zoneFileRawUrl,
  zoneFromWork,
  type AgentAnalyzeResult,
  type AgentProposeResult,
  type CsvPreviewResult,
  type DiffIndexFile,
  type DryRunImportResult,
  type FilePair,
  type GitCommit,
  type GitDiffFile,
  type LineColRange,
  type ProjectDetail,
  type RootCandidate,
  type Zone,
} from "../shared/api";
import type { DiffUnit } from "../features/diff/sentenceMapper";
import {
  applyUnitToWorkText,
  lineRangePayloadForUnit,
} from "../features/diff/applySnippet";
import {
  countLines,
  estimateTier,
} from "../features/diff/largeFileTier";
import { i18n } from "../i18n";
import { useSettingsStore } from "./settings";
import {
  useCompareTargetStore,
  type CompareTarget,
} from "./compareTarget";

function t(
  key: string,
  params?: Record<string, string | number>
): string {
  return String(i18n.global.t(key, params ?? {}));
}

const saveTimers = new Map<string, ReturnType<typeof setTimeout>>();

export const useProjectStore = defineStore("project", () => {
  const projectId = ref<string | null>(null);
  const files = ref<DiffIndexFile[]>([]);
  const currentPath = ref<string | null>(null);
  const pair = ref<FilePair | null>(null);
  const units = ref<DiffUnit[]>([]);
  /** paths with unsaved local edits */
  const dirtyPaths = ref<Record<string, boolean>>({});
  /** last known local buffer per path (work side) */
  const localBuffers = ref<Record<string, string>>({});
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
  const DOCX_EXT = /\.docx$/i;
  const DOC_EXT = /\.doc$/i;

  const wordPreview = ref<{
    path: string;
    url: string;
    legacyDoc: boolean;
  } | null>(null);

  function isImagePath(path: string) {
    return IMAGE_EXT.test(path);
  }

  function isCsvPath(path: string) {
    return CSV_EXT.test(path);
  }

  function isPdfPath(path: string) {
    return PDF_EXT.test(path);
  }

  function isDocxPath(path: string) {
    return DOCX_EXT.test(path);
  }

  function isDocPath(path: string) {
    return DOC_EXT.test(path) && !DOCX_EXT.test(path);
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
    // Zones are isolated; never drive UI from server active_zone_id.
    activeZoneId.value = null;
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
      activeZoneId.value = null;
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
    wordPreview.value = null;
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
      wordPreview.value = null;
      // Open this project PDF in the PDF pane (not necessarily compile artifact)
      pdfSource.value = "file";
      pdfPath.value = path;
      pdfTitle.value = path;
      pdfHref.value = bustUrl(workFileRawUrl(projectId.value, path));
      status.value = path;
      return;
    }
    if (isDocxPath(path) || isDocPath(path)) {
      pair.value = null;
      imagePreview.value = null;
      binaryPreview.value = null;
      wordPreview.value = {
        path,
        url: bustUrl(workFileRawUrl(projectId.value, path)),
        legacyDoc: isDocPath(path),
      };
      status.value = path;
      return;
    }
    if (isImagePath(path)) {
      pair.value = null;
      wordPreview.value = null;
      const workUrl = workFileRawUrl(projectId.value, path);
      // No active-zone dual image preview — zones are isolated.
      imagePreview.value = { path, workUrl, zoneUrl: null };
      binaryPreview.value = null;
      status.value = path;
      return;
    }
    try {
      void compareFile(projectId.value, path).catch(() => undefined);
      pair.value = await getFilePair(projectId.value, path);
      // Light L-tier status hint (still full-load for now; meta/slice later).
      const leftText =
        pair.value?.left?.content ??
        pair.value?.merged?.content ??
        pair.value?.base?.content ??
        "";
      const rightText =
        pair.value?.right?.content ?? pair.value?.revised?.content ?? "";
      const tier = estimateTier(
        Math.max(leftText.length, rightText.length),
        Math.max(countLines(leftText), countLines(rightText))
      );
      status.value =
        tier === "L"
          ? `${path} · large (${countLines(leftText)} lines)`
          : path;
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
    if (detail.id) {
      projectId.value = detail.id;
      try {
        localStorage.setItem("paper-diff-last-project-id", detail.id);
      } catch {
        /* ignore */
      }
    }
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

  async function doImportWorkFiles(files: File[], paths?: string[]) {
    error.value = "";
    busy.value = true;
    uploadProgress.value = 0;
    try {
      const id = await ensureProject();
      status.value = t("store.uploading");
      const detail = await importWorkFilesReplace(
        id,
        files,
        paths,
        (pct) => {
          uploadProgress.value = pct;
        }
      );
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
      // Zones are isolated snapshots — do not activate / auto-compare.
      await refreshZones();
      status.value = t("zones.importOk", {
        name: z.name,
        n: (z as { file_count?: number }).file_count ?? "?",
      });
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
      uploadProgress.value = null;
    }
  }

  async function doAddZoneFiles(
    fileList: File[] | FileList,
    name?: string,
    relativePaths?: string[]
  ) {
    if (!projectId.value) await ensureProject();
    const id = projectId.value!;
    const filesArr = Array.from(fileList as File[]);
    if (!filesArr.length) return;
    error.value = "";
    busy.value = true;
    try {
      const z = await createZone(id, name);
      const rels =
        relativePaths && relativePaths.length === filesArr.length
          ? relativePaths
          : filesArr.map(
              (f) =>
                (f as File & { webkitRelativePath?: string })
                  .webkitRelativePath || f.name
            );
      // Normalize paths: strip leading slashes, collapse \\
      const clean = rels.map((p) =>
        String(p || "")
          .replace(/\\/g, "/")
          .replace(/^\/+/, "")
      );
      const result = (await importZoneFiles(
        id,
        z.id,
        filesArr,
        clean
      )) as Zone & { written?: number; file_count?: number };
      // Zones are isolated — no activate / no auto-compare into work tree.
      await refreshZones();
      const written =
        typeof result.written === "number"
          ? result.written
          : typeof result.file_count === "number"
            ? result.file_count
            : filesArr.length;
      status.value = t("zones.importOk", {
        name: z.name,
        n: written,
      });
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

  /**
   * Deprecated: zones no longer "activate". Kept as a no-op-ish local marker
   * so older call sites compile; does not drive tree compare or file status.
   */
  async function doActivateZone(
    _zoneId: string | null,
    _opts?: { silent?: boolean }
  ) {
    // Intentionally no network / no compare enqueue.
    activeZoneId.value = null;
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

  /**
   * Whether accept must use client-side apply (visible compare buffers).
   * Always true when an explicit zone/git target is set (no global active zone).
   */
  function needsClientApply(
    workPath: string,
    target?: CompareTarget | null
  ): boolean {
    const cmp = useCompareTargetStore();
    const t0 =
      target ??
      (projectId.value
        ? cmp.resolveForWork(projectId.value, workPath)
        : cmp.getForProject(projectId.value));
    if (!t0) return false;
    // Any explicit zone/git target is true-source client apply.
    return true;
  }

  /**
   * Apply the visible compare-side unit into the work file via PUT.
   * Guarantees "what you see is what you pull" for git / non-active zone.
   * L-tier full-line hunks use file-range PUT to avoid shipping whole file.
   */
  async function applyCompareUnit(
    unit: DiffUnit,
    opts: {
      workPath: string;
      rightTextFull: string;
      leftTextFull: string;
      sidesSwapped?: boolean;
    }
  ): Promise<string | null> {
    if (!projectId.value || !opts.workPath) return null;
    busy.value = true;
    error.value = "";
    try {
      const swapped = opts.sidesSwapped ?? sidesSwapped.value;
      const next = applyUnitToWorkText(opts.leftTextFull, unit, {
        rightTextFull: opts.rightTextFull,
        sidesSwapped: swapped,
      });
      const leftTier = estimateTier(
        opts.leftTextFull.length,
        countLines(opts.leftTextFull)
      );
      const rangePayload =
        leftTier === "L"
          ? lineRangePayloadForUnit(opts.leftTextFull, unit, {
              rightTextFull: opts.rightTextFull,
              sidesSwapped: swapped,
            })
          : null;
      if (rangePayload) {
        await putWorkFileRange(projectId.value, {
          path: opts.workPath,
          start_line: rangePayload.start_line,
          end_line: rangePayload.end_line,
          content: rangePayload.content,
        });
      } else {
        await putWorkFile(projectId.value, opts.workPath, next);
      }
      clearDirty(opts.workPath);
      localBuffers.value = { ...localBuffers.value, [opts.workPath]: next };
      if (currentPath.value === opts.workPath) {
        try {
          const p = await getFilePair(projectId.value, opts.workPath);
          pair.value = {
            ...p,
            merged: {
              ...p.merged,
              content: next,
            },
          };
        } catch {
          if (pair.value) {
            pair.value = {
              ...pair.value,
              merged: {
                ...pair.value.merged,
                content: next,
              },
            };
          }
        }
      }
      status.value = t("store.appliedCompare", { path: opts.workPath });
      scheduleAutoCompile();
      return next;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      busy.value = false;
    }
  }

  /**
   * Replace entire work file with visible right (compare) content.
   */
  async function applyCompareFileAll(opts: {
    workPath: string;
    rightTextFull: string;
  }): Promise<string | null> {
    if (!projectId.value || !opts.workPath) return null;
    busy.value = true;
    error.value = "";
    try {
      const next = opts.rightTextFull;
      await putWorkFile(projectId.value, opts.workPath, next);
      clearDirty(opts.workPath);
      localBuffers.value = { ...localBuffers.value, [opts.workPath]: next };
      if (currentPath.value === opts.workPath) {
        try {
          const p = await getFilePair(projectId.value, opts.workPath);
          pair.value = {
            ...p,
            merged: {
              ...p.merged,
              content: next,
            },
          };
        } catch {
          if (pair.value) {
            pair.value = {
              ...pair.value,
              merged: {
                ...pair.value.merged,
                content: next,
              },
            };
          }
        }
      }
      status.value = t("store.appliedCompareAll", { path: opts.workPath });
      scheduleAutoCompile();
      return next;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      busy.value = false;
    }
  }

  async function doAccept(
    unit: DiffUnit,
    buffers?: {
      leftTextFull?: string;
      rightTextFull?: string;
      workPath?: string;
    }
  ) {
    if (!projectId.value || !currentPath.value) return null;
    if (gitPreviewPair.value) return null;
    const workPath = buffers?.workPath || currentPath.value;
    const leftTextFull =
      buffers?.leftTextFull ??
      localBuffers.value[workPath] ??
      pair.value?.merged?.content ??
      pair.value?.left?.content ??
      "";
    const rightTextFull =
      buffers?.rightTextFull ??
      pair.value?.right?.content ??
      pair.value?.revised?.content ??
      "";

    // Prefer client apply for arrow pulls whenever buffers are provided
    // (true source from visible compare), or when target is git/non-active.
    const forceClient =
      buffers?.rightTextFull != null || needsClientApply(workPath);

    if (forceClient) {
      return applyCompareUnit(unit, {
        workPath,
        leftTextFull,
        rightTextFull,
        sidesSwapped: sidesSwapped.value,
      });
    }

    if (!pair.value) return null;
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
          file: workPath,
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
      localBuffers.value = {
        ...localBuffers.value,
        [workPath]: res.merged.content,
      };
      clearDirty(workPath);
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

  async function doAcceptAll(buffers?: {
    leftTextFull?: string;
    rightTextFull?: string;
    workPath?: string;
  }) {
    if (!projectId.value || !currentPath.value) return null;
    const workPath = buffers?.workPath || currentPath.value;
    const rightTextFull =
      buffers?.rightTextFull ??
      pair.value?.right?.content ??
      pair.value?.revised?.content ??
      "";

    if (
      buffers?.rightTextFull != null ||
      needsClientApply(workPath)
    ) {
      return applyCompareFileAll({ workPath, rightTextFull });
    }

    if (!pair.value) return null;
    busy.value = true;
    try {
      const res = await acceptAll(
        projectId.value,
        workPath,
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
      localBuffers.value = {
        ...localBuffers.value,
        [workPath]: res.merged.content,
      };
      clearDirty(workPath);
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
        clearDirty(res.file);
        localBuffers.value = {
          ...localBuffers.value,
          [res.file]: res.merged.content,
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

  function markDirty(path: string, content: string) {
    if (!path) return;
    localBuffers.value = { ...localBuffers.value, [path]: content };
    dirtyPaths.value = { ...dirtyPaths.value, [path]: true };
    // keep pair merged in sync for accept revision UX when path is current
    if (pair.value && currentPath.value === path) {
      pair.value = {
        ...pair.value,
        merged: {
          ...pair.value.merged,
          content,
        },
      };
    }
    const settings = useSettingsStore();
    if (!settings.autoSave || !projectId.value) return;
    const prev = saveTimers.get(path);
    if (prev) clearTimeout(prev);
    saveTimers.set(
      path,
      setTimeout(() => {
        saveTimers.delete(path);
        void savePath(path);
      }, 3000)
    );
  }

  function clearDirty(path: string) {
    if (!dirtyPaths.value[path]) return;
    const next = { ...dirtyPaths.value };
    delete next[path];
    dirtyPaths.value = next;
    const tmr = saveTimers.get(path);
    if (tmr) {
      clearTimeout(tmr);
      saveTimers.delete(path);
    }
  }

  function isDirty(path: string | null | undefined) {
    return !!(path && dirtyPaths.value[path]);
  }

  async function savePath(path: string): Promise<boolean> {
    if (!projectId.value || !path) return false;
    const content = localBuffers.value[path];
    if (content == null) return false;
    try {
      await putWorkFile(projectId.value, path, content);
      clearDirty(path);
      status.value = t("store.saved", { path });
      // refresh revision if current
      if (currentPath.value === path) {
        try {
          const p = await getFilePair(projectId.value, path);
          pair.value = p;
        } catch {
          /* ignore pair refresh */
        }
      }
      return true;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return false;
    }
  }

  async function flushAll(): Promise<boolean> {
    const paths = Object.keys(dirtyPaths.value).filter((p) => dirtyPaths.value[p]);
    let ok = true;
    for (const p of paths) {
      const r = await savePath(p);
      if (!r) ok = false;
    }
    return ok;
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
    try {
      localStorage.setItem("paper-diff-last-project-id", id);
    } catch {
      /* ignore */
    }
    startPolling();
    void refreshProjectMeta();
    void refreshZones();
    void refreshIndex();
  }

  async function restoreLastProject(): Promise<boolean> {
    try {
      const last = localStorage.getItem("paper-diff-last-project-id");
      const listed = await listProjects();
      const projects = listed.projects || [];
      if (!projects.length) return false;
      let pick = projects[0]?.id;
      if (last && projects.some((p) => p.id === last)) pick = last;
      if (!pick) return false;
      projectId.value = pick;
      await applyProjectDetail(await getProject(pick));
      await refreshZones();
      await refreshIndex();
      startPolling();
      void refreshAgentProvider();
      const first =
        files.value.find((f) => f.status === "modified") ||
        files.value.find((f) => f.kind === "text") ||
        files.value[0];
      if (first) await openFile(first.path);
      status.value = t("store.project", { id: pick });
      return true;
    } catch {
      return false;
    }
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
      gitPreviewPair.value = null;
      // Zone is isolated — user picks files into comparer explicitly.
      await refreshZones();
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
        zone_id: null,
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
        // No global active zone; agent uses explicit buffers only.
        zone_id: null,
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
          zone_id: null,
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
          zone_id: null,
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

  async function dryRunSupplement(paths: string[]): Promise<DryRunImportResult | null> {
    if (!projectId.value) return null;
    return dryRunWorkImport(projectId.value, paths);
  }

  async function doSupplementFiles(
    files: File[],
    opts: {
      paths?: string[];
      on_conflict?: "overwrite" | "skip" | "cancel" | "rename";
      resolutions?: Record<string, string>;
    }
  ) {
    if (!projectId.value) await ensureProject();
    const id = projectId.value!;
    error.value = "";
    busy.value = true;
    uploadProgress.value = 0;
    try {
      const res = await supplementWorkFiles(id, files, {
        ...opts,
        onProgress: (pct) => {
          uploadProgress.value = pct;
        },
      });
      uploadProgress.value = 100;
      status.value = t("store.supplementOk", {
        n: (res.written || []).length,
      });
      await afterImport(res);
      return res;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      busy.value = false;
      uploadProgress.value = null;
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
    wordPreview,
    csvPreviewResult,
    uploadProgress,
    sidesSwapped,
    pdfSource,
    pdfPath,
    pdfTitle,
    dirtyPaths,
    localBuffers,
    modifiedCount,
    pairLeftContent,
    pairRightContent,
    isCsvPath,
    isPdfPath,
    toggleSidesSwapped,
    markDirty,
    clearDirty,
    isDirty,
    savePath,
    flushAll,
    refreshPdfIfFile,
    ensureProject,
    refreshIndex,
    refreshProjectMeta,
    refreshZones,
    openFile,
    clearGitPreview,
    doImportWork,
    doImportWorkFiles,
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
    applyCompareUnit,
    applyCompareFileAll,
    needsClientApply,
    doAcceptFile,
    doUndo,
    doCompile,
    scheduleAutoCompile,
    exportUrl,
    reportUrl,
    setProjectId,
    restoreLastProject,
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
    dryRunSupplement,
    doSupplementFiles,
    isDocxPath,
    isDocPath,
    startPolling,
    stopPolling,
  };
});

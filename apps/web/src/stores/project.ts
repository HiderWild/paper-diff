import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  acceptAll,
  acceptFile,
  acceptOps,
  compareFile,
  compileLatexdiff,
  compileProject,
  createProject,
  enqueueCompare,
  exportMergedUrl,
  getCompileJob,
  getCompileLog,
  getDiffIndex,
  getFilePair,
  getProject,
  gitCommit,
  gitStatus,
  importGit,
  pdfUrl,
  setRoot,
  undo,
  uploadVersions,
  type DiffIndexFile,
  type FilePair,
  type LineColRange,
  type ProjectDetail,
  type RootCandidate,
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
  let compileDebounce: ReturnType<typeof setTimeout> | null = null;
  let pollTimer: ReturnType<typeof setInterval> | null = null;

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
    if (!rootFile.value && rootRecommended.value) {
      // Soft default for UI select only — compile still requires setRoot
    }
  }

  async function refreshProjectMeta() {
    if (!projectId.value) return;
    const detail = await getProject(projectId.value);
    await applyProjectDetail(detail);
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
    try {
      // Kick high-priority compare for this file (data refresh via poll)
      void compareFile(projectId.value, path).catch(() => undefined);
      pair.value = await getFilePair(projectId.value, path);
      status.value = path;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      pair.value = null;
    }
  }

  async function afterImport(detail: ProjectDetail) {
    await applyProjectDetail(detail);
    await refreshIndex();
    startPolling();
    const first =
      files.value.find((f) => f.status === "modified") ||
      files.value.find((f) => f.kind === "text") ||
      files.value[0];
    if (first) await openFile(first.path);
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
        include_dot_paths: includeDot || prefix.split("/").some((s) => s.startsWith(".")),
        priority: false,
      });
      await refreshIndex({ quiet: true });
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function doAccept(unit: DiffUnit) {
    if (!projectId.value || !pair.value || !currentPath.value) return;
    busy.value = true;
    error.value = "";
    try {
      const res = await acceptOps(projectId.value, [
        {
          op_id: unit.id,
          file: currentPath.value,
          granularity: unit.granularity,
          left_range: unit.left as LineColRange,
          right_range: unit.right as LineColRange,
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
    return projectId.value ? exportMergedUrl(projectId.value) : null;
  }

  function reportUrl() {
    return projectId.value
      ? `/api/v1/projects/${projectId.value}/export/accept-report.json`
      : null;
  }

  /** For embed: inject existing project id without creating. */
  function setProjectId(id: string) {
    projectId.value = id;
    startPolling();
    void refreshProjectMeta();
    void refreshIndex();
  }

  async function refreshGitStatus() {
    if (!projectId.value) return;
    try {
      const s = await gitStatus(projectId.value);
      gitStatusText.value = [
        s.branch,
        s.dirty ? `dirty ${s.files.length}` : "clean",
        s.repo,
      ].join(" · ");
    } catch (e) {
      gitStatusText.value = e instanceof Error ? e.message : String(e);
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
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
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
    modifiedCount,
    ensureProject,
    refreshIndex,
    refreshProjectMeta,
    openFile,
    doUpload,
    doGitImport,
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
    doGitCommit,
    startPolling,
    stopPolling,
  };
});

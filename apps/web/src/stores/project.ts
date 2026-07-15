import { defineStore } from "pinia";
import { computed, ref } from "vue";
import {
  acceptAll,
  acceptFile,
  acceptOps,
  compileLatexdiff,
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
  type LineColRange,
} from "../shared/api";
import type { DiffUnit } from "../features/diff/sentenceMapper";

export const useProjectStore = defineStore("project", () => {
  const projectId = ref<string | null>(null);
  const files = ref<DiffIndexFile[]>([]);
  const currentPath = ref<string | null>(null);
  const pair = ref<FilePair | null>(null);
  const units = ref<DiffUnit[]>([]);
  const status = ref("Ready");
  const error = ref("");
  const logText = ref("");
  const pdfHref = ref<string | null>(null);
  const busy = ref(false);
  const autoCompile = ref(true);
  const lastCompileErrors = ref<
    Array<{ file?: string | null; line?: number | null; message: string }>
  >([]);
  let compileDebounce: ReturnType<typeof setTimeout> | null = null;

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

  async function refreshIndex() {
    if (!projectId.value) return;
    const idx = await getDiffIndex(projectId.value);
    files.value = idx.files.filter(
      (f) => f.kind === "text" || f.status !== "same"
    );
  }

  async function openFile(path: string) {
    if (!projectId.value) return;
    currentPath.value = path;
    pair.value = await getFilePair(projectId.value, path);
    units.value = [];
    status.value = path;
  }

  async function doUpload(base: File, revised: File) {
    error.value = "";
    busy.value = true;
    try {
      const id = await ensureProject();
      status.value = "Uploading…";
      await uploadVersions(id, base, revised);
      status.value = `Project ${id}`;
      await refreshIndex();
      const first =
        files.value.find((f) => f.status === "modified") || files.value[0];
      if (first) await openFile(first.path);
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
      status.value = "Importing from git…";
      await importGit(id, body);
      status.value = `Project ${id} (git)`;
      await refreshIndex();
      const first =
        files.value.find((f) => f.status === "modified") || files.value[0];
      if (first) await openFile(first.path);
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      busy.value = false;
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
      status.value = `Accepted ${unit.granularity} → rev ${res.merged.revision}`;
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
      status.value = `Accepted all → rev ${res.merged.revision}`;
      scheduleAutoCompile();
      return res.merged.content;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      busy.value = false;
    }
  }

  async function doAcceptFile(path: string, action: "add" | "delete" | "replace_all") {
    if (!projectId.value) return;
    busy.value = true;
    error.value = "";
    try {
      await acceptFile(projectId.value, path, action);
      status.value = `${action} ${path}`;
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
      if (pair.value && res.file === currentPath.value && res.merged.content != null) {
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
      status.value = "Undo ok";
      return res.merged?.content ?? null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    } finally {
      busy.value = false;
    }
  }

  function scheduleAutoCompile() {
    if (!autoCompile.value || !projectId.value) return;
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
    busy.value = true;
    error.value = "";
    logText.value = `Compiling (${kind})…\n`;
    lastCompileErrors.value = [];
    try {
      const start =
        kind === "latexdiff"
          ? await compileLatexdiff(projectId.value)
          : await compileProject(projectId.value);
      const job = await waitJob(start.job_id);
      if (!job) {
        error.value = "compile timeout waiting for job";
        status.value = "Compile timeout";
        return;
      }
      logText.value += `status=${job.status}\n`;
      if (job.message) logText.value += job.message + "\n";
      if (job.errors?.length) {
        lastCompileErrors.value = job.errors;
        logText.value +=
          job.errors.map((e) => `${e.file || "?"}:${e.line || "?"} ${e.message}`).join(
            "\n"
          ) + "\n";
      }
      try {
        logText.value += await getCompileLog(projectId.value, start.job_id);
      } catch {
        /* optional */
      }
      if (job.status === "succeeded") {
        pdfHref.value =
          pdfUrl(projectId.value, start.job_id) + `&t=${Date.now()}`;
        status.value = kind === "latexdiff" ? "latexdiff PDF OK" : "Compile OK";
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
    modifiedCount,
    ensureProject,
    refreshIndex,
    openFile,
    doUpload,
    doGitImport,
    doAccept,
    doAcceptAll,
    doAcceptFile,
    doUndo,
    doCompile,
    scheduleAutoCompile,
    exportUrl,
    reportUrl,
    setProjectId,
  };
});

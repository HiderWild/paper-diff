export type LineColRange = {
  start_line: number;
  start_col: number;
  end_line: number;
  end_col: number;
};

export type FilePair = {
  path: string;
  encoding: string;
  base: { content: string; sha256: string };
  revised: { content: string; sha256: string };
  merged: { content: string; sha256: string; revision: number };
  left?: { content: string; sha256: string; kind?: string; revision?: number };
  right?: {
    content: string;
    sha256: string;
    kind?: string;
    zone_id?: string | null;
  } | null;
  active_zone_id?: string | null;
};

export type DiffIndexFile = {
  path: string;
  status: string;
  kind: string;
  revision?: number;
  compare_state?: string;
  is_dot?: boolean;
  error?: string | null;
};

export type Zone = {
  id: string;
  name: string;
  created_at?: string;
  source?: string;
  active?: boolean;
  file_count?: number;
};

export type ProjectDetail = {
  id: string;
  status: string;
  model?: string;
  root_file?: string | null;
  root_recommended?: string | null;
  root_candidates?: Array<{ path: string; score?: number; reasons?: string[] }>;
  root_detection?: string;
  include_dot_paths?: boolean;
  active_zone_id?: string | null;
  zones?: Zone[];
  git?: {
    repo?: string;
    subdir?: string;
    base_ref?: string;
    revised_ref?: string;
  } | null;
};

export type GitCommit = {
  sha: string;
  short: string;
  author?: string;
  email?: string;
  date?: string;
  subject: string;
};

export type RootCandidate = {
  path: string;
  score?: number;
  reasons?: string[];
};

/** Override from embed SDK */
let baseUrl = "";
export function setApiBase(url: string) {
  baseUrl = url.replace(/\/$/, "");
}

function BASE() {
  return baseUrl;
}

async function parse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body?.error?.message || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return res.json();
  return res as unknown as T;
}

export async function createProject(): Promise<{ id: string; status: string }> {
  return parse(await fetch(`${BASE()}/api/v1/projects`, { method: "POST" }));
}

export type ProjectListItem = {
  id: string;
  status: string;
  model?: string;
  root_file?: string | null;
  active_zone_id?: string | null;
  zone_count?: number;
  work_file_count?: number;
  updated_at?: number;
};

export async function listProjects(): Promise<{ projects: ProjectListItem[] }> {
  return parse(await fetch(`${BASE()}/api/v1/projects`));
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  return parse(await fetch(`${BASE()}/api/v1/projects/${projectId}`));
}

export async function setRoot(
  projectId: string,
  rootFile: string
): Promise<ProjectDetail> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/root`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ root_file: rootFile }),
    })
  );
}

export async function uploadVersions(
  projectId: string,
  base: File,
  revised: File
): Promise<ProjectDetail> {
  const fd = new FormData();
  fd.append("base", base);
  fd.append("revised", revised);
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/versions/upload`, {
      method: "POST",
      body: fd,
    })
  );
}

/** XHR upload with optional progress callback (0–100). */
export function xhrUpload<T = unknown>(
  url: string,
  formData: FormData,
  onProgress?: (pct: number) => void
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.responseType = "json";
    if (onProgress && xhr.upload) {
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable && ev.total > 0) {
          onProgress(Math.min(100, Math.round((ev.loaded / ev.total) * 100)));
        }
      };
    }
    xhr.onload = () => {
      const status = xhr.status;
      const body = xhr.response;
      if (status >= 200 && status < 300) {
        resolve(body as T);
        return;
      }
      let msg = xhr.statusText || `HTTP ${status}`;
      try {
        const errBody = typeof body === "object" && body ? body : JSON.parse(xhr.responseText || "{}");
        msg = errBody?.error?.message || JSON.stringify(errBody) || msg;
      } catch {
        /* ignore */
      }
      reject(new Error(msg));
    };
    xhr.onerror = () => reject(new Error("network error"));
    xhr.send(formData);
  });
}

/** v2: import a single work zip as the project tree. */
export async function importWorkZip(
  projectId: string,
  work: File,
  onProgress?: (pct: number) => void
): Promise<ProjectDetail> {
  const fd = new FormData();
  fd.append("work", work);
  const url = `${BASE()}/api/v1/projects/${projectId}/work/import/zip`;
  if (onProgress) {
    return xhrUpload<ProjectDetail>(url, fd, onProgress);
  }
  return parse(
    await fetch(url, {
      method: "POST",
      body: fd,
    })
  );
}

export async function listZones(
  projectId: string
): Promise<{ zones: Zone[]; active_zone_id?: string | null }> {
  return parse(await fetch(`${BASE()}/api/v1/projects/${projectId}/zones`));
}

export async function createZone(
  projectId: string,
  name?: string
): Promise<Zone> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/zones`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name || undefined }),
    })
  );
}

export async function deleteZone(
  projectId: string,
  zoneId: string
): Promise<{ deleted: string }> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/zones/${zoneId}`, {
      method: "DELETE",
    })
  );
}

export async function renameZone(
  projectId: string,
  zoneId: string,
  name: string
): Promise<Zone> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/zones/${zoneId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    })
  );
}

export async function activateZone(
  projectId: string,
  zoneId: string | null
): Promise<{ zones: Zone[]; active_zone_id?: string | null }> {
  if (zoneId) {
    return parse(
      await fetch(
        `${BASE()}/api/v1/projects/${projectId}/zones/${zoneId}/activate`,
        { method: "POST" }
      )
    );
  }
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/zones/activate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ zone_id: null }),
    })
  );
}

export async function importZoneZip(
  projectId: string,
  zoneId: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<Zone> {
  const fd = new FormData();
  fd.append("file", file);
  const url = `${BASE()}/api/v1/projects/${projectId}/zones/${zoneId}/import/zip`;
  if (onProgress) {
    return xhrUpload<Zone>(url, fd, onProgress);
  }
  return parse(
    await fetch(url, { method: "POST", body: fd })
  );
}

export async function importZoneFiles(
  projectId: string,
  zoneId: string,
  files: File[],
  relativePaths?: string[]
): Promise<Zone> {
  const fd = new FormData();
  for (const f of files) {
    fd.append("files", f);
  }
  if (relativePaths?.length) {
    fd.append("paths", JSON.stringify(relativePaths));
  }
  return parse(
    await fetch(
      `${BASE()}/api/v1/projects/${projectId}/zones/${zoneId}/import/files`,
      { method: "POST", body: fd }
    )
  );
}

export async function zoneFromWork(
  projectId: string,
  name?: string
): Promise<Zone> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/zones/from-work`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name || undefined }),
    })
  );
}

export async function importGit(
  projectId: string,
  body: {
    repo_url: string;
    base_ref: string;
    revised_ref: string;
    subdir?: string;
  }
): Promise<ProjectDetail> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/versions/git`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
}

export async function getCompileLog(
  projectId: string,
  jobId: string
): Promise<string> {
  const res = await fetch(
    `${BASE()}/api/v1/projects/${projectId}/compile/${jobId}/log`
  );
  if (!res.ok) throw new Error(await res.text());
  return res.text();
}

export async function getDiffIndex(projectId: string): Promise<{
  files: DiffIndexFile[];
  summary?: {
    total: number;
    ready: number;
    pending: number;
    include_dot_paths?: boolean;
  };
}> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/diff-index`)
  );
}

export async function enqueueCompare(
  projectId: string,
  body: {
    paths?: string[];
    prefixes?: string[];
    include_dot_paths?: boolean;
    priority?: boolean;
  }
): Promise<{ queued: string[]; count: number }> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/compare/enqueue`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  );
}

export async function compareFile(
  projectId: string,
  path: string
): Promise<{ queued: string[]; count: number }> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/compare/file`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    })
  );
}

export async function getFilePair(
  projectId: string,
  path: string
): Promise<FilePair> {
  const q = new URLSearchParams({ path });
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/file-pair?${q}`)
  );
}

export async function acceptOps(
  projectId: string,
  ops: Array<{
    op_id?: string;
    file: string;
    granularity: "hunk" | "word" | "sentence";
    left_range: LineColRange;
    right_range: LineColRange;
    expected_merged_revision: number;
  }>
): Promise<{
  merged: { content: string; sha256: string; revision: number };
}> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/accept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ops }),
    })
  );
}

export async function acceptAll(
  projectId: string,
  file: string,
  expected_merged_revision: number
): Promise<{ merged: { content: string; revision: number } }> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/accept-all`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file, expected_merged_revision }),
    })
  );
}

export async function acceptFile(
  projectId: string,
  path: string,
  action: "add" | "delete" | "replace_all"
): Promise<unknown> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/accept-file`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, action }),
    })
  );
}

export async function undo(
  projectId: string,
  steps = 1
): Promise<{
  merged: { content: string; revision: number };
  file: string;
}> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/undo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps }),
    })
  );
}

export async function compileProject(
  projectId: string,
  rootFile?: string | null
): Promise<{ job_id: string; status: string }> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/compile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        side: "work",
        root_file: rootFile || undefined,
      }),
    })
  );
}

export async function compileLatexdiff(
  projectId: string,
  rootFile?: string | null
): Promise<{ job_id: string; status: string }> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/compile/latexdiff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ root_file: rootFile || undefined }),
    })
  );
}

export async function getCompileJob(
  projectId: string,
  jobId: string
): Promise<{
  status: string;
  message?: string;
  errors?: Array<{ file?: string; line?: number; message: string }>;
  pdf_url?: string;
}> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/compile/${jobId}`)
  );
}

export function pdfUrl(projectId: string, jobId?: string): string {
  if (jobId) {
    return `${BASE()}/api/v1/projects/${projectId}/artifacts/pdf?job_id=${jobId}`;
  }
  return `${BASE()}/api/v1/projects/${projectId}/artifacts/pdf`;
}

export function exportMergedUrl(projectId: string): string {
  return `${BASE()}/api/v1/projects/${projectId}/export/merged.zip`;
}

/** v2 preferred export of the work tree. */
export function exportWorkUrl(projectId: string): string {
  return `${BASE()}/api/v1/projects/${projectId}/work/export.zip`;
}

export async function gitStatus(projectId: string): Promise<{
  repo: string;
  branch: string;
  files: Array<{ xy: string; path: string }>;
  dirty: boolean;
  mode?: string;
  base_ref?: string;
  revised_ref?: string;
}> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/git/status`)
  );
}

export async function gitLog(
  projectId: string,
  maxCount = 50
): Promise<{ repo?: string; mode?: string; commits: GitCommit[] }> {
  const q = new URLSearchParams({ max_count: String(maxCount) });
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/git/log?${q}`)
  );
}

export async function gitRestore(
  projectId: string,
  opts?: { mode?: "discard" | "checkout"; paths?: string[]; ref?: string }
): Promise<{ restored?: string[]; ref?: string; mode?: string }> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/git/restore`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: opts?.mode ?? "discard",
        paths: opts?.paths,
        ref: opts?.ref,
      }),
    })
  );
}

export async function gitCommit(
  projectId: string,
  message: string,
  paths?: string[]
): Promise<{ committed: boolean; message: string; sha: string | null }> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/git/commit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, paths, sync_from_merged: true }),
    })
  );
}

export type GitDiffFile = {
  path: string;
  status?: string;
  git_status?: string;
  xy?: string;
  old_path?: string | null;
};

export async function gitDiff(
  projectId: string,
  baseRef: string,
  revisedRef: string
): Promise<{
  base_ref: string;
  revised_ref: string;
  files: GitDiffFile[];
  mode?: string;
}> {
  const q = new URLSearchParams({
    base_ref: baseRef,
    revised_ref: revisedRef,
  });
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/git/diff?${q}`)
  );
}

export async function gitShow(
  projectId: string,
  ref: string,
  path: string
): Promise<{
  path: string;
  ref: string;
  content: string | null;
  encoding?: string | null;
  binary?: boolean;
  size?: number;
}> {
  const q = new URLSearchParams({ ref, path });
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/git/show?${q}`)
  );
}

export async function gitZoneFromCommit(
  projectId: string,
  ref: string,
  name?: string
): Promise<Zone> {
  const raw = await parse<{
    zone?: Zone;
    zone_id?: string;
    name?: string;
    file_count?: number;
    id?: string;
  }>(
    await fetch(
      `${BASE()}/api/v1/projects/${projectId}/git/zone-from-commit`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ref, name: name || undefined }),
      }
    )
  );
  if (raw.zone?.id) return raw.zone;
  return {
    id: raw.zone_id || raw.id || "",
    name: raw.name || raw.zone?.name || ref.slice(0, 12),
    file_count: raw.file_count,
    source: "git_commit",
  };
}

export type AgentAnalyzeResult = {
  status: string;
  provider?: string;
  project_id?: string;
  path?: string | null;
  zone_id?: string | null;
  summary?: string;
  left_strengths?: string[];
  right_strengths?: string[];
  risks?: string[];
  recommendations?: string[];
  stats?: { units?: number; left_chars?: number; right_chars?: number };
  message?: string;
  error?: string;
};

export type AgentProposeResult = {
  status: string;
  provider?: string;
  draft_id?: string;
  path?: string | null;
  proposed_content?: string;
  rationale?: string;
  zone_id?: string | null;
  project_id?: string;
  message?: string;
};

export type AgentApplyResult = {
  status: string;
  provider?: string;
  project_id?: string;
  path?: string;
  revision?: number;
  sha256?: string;
  message?: string;
};

export type AgentChatResult = {
  status: string;
  provider?: string;
  project_id?: string;
  reply?: string;
  suggested_patch?: { path?: string; note?: string } | null;
  message?: string;
};

async function agentPost<T>(
  projectId: string,
  action: string,
  body: Record<string, unknown>
): Promise<T> {
  const res = await fetch(
    `${BASE()}/api/v1/projects/${projectId}/agent/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
  if (res.status === 404) {
    return {
      status: "not_configured",
      message: "Agent endpoint not available",
    } as T;
  }
  return parse(res);
}

export async function agentAnalyze(
  projectId: string,
  body: {
    path?: string;
    left_text?: string;
    right_text?: string;
    units?: unknown[];
    zone_id?: string | null;
  } = {}
): Promise<AgentAnalyzeResult> {
  return agentPost(projectId, "analyze", body);
}

export async function agentPropose(
  projectId: string,
  body: {
    path?: string;
    left_text?: string;
    right_text?: string;
    units?: unknown[];
    zone_id?: string | null;
    instruction?: string;
  } = {}
): Promise<AgentProposeResult> {
  return agentPost(projectId, "propose", body);
}

export async function agentApply(
  projectId: string,
  body: {
    path: string;
    content: string;
    expected_revision?: number;
  }
): Promise<AgentApplyResult> {
  return agentPost(projectId, "apply", body);
}

export async function agentChat(
  projectId: string,
  body: {
    message: string;
    path?: string;
    selection?: string;
    zone_id?: string | null;
  }
): Promise<AgentChatResult> {
  return agentPost(projectId, "chat", body);
}

export type AgentChatStreamHandlers = {
  onToken?: (text: string) => void;
  onMessage?: (data: {
    reply?: string;
    provider?: string;
    suggested_patch?: unknown;
  }) => void;
  onDone?: (data: { status?: string }) => void;
  onError?: (data: unknown) => void;
};

/** Parse SSE body from agent chat/stream. */
export async function agentChatStream(
  projectId: string,
  body: {
    message: string;
    path?: string;
    selection?: string;
    zone_id?: string | null;
  },
  handlers: AgentChatStreamHandlers = {}
): Promise<AgentChatResult> {
  const res = await fetch(
    `${BASE()}/api/v1/projects/${projectId}/agent/chat/stream`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }
  );
  if (!res.ok) {
    return parse(res);
  }
  const reader = res.body?.getReader();
  if (!reader) {
    return { status: "error", message: "no stream body" };
  }
  const dec = new TextDecoder();
  let buf = "";
  let reply = "";
  let provider: string | undefined;
  let status = "ok";
  let eventName = "message";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n");
    buf = parts.pop() || "";
    for (const line of parts) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        const raw = line.slice(5).trim();
        let data: Record<string, unknown> = {};
        try {
          data = JSON.parse(raw);
        } catch {
          data = { text: raw };
        }
        if (eventName === "token") {
          const t = String(data.text || "");
          reply += t;
          handlers.onToken?.(t);
        } else if (eventName === "message") {
          if (typeof data.reply === "string") reply = data.reply;
          if (typeof data.provider === "string") provider = data.provider;
          handlers.onMessage?.(data as { reply?: string; provider?: string });
        } else if (eventName === "error") {
          status = String(data.status || "error");
          handlers.onError?.(data);
        } else if (eventName === "done") {
          if (data.status) status = String(data.status);
          handlers.onDone?.(data as { status?: string });
        }
        eventName = "message";
      }
    }
  }
  return {
    status,
    provider,
    project_id: projectId,
    reply,
  };
}

export type CsvPreviewResult = {
  project_id?: string;
  left_rows: number;
  right_rows: number;
  changed_rows: number;
  changes: Array<{
    row: number;
    status: string;
    left?: string | null;
    right?: string | null;
    cells?: Array<{ col: number; left?: string | null; right?: string | null }>;
  }>;
  truncated?: boolean;
};

export async function csvPreview(
  projectId: string,
  left: string,
  right: string,
  maxRows = 200
): Promise<CsvPreviewResult> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/diff/csv-preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ left, right, max_rows: maxRows }),
    })
  );
}

export function workFileRawUrl(projectId: string, path: string): string {
  const q = new URLSearchParams({ path });
  return `${BASE()}/api/v1/projects/${projectId}/work/file-raw?${q}`;
}

export function zoneFileRawUrl(
  projectId: string,
  zoneId: string,
  path: string
): string {
  const q = new URLSearchParams({ path });
  return `${BASE()}/api/v1/projects/${projectId}/zones/${zoneId}/file-raw?${q}`;
}

export async function getHealth(): Promise<{
  ok?: boolean;
  status?: string;
  version?: string;
  model?: string;
  agent_provider?: string;
}> {
  return parse(await fetch(`${BASE()}/api/v1/health`));
}

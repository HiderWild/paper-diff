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

export type ProjectDetail = {
  id: string;
  status: string;
  root_file?: string | null;
  root_recommended?: string | null;
  root_candidates?: Array<{ path: string; score?: number; reasons?: string[] }>;
  root_detection?: string;
  include_dot_paths?: boolean;
  git?: {
    repo?: string;
    subdir?: string;
    base_ref?: string;
    revised_ref?: string;
  } | null;
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
        side: "merged",
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

export async function gitStatus(projectId: string): Promise<{
  repo: string;
  branch: string;
  files: Array<{ xy: string; path: string }>;
  dirty: boolean;
  base_ref?: string;
  revised_ref?: string;
}> {
  return parse(
    await fetch(`${BASE()}/api/v1/projects/${projectId}/git/status`)
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

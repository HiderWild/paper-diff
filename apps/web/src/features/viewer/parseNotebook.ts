/**
 * Lightweight Jupyter nbformat (v3/v4) parser for read-only cell rendering.
 */

export type NotebookCellKind = "code" | "markdown" | "raw";

export type NotebookOutput =
  | { type: "stream"; name: string; text: string }
  | { type: "error"; ename: string; evalue: string; traceback: string[] }
  | {
      type: "display" | "execute_result";
      text?: string;
      html?: string;
      imagePng?: string;
      imageJpeg?: string;
      dataKeys: string[];
    };

export type NotebookCell = {
  index: number;
  id?: string;
  kind: NotebookCellKind;
  source: string;
  language: string;
  executionCount: number | null;
  outputs: NotebookOutput[];
};

export type NotebookData = {
  nbformat: number;
  language: string;
  cells: NotebookCell[];
  error?: string;
};

function joinSource(src: unknown): string {
  if (typeof src === "string") return src;
  if (Array.isArray(src)) return src.map(String).join("");
  return "";
}

function asMimeBundle(data: unknown): Record<string, unknown> {
  if (data && typeof data === "object" && !Array.isArray(data)) {
    return data as Record<string, unknown>;
  }
  return {};
}

function mimeText(value: unknown): string | undefined {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(String).join("");
  return undefined;
}

function parseOutput(raw: unknown): NotebookOutput | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const ot = String(o.output_type || "");

  if (ot === "stream") {
    return {
      type: "stream",
      name: String(o.name || "stdout"),
      text: joinSource(o.text),
    };
  }
  if (ot === "error") {
    const tb = Array.isArray(o.traceback) ? o.traceback.map(String) : [];
    return {
      type: "error",
      ename: String(o.ename || "Error"),
      evalue: String(o.evalue || ""),
      traceback: tb,
    };
  }
  if (ot === "display_data" || ot === "execute_result") {
    const data = asMimeBundle(o.data);
    return {
      type: ot === "display_data" ? "display" : "execute_result",
      text:
        mimeText(data["text/plain"]) ??
        mimeText(data["text/markdown"]) ??
        undefined,
      html: mimeText(data["text/html"]),
      imagePng: mimeText(data["image/png"]),
      imageJpeg: mimeText(data["image/jpeg"]),
      dataKeys: Object.keys(data),
    };
  }
  return null;
}

function mapCell(
  raw: unknown,
  index: number,
  defaultLang: string
): NotebookCell | null {
  if (!raw || typeof raw !== "object") return null;
  const c = raw as Record<string, unknown>;
  const ct = String(c.cell_type || "code");
  let kind: NotebookCellKind = "code";
  if (ct === "markdown") kind = "markdown";
  else if (ct === "raw") kind = "raw";
  else kind = "code";

  const meta = (c.metadata as Record<string, unknown>) || {};
  const langMeta =
    (meta.language as string) ||
    ((meta as { vscode?: { languageId?: string } }).vscode?.languageId);

  const outputsRaw = Array.isArray(c.outputs) ? c.outputs : [];
  const outputs: NotebookOutput[] = [];
  for (const o of outputsRaw) {
    const p = parseOutput(o);
    if (p) outputs.push(p);
  }

  return {
    index,
    id: typeof c.id === "string" ? c.id : undefined,
    kind,
    source: joinSource(c.source),
    language: langMeta || defaultLang || "python",
    executionCount:
      typeof c.execution_count === "number" ? c.execution_count : null,
    outputs,
  };
}

/** Strip ANSI escape sequences from traceback lines. */
export function stripAnsi(s: string): string {
  return s.replace(/\u001b\[[0-9;]*m/g, "");
}

export function parseNotebook(text: string): NotebookData {
  try {
    const nb = JSON.parse(text) as Record<string, unknown>;
    const nbformat = Number(nb.nbformat || 0);
    const meta = (nb.metadata as Record<string, unknown>) || {};
    const kernelspec = (meta.kernelspec as Record<string, unknown>) || {};
    const langInfo = (meta.language_info as Record<string, unknown>) || {};
    const language = String(
      langInfo.name || kernelspec.language || "python"
    ).toLowerCase();

    const cellsRaw = Array.isArray(nb.cells) ? nb.cells : [];
    // nbformat 3 used worksheets
    let list = cellsRaw;
    if (!list.length && Array.isArray(nb.worksheets)) {
      const ws = nb.worksheets as Array<{ cells?: unknown[] }>;
      list = ws.flatMap((w) => (Array.isArray(w.cells) ? w.cells : []));
    }

    const cells: NotebookCell[] = [];
    list.forEach((c, i) => {
      const mapped = mapCell(c, i, language);
      if (mapped) cells.push(mapped);
    });

    return { nbformat, language, cells };
  } catch (e) {
    return {
      nbformat: 0,
      language: "python",
      cells: [],
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

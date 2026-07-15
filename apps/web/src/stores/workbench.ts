/**
 * VS Code–style workbench: columns (groups) hold tabs (tools).
 * Columns have no labels; empty columns auto-close.
 */
import { defineStore } from "pinia";
import { computed, ref } from "vue";

export type ToolKind =
  | "comparer"
  | "editor"
  | "pdf"
  | "word"
  | "output";

export type ViewTab = {
  id: string;
  kind: ToolKind;
  path: string | null;
  title?: string;
};

export type Column = {
  id: string;
  /** Tab ids in order */
  tabIds: string[];
  activeTabId: string | null;
  /** Flex weight for horizontal share within a row */
  size: number;
};

/** Layout tree: vertical stack of horizontal rows of columns */
export type LayoutRow = {
  id: string;
  columnIds: string[];
  /** Flex weight for row height */
  size: number;
};

export type DropIntent =
  | { type: "tab-insert"; columnId: string; index: number }
  | { type: "tab-append"; columnId: string }
  | { type: "split-left"; columnId: string }
  | { type: "split-right"; columnId: string }
  | { type: "split-above"; columnId: string }
  | { type: "split-below"; columnId: string }
  | { type: "between-columns"; rowId: string; index: number }
  | { type: "between-rows"; index: number }
  | { type: "row-above-pair"; rowId: string }
  | { type: "row-below-pair"; rowId: string };

/** v3: empty default layout (no forced comparer/pdf tabs) */
const KEY = "paper-diff-workbench-v3";
const EDGE = 0.18; // side/top/bottom edge fraction for split-into-new-group
const PAIR_TOP = 0.1; // upper 10% of a gap: "above both"

function uid(prefix = "id") {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

export function fileKindForPath(
  path: string
): "pdf" | "word" | "image" | "text" | "other" {
  const p = path.toLowerCase();
  if (p.endsWith(".pdf")) return "pdf";
  if (p.endsWith(".docx") || p.endsWith(".doc")) return "word";
  if (/\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(p)) return "image";
  if (
    /\.(tex|bib|cls|sty|txt|md|csv|tsv|json|ya?ml|xml|py|r|html|css|js|ts|sh|toml|ini|cfg|bbl)$/i.test(
      p
    ) ||
    !p.includes(".")
  ) {
    return "text";
  }
  return "other";
}

export function toolAcceptsPath(kind: ToolKind, path: string): boolean {
  if (kind === "output") return false;
  const fk = fileKindForPath(path);
  if (kind === "pdf") return fk === "pdf";
  if (kind === "word") return fk === "word";
  if (kind === "editor") return fk === "text" || fk === "other";
  if (kind === "comparer") return fk === "text" || fk === "other";
  return false;
}

/** Empty workbench: no tabs/columns forced. User opens tools via strip or tree. */
function defaultState() {
  return {
    tabs: {} as Record<string, ViewTab>,
    columns: {} as Record<string, Column>,
    rows: [] as LayoutRow[],
    focusedTabId: null as string | null,
  };
}

type Persisted = ReturnType<typeof defaultState>;

function load(): Persisted {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return defaultState();
    const p = JSON.parse(raw) as Persisted;
    // Allow empty layout; only reset if corrupt shape
    if (!p.tabs || !p.columns || !Array.isArray(p.rows)) {
      return defaultState();
    }
    return p;
  } catch {
    return defaultState();
  }
}

/**
 * Classify mouse position inside a column rect into a drop intent.
 * @param relX 0..1 left→right within column
 * @param relY 0..1 top→bottom within column
 */
export function intentFromColumnPoint(
  columnId: string,
  relX: number,
  relY: number,
  opts?: { inTabBar?: boolean; tabIndex?: number }
): DropIntent {
  if (opts?.inTabBar) {
    return {
      type: "tab-insert",
      columnId,
      index: opts.tabIndex ?? 0,
    };
  }
  // Edges open new column splits (tab moves alone into new column)
  if (relY < EDGE) return { type: "split-above", columnId };
  if (relY > 1 - EDGE) return { type: "split-below", columnId };
  if (relX < EDGE) return { type: "split-left", columnId };
  if (relX > 1 - EDGE) return { type: "split-right", columnId };
  return { type: "tab-append", columnId };
}

/**
 * Mouse on sash/gap between two columns in a row.
 * Upper 10%: place a new row above both; else insert column between with equal share.
 */
export function intentFromColumnGap(
  rowId: string,
  insertIndex: number,
  relYInGap: number
): DropIntent {
  if (relYInGap < PAIR_TOP) {
    return { type: "row-above-pair", rowId };
  }
  if (relYInGap > 1 - PAIR_TOP) {
    return { type: "row-below-pair", rowId };
  }
  return { type: "between-columns", rowId, index: insertIndex };
}

export const useWorkbenchStore = defineStore("workbench", () => {
  const initial = load();
  const tabs = ref<Record<string, ViewTab>>({ ...initial.tabs });
  const columns = ref<Record<string, Column>>({ ...initial.columns });
  const rows = ref<LayoutRow[]>(
    initial.rows.map((r) => ({ ...r, columnIds: [...r.columnIds] }))
  );
  const focusedTabId = ref<string | null>(initial.focusedTabId);
  const dropPreview = ref<DropIntent | null>(null);

  const toasts = ref<
    Array<{ id: string; message: string; level?: "info" | "warn" | "error" }>
  >([]);

  function persist() {
    try {
      localStorage.setItem(
        KEY,
        JSON.stringify({
          tabs: tabs.value,
          columns: columns.value,
          rows: rows.value,
          focusedTabId: focusedTabId.value,
        })
      );
    } catch {
      /* ignore */
    }
  }

  function toast(
    message: string,
    level: "info" | "warn" | "error" = "warn"
  ) {
    const id = uid("toast");
    toasts.value = [...toasts.value, { id, message, level }];
    setTimeout(() => {
      toasts.value = toasts.value.filter((t) => t.id !== id);
    }, 4200);
  }

  function dismissToast(id: string) {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }

  function findColumnOfTab(tabId: string): string | null {
    for (const c of Object.values(columns.value)) {
      if (c.tabIds.includes(tabId)) return c.id;
    }
    return null;
  }

  function findRowOfColumn(columnId: string): string | null {
    for (const r of rows.value) {
      if (r.columnIds.includes(columnId)) return r.id;
    }
    return null;
  }

  function getTab(id: string) {
    return tabs.value[id] || null;
  }

  function getColumn(id: string) {
    return columns.value[id] || null;
  }

  const focusedTab = computed(() =>
    focusedTabId.value ? tabs.value[focusedTabId.value] || null : null
  );

  function ensureSeed() {
    // Empty layout is valid; kept for call-site compatibility.
  }

  /** One empty column so a tool can be opened into it. */
  function ensureColumn(): string {
    if (rows.value.length && Object.keys(columns.value).length) {
      const first = rows.value[0]?.columnIds[0];
      if (first && columns.value[first]) return first;
    }
    const col: Column = {
      id: uid("col"),
      tabIds: [],
      activeTabId: null,
      size: 1,
    };
    columns.value = { ...columns.value, [col.id]: col };
    if (!rows.value.length) {
      rows.value = [{ id: uid("row"), columnIds: [col.id], size: 1 }];
    } else {
      const r0 = rows.value[0];
      rows.value = [
        { ...r0, columnIds: [...r0.columnIds, col.id] },
        ...rows.value.slice(1),
      ];
    }
    return col.id;
  }

  /** Remove empty columns/rows. Allow fully empty workbench (no forced tab). */
  function pruneEmpty() {
    for (const id of Object.keys(columns.value)) {
      const c = columns.value[id];
      if (!c.tabIds.length) {
        for (const r of rows.value) {
          r.columnIds = r.columnIds.filter((x) => x !== id);
        }
        const next = { ...columns.value };
        delete next[id];
        columns.value = next;
      }
    }
    rows.value = rows.value.filter((r) => r.columnIds.length > 0);
    if (!rows.value.length) {
      focusedTabId.value = null;
    }
  }

  function focusTab(tabId: string) {
    const colId = findColumnOfTab(tabId);
    if (!colId) return;
    const c = columns.value[colId];
    columns.value = {
      ...columns.value,
      [colId]: { ...c, activeTabId: tabId },
    };
    focusedTabId.value = tabId;
    persist();
  }

  function createTab(kind: ToolKind, path: string | null = null): ViewTab {
    const tab: ViewTab = {
      id: uid("tab"),
      kind,
      path,
      title: path || undefined,
    };
    tabs.value = { ...tabs.value, [tab.id]: tab };
    return tab;
  }

  function addTabToColumn(
    columnId: string,
    kind: ToolKind,
    path: string | null = null,
    index?: number
  ) {
    const c = columns.value[columnId];
    if (!c) return null;
    const tab = createTab(kind, path);
    const tabIds = [...c.tabIds];
    const at =
      index == null || index < 0 || index > tabIds.length
        ? tabIds.length
        : index;
    tabIds.splice(at, 0, tab.id);
    columns.value = {
      ...columns.value,
      [columnId]: { ...c, tabIds, activeTabId: tab.id },
    };
    focusedTabId.value = tab.id;
    persist();
    return tab;
  }

  /** Open tool: prefer focused column, else first column, else create empty column. */
  function openTool(kind: ToolKind, path: string | null = null) {
    let colId: string | null = null;
    if (focusedTabId.value) colId = findColumnOfTab(focusedTabId.value);
    if (!colId) {
      const firstRow = rows.value[0];
      colId = firstRow?.columnIds[0] ?? null;
    }
    if (!colId) {
      colId = ensureColumn();
    }
    return addTabToColumn(colId, kind, path);
  }

  function closeTab(tabId: string) {
    const colId = findColumnOfTab(tabId);
    if (!colId) return;
    const c = columns.value[colId];
    const tabIds = c.tabIds.filter((x) => x !== tabId);
    let activeTabId = c.activeTabId;
    if (activeTabId === tabId) {
      activeTabId = tabIds[tabIds.length - 1] ?? null;
    }
    columns.value = {
      ...columns.value,
      [colId]: { ...c, tabIds, activeTabId },
    };
    const nextTabs = { ...tabs.value };
    delete nextTabs[tabId];
    tabs.value = nextTabs;
    if (focusedTabId.value === tabId) {
      focusedTabId.value = activeTabId;
    }
    pruneEmpty();
    persist();
  }

  function detachTab(tabId: string): ViewTab | null {
    const colId = findColumnOfTab(tabId);
    if (!colId) return null;
    const tab = tabs.value[tabId];
    if (!tab) return null;
    const c = columns.value[colId];
    const tabIds = c.tabIds.filter((x) => x !== tabId);
    let activeTabId = c.activeTabId;
    if (activeTabId === tabId) {
      activeTabId = tabIds[tabIds.length - 1] ?? null;
    }
    columns.value = {
      ...columns.value,
      [colId]: { ...c, tabIds, activeTabId },
    };
    // leave tab in tabs map; caller re-attaches
    return tab;
  }

  function attachTab(
    tabId: string,
    columnId: string,
    index?: number
  ) {
    const c = columns.value[columnId];
    const tab = tabs.value[tabId];
    if (!c || !tab) return;
    if (c.tabIds.includes(tabId)) {
      // reorder within same column
      const tabIds = c.tabIds.filter((x) => x !== tabId);
      const at =
        index == null || index < 0 || index > tabIds.length
          ? tabIds.length
          : index;
      tabIds.splice(at, 0, tabId);
      columns.value = {
        ...columns.value,
        [columnId]: { ...c, tabIds, activeTabId: tabId },
      };
    } else {
      const tabIds = [...c.tabIds];
      const at =
        index == null || index < 0 || index > tabIds.length
          ? tabIds.length
          : index;
      tabIds.splice(at, 0, tabId);
      columns.value = {
        ...columns.value,
        [columnId]: { ...c, tabIds, activeTabId: tabId },
      };
    }
    focusedTabId.value = tabId;
    pruneEmpty();
    persist();
  }

  function newColumnWithTab(tabId: string): Column {
    const col: Column = {
      id: uid("col"),
      tabIds: [tabId],
      activeTabId: tabId,
      size: 1,
    };
    columns.value = { ...columns.value, [col.id]: col };
    return col;
  }

  function insertColumnInRow(
    rowId: string,
    columnId: string,
    index: number
  ) {
    rows.value = rows.value.map((r) => {
      if (r.id !== rowId) return r;
      const ids = [...r.columnIds];
      const at = Math.max(0, Math.min(index, ids.length));
      ids.splice(at, 0, columnId);
      // equalize sizes
      const size = 1;
      for (const cid of ids) {
        const c = columns.value[cid];
        if (c) columns.value[cid] = { ...c, size };
      }
      return { ...r, columnIds: ids };
    });
  }

  function insertRowAt(index: number, columnIds: string[], size = 1) {
    const row: LayoutRow = { id: uid("row"), columnIds, size };
    const next = [...rows.value];
    next.splice(Math.max(0, Math.min(index, next.length)), 0, row);
    rows.value = next;
  }

  function applyDrop(tabId: string, intent: DropIntent) {
    // ensure tab exists
    if (!tabs.value[tabId]) return;
    detachTab(tabId);

    switch (intent.type) {
      case "tab-insert":
        attachTab(tabId, intent.columnId, intent.index);
        break;
      case "tab-append":
        attachTab(tabId, intent.columnId);
        break;
      case "split-left":
      case "split-right": {
        const rowId = findRowOfColumn(intent.columnId);
        if (!rowId) {
          attachTab(tabId, intent.columnId);
          break;
        }
        const row = rows.value.find((r) => r.id === rowId)!;
        const idx = row.columnIds.indexOf(intent.columnId);
        const col = newColumnWithTab(tabId);
        const insertAt = intent.type === "split-left" ? idx : idx + 1;
        insertColumnInRow(rowId, col.id, insertAt);
        focusedTabId.value = tabId;
        pruneEmpty();
        persist();
        break;
      }
      case "split-above":
      case "split-below": {
        const rowId = findRowOfColumn(intent.columnId);
        if (!rowId) {
          attachTab(tabId, intent.columnId);
          break;
        }
        const ri = rows.value.findIndex((r) => r.id === rowId);
        const col = newColumnWithTab(tabId);
        insertRowAt(
          intent.type === "split-above" ? ri : ri + 1,
          [col.id],
          1
        );
        focusedTabId.value = tabId;
        pruneEmpty();
        persist();
        break;
      }
      case "between-columns": {
        const col = newColumnWithTab(tabId);
        insertColumnInRow(intent.rowId, col.id, intent.index);
        // trisect-ish: equal sizes for columns in row
        const row = rows.value.find((r) => r.id === intent.rowId);
        if (row) {
          for (const cid of row.columnIds) {
            const c = columns.value[cid];
            if (c) columns.value[cid] = { ...c, size: 1 };
          }
        }
        focusedTabId.value = tabId;
        pruneEmpty();
        persist();
        break;
      }
      case "between-rows": {
        const col = newColumnWithTab(tabId);
        insertRowAt(intent.index, [col.id], 1);
        focusedTabId.value = tabId;
        pruneEmpty();
        persist();
        break;
      }
      case "row-above-pair":
      case "row-below-pair": {
        const ri = rows.value.findIndex((r) => r.id === intent.rowId);
        const col = newColumnWithTab(tabId);
        insertRowAt(
          intent.type === "row-above-pair" ? ri : ri + 1,
          [col.id],
          1
        );
        focusedTabId.value = tabId;
        pruneEmpty();
        persist();
        break;
      }
      default:
        break;
    }
    dropPreview.value = null;
  }

  /** Move entire column via drop intent (column drag). */
  function moveColumn(columnId: string, intent: DropIntent) {
    const col = columns.value[columnId];
    if (!col) return;
    const fromRowId = findRowOfColumn(columnId);
    if (!fromRowId) return;

    // remove from current row
    rows.value = rows.value.map((r) =>
      r.id === fromRowId
        ? { ...r, columnIds: r.columnIds.filter((x) => x !== columnId) }
        : r
    );
    rows.value = rows.value.filter((r) => r.columnIds.length > 0);

    switch (intent.type) {
      case "split-left":
      case "split-right": {
        const rowId = findRowOfColumn(intent.columnId) || intent.columnId;
        // if intent.columnId still exists as column:
        const targetRow =
          findRowOfColumn(intent.columnId) ||
          rows.value.find((r) => r.columnIds.includes(intent.columnId))?.id;
        if (targetRow) {
          const row = rows.value.find((r) => r.id === targetRow)!;
          const idx = row.columnIds.indexOf(intent.columnId);
          const insertAt = intent.type === "split-left" ? idx : idx + 1;
          insertColumnInRow(targetRow, columnId, Math.max(0, insertAt));
        } else {
          insertRowAt(rows.value.length, [columnId], 1);
        }
        break;
      }
      case "split-above":
      case "split-below": {
        const ri = rows.value.findIndex((r) =>
          r.columnIds.includes(intent.columnId)
        );
        insertRowAt(
          intent.type === "split-above" ? Math.max(0, ri) : ri + 1,
          [columnId],
          1
        );
        break;
      }
      case "between-columns":
        insertColumnInRow(intent.rowId, columnId, intent.index);
        break;
      case "between-rows":
        insertRowAt(intent.index, [columnId], 1);
        break;
      case "row-above-pair":
      case "row-below-pair": {
        const ri = rows.value.findIndex((r) => r.id === intent.rowId);
        insertRowAt(
          intent.type === "row-above-pair" ? ri : ri + 1,
          [columnId],
          1
        );
        break;
      }
      case "tab-append":
      case "tab-insert":
        // merge all tabs into target column then drop empty
        {
          const target = intent.columnId;
          const targetCol = columns.value[target];
          if (targetCol) {
            for (const tid of [...col.tabIds]) {
              detachTab(tid);
              attachTab(
                tid,
                target,
                intent.type === "tab-insert" ? intent.index : undefined
              );
            }
          }
        }
        break;
      default:
        insertRowAt(rows.value.length, [columnId], 1);
    }
    pruneEmpty();
    persist();
  }

  function bindPath(tabId: string, path: string): boolean {
    const tab = tabs.value[tabId];
    if (!tab) return false;
    if (!toolAcceptsPath(tab.kind, path)) return false;
    tabs.value = {
      ...tabs.value,
      [tabId]: { ...tab, path, title: path },
    };
    focusedTabId.value = tabId;
    const colId = findColumnOfTab(tabId);
    if (colId) {
      const c = columns.value[colId];
      columns.value = {
        ...columns.value,
        [colId]: { ...c, activeTabId: tabId },
      };
    }
    persist();
    return true;
  }

  function bindPathWithMessage(
    tabId: string,
    path: string,
    failMessage: string
  ): boolean {
    const ok = bindPath(tabId, path);
    if (!ok) toast(failMessage, "warn");
    return ok;
  }

  function setDropPreview(intent: DropIntent | null) {
    dropPreview.value = intent;
  }

  function setRowSize(rowId: string, size: number) {
    rows.value = rows.value.map((r) =>
      r.id === rowId ? { ...r, size: Math.max(0.3, size) } : r
    );
    persist();
  }

  function setColumnSize(columnId: string, size: number) {
    const c = columns.value[columnId];
    if (!c) return;
    columns.value = {
      ...columns.value,
      [columnId]: { ...c, size: Math.max(0.3, size) },
    };
    persist();
  }

  /** Flat list for tests / migration compat */
  const allTabs = computed(() => Object.values(tabs.value));

  return {
    tabs,
    columns,
    rows,
    focusedTabId,
    focusedTab,
    dropPreview,
    toasts,
    toast,
    dismissToast,
    allTabs,
    getTab,
    getColumn,
    findColumnOfTab,
    findRowOfColumn,
    focusTab,
    openTool,
    addTabToColumn,
    closeTab,
    applyDrop,
    moveColumn,
    bindPath,
    bindPathWithMessage,
    setDropPreview,
    setRowSize,
    setColumnSize,
    createTab,
    detachTab,
    attachTab,
    pruneEmpty,
    persist,
    ensureSeed,
    toolAcceptsPath,
    fileKindForPath,
  };
});

// Back-compat aliases used by older components during transition
export type ViewInstance = ViewTab;

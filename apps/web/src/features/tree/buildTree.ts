export type FileMeta = {
  path: string;
  status: string;
  kind: string;
  compare_state?: string;
  is_dot?: boolean;
};

export type TreeNode = {
  name: string;
  path: string;
  type: "dir" | "file";
  children?: TreeNode[];
  file?: FileMeta;
};

function splitPath(path: string): string[] {
  return path.replace(/\\/g, "/").split("/").filter(Boolean);
}

/** Build a sorted directory tree from flat file paths. */
export function buildTree(files: FileMeta[]): TreeNode[] {
  type Mutable = {
    name: string;
    path: string;
    type: "dir" | "file";
    children: Map<string, Mutable>;
    file?: FileMeta;
  };
  const root: Mutable = { name: "", path: "", type: "dir", children: new Map() };

  for (const f of files) {
    const parts = splitPath(f.path);
    if (!parts.length) continue;
    let cur = root;
    let acc = "";
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      acc = acc ? `${acc}/${part}` : part;
      const isLeaf = i === parts.length - 1;
      let child = cur.children.get(part);
      if (!child) {
        child = {
          name: part,
          path: acc,
          type: isLeaf ? "file" : "dir",
          children: new Map(),
          file: isLeaf ? f : undefined,
        };
        cur.children.set(part, child);
      } else if (isLeaf) {
        // File wins leaf slot; keep as file even if a dir existed (shouldn't)
        child.type = "file";
        child.file = f;
      } else {
        // Ensure intermediate is a directory
        child.type = "dir";
      }
      cur = child;
    }
  }

  function toNodes(m: Mutable): TreeNode[] {
    const dirs: TreeNode[] = [];
    const filesOut: TreeNode[] = [];
    for (const child of m.children.values()) {
      if (child.type === "dir") {
        dirs.push({
          name: child.name,
          path: child.path,
          type: "dir",
          children: toNodes(child),
        });
      } else {
        filesOut.push({
          name: child.name,
          path: child.path,
          type: "file",
          file: child.file,
        });
      }
    }
    dirs.sort((a, b) => a.name.localeCompare(b.name));
    filesOut.sort((a, b) => a.name.localeCompare(b.name));
    return [...dirs, ...filesOut];
  }

  return toNodes(root);
}

export function filterDotTree(nodes: TreeNode[], showDot: boolean): TreeNode[] {
  if (showDot) return nodes;
  return nodes
    .filter((n) => !n.name.startsWith("."))
    .map((n) =>
      n.type === "dir" && n.children
        ? { ...n, children: filterDotTree(n.children, showDot) }
        : n
    );
}

/** First-level directory paths only (for default expand). */
export function topLevelDirPaths(nodes: TreeNode[]): string[] {
  return nodes.filter((n) => n.type === "dir").map((n) => n.path);
}

export function isDotPath(path: string): boolean {
  return splitPath(path).some((p) => p.startsWith(".") && p !== "." && p !== "..");
}

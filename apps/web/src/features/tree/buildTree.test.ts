import { describe, expect, it } from "vitest";
import {
  buildTree,
  filterDotTree,
  isDotPath,
  topLevelDirPaths,
} from "./buildTree";

describe("buildTree", () => {
  it("nests paths and shows basename not full path", () => {
    const t = buildTree([
      { path: "main.tex", status: "modified", kind: "text" },
      { path: "chap/a.tex", status: "same", kind: "text" },
      { path: "chap/b.tex", status: "added", kind: "text" },
      { path: "chap/deep/c.tex", status: "same", kind: "text" },
    ]);
    expect(t.map((n) => n.name).sort()).toEqual(["chap", "main.tex"]);
    const chap = t.find((n) => n.name === "chap")!;
    expect(chap.type).toBe("dir");
    expect(chap.path).toBe("chap");
    const names = chap.children!.map((c) => c.name).sort();
    expect(names).toEqual(["a.tex", "b.tex", "deep"]);
    const deep = chap.children!.find((c) => c.name === "deep")!;
    expect(deep.type).toBe("dir");
    expect(deep.children![0].name).toBe("c.tex");
    expect(deep.children![0].path).toBe("chap/deep/c.tex");
  });

  it("filters dot dirs", () => {
    const t = buildTree([
      { path: ".git/x", status: "same", kind: "text" },
      { path: "main.tex", status: "same", kind: "text" },
    ]);
    const f = filterDotTree(t, false);
    expect(f.map((n) => n.name)).toEqual(["main.tex"]);
  });

  it("topLevelDirPaths", () => {
    const t = buildTree([
      { path: "a/x.tex", status: "same", kind: "text" },
      { path: "b/y.tex", status: "same", kind: "text" },
      { path: "z.tex", status: "same", kind: "text" },
    ]);
    expect(topLevelDirPaths(t).sort()).toEqual(["a", "b"]);
  });

  it("isDotPath", () => {
    expect(isDotPath(".git/config")).toBe(true);
    expect(isDotPath("src/.cache/x")).toBe(true);
    expect(isDotPath("main.tex")).toBe(false);
  });
});

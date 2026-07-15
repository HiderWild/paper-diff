# paper-diff Implementation Plan

> **Status:** P0–P5 implemented (backend + frontend). User real-device UI acceptance deferred.

**Goal:** Vue + FastAPI LaTeX paper diff with Accept merge and Docker full-doc compile.

**Architecture:** Monaco computes visual diff; FastAPI owns workspace, merge, compile.

**Tech stack:** Vue3/Vite/TS/Monaco/Pinia, FastAPI/Pydantic, Docker+latexmk+latexdiff, pytest/vitest.

---

## Completed checklist

### P0 — Foundation
- [x] Monorepo `apps/web`, `apps/api`, `docker/texlive`, `fixtures`
- [x] Dual zip import, tree, file-pair, diff-index
- [x] Monaco side-by-side line diff

### P1 — Accept / merge
- [x] line/col `merge_engine` + Accept / Undo / accept-all
- [x] Export merged.zip
- [x] accept-file add / delete / replace_all
- [x] Accept report JSON export

### P2 — Sentence / word units
- [x] sentence-mapper (LaTeX-aware tokenize + charChanges)
- [x] Accept chips in UI (hunk/word/sentence filter)

### P3 — Compile
- [x] Docker latexmk + Windows volume mount
- [x] Async background jobs + per-project serial lock
- [x] SSE `/events` + poll fallback
- [x] PDF artifact + log endpoint
- [x] Compile smoke test

### P4 — Git / UX
- [x] Git dual-ref import (+ subdir)
- [x] Auto-compile debounce (2s after accept)
- [x] Compile error list → jump to left editor line

### P5 — latexdiff + embed
- [x] `POST .../compile/latexdiff` (flatten + latexdiff + latexmk)
- [x] Embed SDK `mountPaperDiff` (`src/embed.ts`)
- [x] Pinia store for host integration

---

## Verify

```bash
cd apps/api && pytest -v
cd apps/web && npm test
docker build -t paper-diff-texlive:latest docker/texlive
```

## Deferred (user later)

- Live browser walkthrough / visual polish
- Production auth / multi-tenant storage
- Rename fuzzy path matching

## Next major track

- Workbench layout / tree / async compare / Git facade：见  
  `docs/superpowers/plans/2026-07-15-workbench-git-async-diff.md`（M1–M5 **core**；预设/命令面板属后续）
- **Product model v2**（项目本体 + 比较区 + 内置 Git + Agent）：见  
  `docs/superpowers/plans/2026-07-15-project-core-zones-git-llm.md`  
  **L0 main path done**；Agent chat/CSV UI/图片预览/上传进度等缺口见补强计划
- **Hardening / gap closure（复审后）：**  
  `docs/superpowers/plans/2026-07-15-hardening-followups.md`（R0 文档口径 → R1 接线 → R2 测试 → R3–R5）

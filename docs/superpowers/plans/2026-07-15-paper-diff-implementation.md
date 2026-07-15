# paper-diff Implementation Plan

> **For agentic workers:** Use task-by-task execution with tests first (TDD).

**Goal:** Vue + FastAPI LaTeX paper diff with Accept merge and Docker full-doc compile.

**Architecture:** Monaco computes visual diff; FastAPI owns workspace, merge, compile.

**Tech stack:** Vue3/Vite/TS/Monaco, FastAPI/Pydantic, Docker+latexmk, pytest.

---

### Task 1: Backend scaffolding + merge_engine (TDD)

**Files:**
- `apps/api/pyproject.toml`
- `apps/api/app/...`
- `apps/api/tests/test_merge_engine.py`

### Task 2: Project import/align/file APIs

**Files:**
- `apps/api/app/api/routes_projects.py`
- `apps/api/app/services/import_service.py`
- `apps/api/tests/test_projects_api.py`

### Task 3: Accept / undo / export APIs

### Task 4: Vue workbench + Monaco Diff (P0)

### Task 5: Accept UI + sentence-mapper (P1–P2)

### Task 6: Docker compile + PDF preview (P3)

See design spec: `docs/superpowers/specs/2026-07-15-paper-diff-design.md`

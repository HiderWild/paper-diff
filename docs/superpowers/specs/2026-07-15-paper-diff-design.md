# paper-diff Design Spec

**Date:** 2026-07-15  
**Status:** Approved  
**Approach:** A — Monaco Diff (frontend) + Python FastAPI (workspace/merge/compile) + Docker TeX

## Goals

Web UI for LaTeX paper revision review:

1. One project, two versions (`base` / `revised`) from zip upload (MVP) or Git refs (later).
2. Side-by-side red/green diff (left = **merged** working tree, right = **revised**).
3. Accept changes right→left at hunk / word / **sentence** granularity.
4. Full-document compile of the multi-file **merged** tree in an isolated Docker TeX environment.
5. Vue frontend (embeddable later); Python backend.

## Non-goals (MVP)

- Full LaTeX LSP / Workshop intellisense
- Real-time multi-user CRDT collaboration
- Browser WASM TeX as primary engine
- Using `latexdiff` as the merge engine (optional PDF-only side path later)
- Porting entire VS Code or LaTeX Workshop

## Architecture layers

```
L5 App shell (Vue, embed adapter)
L4 Workbench UI (tree, diff, PDF, log)
L3 Browser domain (Monaco diff, sentence-mapper, accept controller)
L2 HTTP REST + SSE
L1 FastAPI services (import, align, merge, root, compile)
L0 Workspace FS + Docker TeX runner
```

## Core model

| Object | Meaning |
|--------|---------|
| Project | Review session with on-disk workspace |
| Version | `base`, `revised` snapshots; `merged` working tree |
| File path | Normalized relative path (`chapters/intro.tex`) |
| DiffUnit | `hunk` \| `word` \| `sentence` with left/right line-col ranges |
| AcceptOp | Replace left(merged) range with right(revised) text |
| CompileJob | Docker latexmk run |

**Merged buffer:** left editor shows `merged` (initialized from `base`). Accept patches `merged` only. Export/compile use `merged`.

## Module boundaries

| Module | Does | Does not |
|--------|------|----------|
| `diff-editor` | Monaco side-by-side UI | Persist files |
| `sentence-mapper` | Aggregate char/word into sentences | Network I/O |
| `accept-controller` | UI state machine, call API | Direct disk write |
| `merge_engine` | Line/col patch, revision lock, undo snapshots | Docker |
| `root_detect` | Magic root / documentclass / main.tex | Edit content |
| `compile_orchestrator` | Recipe queue, timeout, log parse | Diff algorithm |
| `docker_runner` | Isolated container exec | Business rules |
| `version_import` | Materialize zip/git trees | Merge logic |

## Tech stack

- Frontend: Vue 3, TypeScript, Vite, Pinia, monaco-editor, pdfjs-dist
- Backend: Python 3.11+, FastAPI, Pydantic v2, uvicorn
- Compile: Docker + TeX Live + latexmk
- Tests: pytest, vitest (later)

## Repository layout

```
paper-diff/
  apps/web/          # Vue app
  apps/api/          # FastAPI
  docker/texlive/    # Compile image
  docs/superpowers/  # Specs & plans
  fixtures/          # Sample dual-version papers
```

## API contract (`/api/v1`)

### Project & versions

- `POST /projects` → `{ id }`
- `POST /projects/{id}/versions/upload` multipart `base`, `revised` zips
- `POST /projects/{id}/versions/git` (phase 4)
- `GET /projects/{id}` project detail + alignment summary
- `GET /projects/{id}/tree`
- `GET /projects/{id}/file-pair?path=`
- `GET /projects/{id}/diff-index`

### Accept / merge

Ranges are **line/col** (1-based line, 0-based column; Monaco-compatible):

```json
{
  "ops": [{
    "op_id": "client-uuid",
    "file": "chapters/intro.tex",
    "granularity": "sentence",
    "left_range":  { "start_line": 10, "start_col": 0, "end_line": 10, "end_col": 42 },
    "right_range": { "start_line": 10, "start_col": 0, "end_line": 12, "end_col": 5 },
    "expected_merged_revision": 7
  }]
}
```

- `POST /projects/{id}/accept`
- `POST /projects/{id}/accept-all` body `{ file, expected_merged_revision }`
- `POST /projects/{id}/accept-file` add/delete/replace from revised
- `POST /projects/{id}/undo` body `{ steps: 1 }`
- `GET /projects/{id}/export/merged.zip`

Conflict: `409 MERGE_CONFLICT` when revision mismatches.

### Compile

- `POST /projects/{id}/compile` → `{ job_id }`
- `GET /projects/{id}/compile/{job_id}`
- `GET /projects/{id}/artifacts/pdf`
- `GET /projects/{id}/events` SSE (or poll job status)

Docker defaults: `--network=none`, memory/CPU limits, no shell-escape, serial per project.

### Errors

```json
{ "error": { "code": "...", "message": "...", "details": {}, "request_id": "..." } }
```

## Diff / Accept (frontend)

1. Monaco DiffEditor: left=merged, right=revised; both read-only in MVP.
2. `getLineChanges()` + charChanges → offset via Position API.
3. `sentence-mapper`: tokenize LaTeX-aware (commands, `$...$` atoms); aggregate words into sentences on text nodes.
4. Accept → POST ranges → replace left model with returned merged content → recompute units for file.
5. Undo via server inverse/full-file snapshot.

## Compile (backend)

1. Detect root: user → `%!TeX root` → `main.tex` → first `\documentclass`.
2. Run recipe `latexmk` in Docker with merged tree mounted at `/work`.
3. Parse log for `file:line: message`; surface to UI.
4. Optional later: latexdiff flatten for annotated PDF only.

## Phased delivery

| Phase | Deliverable |
|-------|-------------|
| P0 | Monorepo, dual zip, tree, file-pair, Monaco line diff |
| P1 | Accept hunk/word, undo, export |
| P2 | Sentence units + Accept UI |
| P3 | Docker compile + PDF + log/SSE-or-poll |
| P4 | Git refs, auto-compile debounce, error jump |
| P5 | latexdiff side path, embed SDK |

## Success criteria

- Upload two fixture zips → see file tree + side-by-side diff.
- Accept a word/sentence/hunk → left updates; export zip contains change.
- Undo restores previous merged content.
- With Docker available, compile merged multi-file project to PDF and preview.
- Without Docker, compile returns clear `DOCKER_UNAVAILABLE` / actionable error.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Bad sentence boundaries in TeX | Fallback to hunk; LaTeX-aware tokenizer |
| TeX image size | Cached image; optional scheme trim |
| Encoding / offset bugs | Line/col ranges only |
| Accidental path escape | Normalize + workspace jail |
| Over-porting Workshop | Port strategies only, not extension host |

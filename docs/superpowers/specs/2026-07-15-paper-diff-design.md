# paper-diff Design Spec

**Date:** 2026-07-15  
**Status:** Approved — P0–P5 + product **v2 L0** (work/zones/local git). Hardening L1–L2 in progress.  
**Approach:** A — Monaco Diff (frontend) + Python FastAPI (workspace/merge/compile) + Docker TeX  
**Follow-up:** `docs/superpowers/plans/2026-07-15-hardening-followups.md`

## Goals

Web UI for LaTeX / research paper revision review:

1. **v2 (primary):** One persistent **project** (`work` tree) + optional **compare zones**; Git timeline optional/local.
2. **MVP legacy (compat):** dual zip `base`/`revised` still maps to work + auto-zone.
3. Side-by-side red/green diff: **left = work (editable truth)**, **right = active zone (or commit preview)**.
4. Accept changes right→left at hunk / word / **sentence** granularity into **work**.
5. Full-document compile of the multi-file **work** tree in Docker TeX.
6. Vue frontend (embeddable); Python backend.

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

## Core model (MVP historical)

| Object | Meaning |
|--------|---------|
| Project | Review session with on-disk workspace |
| Version | `base`, `revised` snapshots; `merged` working tree (**legacy names**) |
| File path | Normalized relative path (`chapters/intro.tex`) |
| DiffUnit | `hunk` \| `word` \| `sentence` with left/right line-col ranges |
| AcceptOp | Replace left range with right text |
| CompileJob | Docker latexmk run |

**Legacy buffer names:** API still exposes `base` / `revised` / `merged` for compatibility.  
**v2 truth:** `merged` ≡ **work** (editable); `revised` ≡ **active compare zone** (or empty).

---

## v2 domain model (product)

```
Project
├── work/                 # sole editable draft; compile & export target
├── zones/{zone_id}/      # compare snapshots (zip / folder / files / git commit)
│   ├── tree/
│   └── meta.json
├── .git/                 # project-local timeline (or bound external repo)
├── snapshots/            # accept / agent-apply undo
├── artifacts/, jobs/
└── meta.json
```

| Object | Meaning | Lifecycle |
|--------|---------|-----------|
| **Project** | Persistent research unit | create → import work → edit/commit → export |
| **Work** | Current paper tree | editable; Accept / agent apply / compile |
| **Compare zone** | Read-mostly snapshot | create → activate as right side → delete |
| **Git history** | Commits of work | init / commit / log / restore / zone-from-commit |
| **Diff session** | Left/right sources | default: work vs active zone; alt: commit A vs B (preview, no write) |
| **Agent session** | analyze / propose / apply / chat | stub by default; optional HTTP provider |

### Left / right rules

| Side | Default | Optional |
|------|---------|----------|
| Left editor | `work` (Accept target) | commit preview (read-only) |
| Right editor | active **zone** | other commit, agent draft |

Product copy: **项目 / 比较区 / 历史** — not “基准版 / 修订版” except advanced dual-zip compat.

### Disk vs API aliases

| Disk | API sides / keys |
|------|------------------|
| `work/` | side `work` or `merged` (alias) |
| `zones/{id}/tree` | side `zone:{id}` |
| `base/`, `revised/` | legacy materialization for dual-zip / latexdiff |

### Completion tiers (status claims)

| Tier | Meaning |
|------|---------|
| L0 | work + zones + accept + compile + local git |
| L1 | every public API wired in UI or explicitly deferred |
| L2 | real agent provider, upload %, layout presets, … |
| L3 | remote git auth, multi-tenant, large-repo perf |

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
| P0–P5 | Dual zip MVP, accept, sentence, Docker compile, git dual-ref, latexdiff, embed |
| v2 L0 | Single work zip, zones, local git timeline, two-commit preview |
| Hardening R* | Chat UI, CSV/image UI, upload progress, tests — see hardening plan |

### Key v2 APIs (additive)

- `POST /projects/{id}/work/import/zip`
- `GET|PUT /projects/{id}/work/file`, `GET .../work/file-raw` (images)
- Zones: `/projects/{id}/zones` CRUD + activate + import
- Git: status, log, commit, restore, diff, show, zone-from-commit; push → 501
- Agent: analyze, propose, apply, chat[, stream] (`PAPER_DIFF_AGENT_PROVIDER`)
- `POST /projects/{id}/diff/csv-preview`

## Success criteria

**L0 (main path):**

- Import **one** project zip → tree visible; optional zone zip → right side compare.
- Accept word/sentence/hunk → **work** updates; export contains change; undo works.
- With Docker: compile **work** to PDF; without Docker: clear error.
- Local git: commit / log / discard / zone-from-commit.

**L1+ (hardening):** chat UI, csv/image preview, upload progress — tracked in hardening plan.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Bad sentence boundaries in TeX | Fallback to hunk; LaTeX-aware tokenizer |
| TeX image size | Cached image; optional scheme trim |
| Encoding / offset bugs | Line/col ranges only |
| Accidental path escape | Normalize + workspace jail |
| Over-porting Workshop | Port strategies only, not extension host |

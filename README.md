# paper-diff

Web UI for **LaTeX paper version diff + accept merge + full-document Docker compile**.

- **Frontend:** Vue 3 + Monaco Diff (left = merged, right = revised) + PDF.js  
- **Backend:** Python FastAPI (workspace, align, merge, compile)  
- **Design:** [docs/superpowers/specs/2026-07-15-paper-diff-design.md](docs/superpowers/specs/2026-07-15-paper-diff-design.md)

## Quick start (dev)

### API

```bash
cd apps/api
pip install -e ".[dev]"
# Windows PowerShell:
$env:PAPER_DIFF_WORKSPACE_ROOT = "$PWD/../../data/projects"
uvicorn app.main:app --reload --port 8000
```

### Web

```bash
cd apps/web
npm install
npm run dev
```

Open http://127.0.0.1:5173 — import two zip snapshots (base / revised).

### Tests

```bash
cd apps/api && pytest -v
cd apps/web && npm test
```

### Docker TeX image (for compile)

```bash
docker build -t paper-diff-texlive:latest docker/texlive
```

Image is Debian + TeX Live base + latexmk (~550MB). Without Docker / without image,
**Compile** returns an actionable error (`DOCKER_UNAVAILABLE` / `IMAGE_MISSING`).

Smoke test (runs only if image present):

```bash
cd apps/api && pytest tests/test_compile_smoke.py -v
```

### Git dual-ref import

API:

```http
POST /api/v1/projects/{id}/versions/git
{
  "repo_url": "D:/path/to/repo",
  "base_ref": "<sha-or-branch>",
  "revised_ref": "<sha-or-branch>",
  "subdir": "paper/"   // optional
}
```

UI toolbar also has repo / base / revised / subdir fields.

## Workflow

1. Upload `base.zip` + `revised.zip` (or Import git dual refs).  
2. Open a modified `.tex` in the file list.  
3. Accept sentence / word / hunk chips (right → left merged).  
4. File-level ops: Add / Delete / Replace all from the file tree.  
5. Undo / Export merged zip / Accept report JSON.  
6. Compile merged tree (async) with latexmk in Docker → PDF; optional **latexdiff PDF**.  
7. Toggle auto-compile (debounced after accept). Click compile errors to jump.

## Embed into a host app

```ts
import { mountPaperDiff } from "./src/embed";

const handle = mountPaperDiff(document.getElementById("root")!, {
  apiBase: "http://127.0.0.1:8000",
  projectId: undefined, // or existing id
  autoCompile: true,
});
// handle.destroy()
```

## API highlights

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/v1/projects` | create |
| POST | `.../versions/upload` | base+revised zip |
| POST | `.../versions/git` | dual ref |
| POST | `.../accept` | range ops |
| POST | `.../accept-file` | add/delete/replace_all |
| POST | `.../compile` | async latexmk |
| POST | `.../compile/latexdiff` | annotated PDF side path |
| GET | `.../events` | SSE |
| GET | `.../export/merged.zip` | |
| GET | `.../export/accept-report.json` | |

## Fixture

`fixtures/sample-base.zip` / `sample-revised.zip` and trees under `fixtures/sample/`.

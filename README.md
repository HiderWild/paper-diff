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

### Docker TeX image (optional, for compile)

```bash
docker build -t paper-diff-texlive:latest docker/texlive
```

Without Docker, **Compile** returns a clear failure (`DOCKER_UNAVAILABLE` / docker not on PATH).

## Workflow

1. Upload `base.zip` + `revised.zip` (same relative tree).  
2. Open a modified `.tex` in the file list.  
3. Accept sentence / word / hunk chips (right → left merged).  
4. Undo / Accept file / Export merged zip.  
5. Compile merged tree with latexmk in Docker → PDF preview.

## Fixture idea

Create two small multi-file trees under `fixtures/` and zip them for manual QA.

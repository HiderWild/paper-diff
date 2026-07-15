# paper-diff agent notes

## Commands

- API tests: `cd apps/api && pytest -v`
- API run: `cd apps/api && uvicorn app.main:app --reload --port 8000`
- Web: `cd apps/web && npm install && npm run dev`
- Web tests: `cd apps/web && npm test`
- TeX image: `docker build -t paper-diff-texlive:latest docker/texlive`

## Env

- `PAPER_DIFF_WORKSPACE_ROOT` — project storage (default `./data/projects`)
- `PAPER_DIFF_TEX_IMAGE` — default `paper-diff-texlive:latest`
- `PAPER_DIFF_DOCKER_ENABLED` — default true
- `PAPER_DIFF_COMPILE_TIMEOUT_S` — default 120

## Architecture pointers

- Spec: `docs/superpowers/specs/2026-07-15-paper-diff-design.md`
- Merge line/col: `apps/api/app/domain/merge_engine.py`
- Accept/import: `apps/api/app/services/project_service.py`
- Compile: `apps/api/app/services/compile_service.py`
- Sentence mapper: `apps/web/src/features/diff/sentenceMapper.ts`

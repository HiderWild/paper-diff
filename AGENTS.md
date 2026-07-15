# paper-diff agent notes

## Commands

- API tests: `cd apps/api && pytest -v`
- API run: `cd apps/api && uvicorn app.main:app --reload --port 8000`
- Web: `cd apps/web && npm install && npm run dev`
- Web tests: `cd apps/web && npm test`
- TeX image: `docker build -t paper-diff-texlive:latest docker/texlive`
- Compile smoke: `cd apps/api && pytest tests/test_compile_smoke.py -v`
- Git import API: `POST /api/v1/projects/{id}/versions/git`

## Env

- `PAPER_DIFF_WORKSPACE_ROOT` — project storage (default `./data/projects`)
- `PAPER_DIFF_TEX_IMAGE` — default `paper-diff-texlive:latest`
- `PAPER_DIFF_DOCKER_ENABLED` — default true
- `PAPER_DIFF_COMPILE_TIMEOUT_S` — default 120
- `PAPER_DIFF_MAX_UPLOAD_MB` — zip size limit per side (default 500)
- `PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP` — wipe workspace on API start (default **true**, for dev disk; set `false` to keep projects)

## Architecture pointers

- Spec: `docs/superpowers/specs/2026-07-15-paper-diff-design.md`
- Plan status: `docs/superpowers/plans/2026-07-15-paper-diff-implementation.md`
- Workbench track: `docs/superpowers/plans/2026-07-15-workbench-git-async-diff.md`
- **Product v2 (project core + zones + git + agent):** `docs/superpowers/plans/2026-07-15-project-core-zones-git-llm.md`
- Merge line/col: `apps/api/app/domain/merge_engine.py`
- Accept/import: `apps/api/app/services/project_service.py`
- Compare queue (lazy): `apps/api/app/services/compare_service.py`
- Root candidates: `apps/api/app/domain/root_detect.py` + `POST /projects/{id}/root`
- Git facade status/commit: `apps/api/app/services/git_service.py`
- Compile async/SSE/latexdiff: `apps/api/app/services/compile_service.py` (requires user-selected root)
- Sentence mapper: `apps/web/src/features/diff/sentenceMapper.ts`
- File tree: `apps/web/src/features/tree/`
- Layout store (resizable panes): `apps/web/src/stores/layout.ts`
- Pinia project store: `apps/web/src/stores/project.ts`
- Embed: `apps/web/src/embed.ts` → `mountPaperDiff`
- i18n (zh-CN default / en): `apps/web/src/i18n/`

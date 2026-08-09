# paper-diff agent notes

## Commands

- API tests (no Docker): `cd apps/api && pytest -v --ignore=tests/test_compile_smoke.py`
- API tests (all): `cd apps/api && pytest -v`
- API run: `cd apps/api && uvicorn app.main:app --reload --port 8000`
- Web: `cd apps/web && npm install && npm run dev`
- Web tests: `cd apps/web && npm test`
- Web typecheck: `cd apps/web && npx vue-tsc -b`
- Manual smoke: `docs/superpowers/manual-smoke.md`
- CI-ish gate: api pytest (ignore smoke) + `npm test` + `vue-tsc -b`
- TeX image: `docker build -t paper-diff-texlive:latest docker/texlive`
- Compile smoke: `cd apps/api && pytest tests/test_compile_smoke.py -v`
- Git import API: `POST /api/v1/projects/{id}/versions/git`

## 文档语言与代码导航

- 仓库文档的主要语言是中文。自本规则生效后，新建文档以及新增的成段自然语言默认使用中文；术语、缩写、API、代码标识符、命令和必须保持原文的名称可以使用英文。
- 不要求把已经完成或既有的英文文档整体翻译、重写为中文；修改旧文档时只需让本次新增内容遵循上述规则，除非任务明确要求统一语言。
- 获取代码结构、符号关系、调用链和影响范围时优先使用 CodeGraph。进入仓库后若不存在 `.codegraph/`，直接运行 `codegraph init .` 完成初始化；若已存在但有待同步变更，运行 `codegraph sync .`。
- 优先使用 `codegraph files`、`codegraph explore`、`codegraph node`、`codegraph query`、`codegraph callers/callees`、`codegraph impact` 和 `codegraph affected` 理解结构，再按需使用 `rg` 做精确文本或文件搜索。

## Env

- `PAPER_DIFF_WORKSPACE_ROOT` — project storage (default `./data/projects`)
- `PAPER_DIFF_TEX_IMAGE` — default `paper-diff-texlive:latest`
- `PAPER_DIFF_DOCKER_ENABLED` — default true
- `PAPER_DIFF_STORE_AUX` — persist .aux/.bbl after compile for rendered sentence diff (default true; set false for disk-constrained deploys)
- `PAPER_DIFF_COMPILE_TIMEOUT_S` — default 120
- `PAPER_DIFF_MAX_UPLOAD_MB` — zip size limit per side (default 500)
- `PAPER_DIFF_CLEAR_WORKSPACE_ON_STARTUP` — wipe workspace on API start (default **false**; set `true` only for disposable wipes)
- `PAPER_DIFF_AGENT_PROVIDER` — `off` (default) | `http` | `stub` (tests only; do not use stub in product)
- `PAPER_DIFF_AGENT_API_KEY` / `PAPER_DIFF_AGENT_HTTP_URL` — real provider when provider=http

## Architecture pointers

- Storage abstraction / host integration: `docs/architecture/storage-host-integration.md`
- Storage implementation plan: `docs/superpowers/plans/2026-07-19-file-access-layer-abstraction.md`

- Spec: `docs/superpowers/specs/2026-07-15-paper-diff-design.md`（待 R0 补 v2 模型章节）
- Plan status: `docs/superpowers/plans/2026-07-15-paper-diff-implementation.md`
- Workbench track: `docs/superpowers/plans/2026-07-15-workbench-git-async-diff.md`
- **Product v2 (project core + zones + git + agent):** `docs/superpowers/plans/2026-07-15-project-core-zones-git-llm.md`
- **Hardening / gap closure (post-audit R0–R5):** `docs/superpowers/plans/2026-07-15-hardening-followups.md`
- **Import modal + diff chrome + autosave (draft, largely superseded):** `docs/superpowers/plans/2026-07-15-import-diffchrome-autosave.md`
- **UX gap closure v1.1 (scaffold landed; remaining P0 mixed):** `docs/superpowers/plans/2026-07-15-ux-gap-closure.md`
- **Comparer + preview hardening (true-source pull / arrows / word zoom — execute next):** `docs/superpowers/plans/2026-07-15-comparer-preview-hardening.md`
- **Large-file performance v1.1 (Steps 0–2 + light 3–4 in tree; window hydrate + hunk UI deferred):** `docs/superpowers/plans/2026-07-15-large-file-performance.md`
- **Word/phrase hover-accept (complete S-tier + sentence; settings toggle):** `docs/superpowers/plans/2026-07-15-word-hover-accept.md` · matrix `...-matrix.md` · code: `wordHover.ts`, `WordHoverCard.vue`, `MonacoDiff.vue`
- **Sentence rendered diff (path C: aux/bbl + KaTeX; P0+P1 done):** `docs/superpowers/plans/2026-07-15-sentence-rendered-diff.md` · code: `renderTexSentence.ts`, `highlightChangedInRendered.ts`, `useTexContext.ts`, `texSentenceContext.ts`, `WordHoverCard.vue` (sentence branch), `tex_context.py`, `compile_service._store_aux_bbl`

## Completion tiers (use in status claims)

- **L0 main path:** work + zones + accept + compile + local git — **done**
- **L1 API↔UI wiring:** every public API has UI or is explicitly deferred — **partial** (accept-report via command palette; advanced import in modal)
- **L2 product depth:** columns/tabs + sash, unified import, autosave, docx, compare-target with **client true-source pull** (git/zone) — **partial** (hover apply optional; real agent still partial)
- **L3 platform:** remote git auth, multi-tenant, virtualized tree — **deferred**
- Merge line/col: `apps/api/app/domain/merge_engine.py`
- Accept/import (work + dual-zip compat): `apps/api/app/services/project_service.py`
- Zones: `apps/api/app/services/zone_service.py` — `work/` truth + `zones/{id}/tree`
- Compare queue (work↔active zone): `apps/api/app/services/compare_service.py`
- Root candidates: `apps/api/app/domain/root_detect.py` + `POST /projects/{id}/root`
- Git facade (project-local + external): `apps/api/app/services/git_service.py` — status/log/commit/restore/zone-from-commit
- Compile async/SSE/latexdiff: `apps/api/app/services/compile_service.py` (target **work**, requires user-selected root)
- Agent (stub default): `POST /projects/{id}/agent/{analyze,propose,apply,chat}`；env `PAPER_DIFF_AGENT_PROVIDER=stub|off|http`
- Git timeline: `GET .../git/{status,log,diff,show}` · `POST .../git/{commit,restore,zone-from-commit}` · push → 501
- Single work import: `POST /projects/{id}/work/import/zip`
- Zones API: `/projects/{id}/zones` CRUD + activate + import
- Media sniff: `apps/api/app/domain/media.py` · CSV: `POST .../diff/csv-preview`
- Sentence mapper: `apps/web/src/features/diff/sentenceMapper.ts`
- File tree: `apps/web/src/features/tree/`
- Layout store (resizable panes): `apps/web/src/stores/layout.ts`
- Pinia project store: `apps/web/src/stores/project.ts`
- Embed: `apps/web/src/embed.ts` → `mountPaperDiff`
- i18n (zh-CN default / en): `apps/web/src/i18n/`

## Disk layout (v2)

```
{workspace_root}/{project_id}/
  work/                 # editable project body (compile/accept/export)
  zones/{zone_id}/tree  # compare zone snapshot
  zones/{zone_id}/meta.json
  .git/                 # project-local timeline
  base/, revised/       # legacy materialization (compat dual-zip / latexdiff)
  snapshots/, jobs/, artifacts/
  meta.json
```

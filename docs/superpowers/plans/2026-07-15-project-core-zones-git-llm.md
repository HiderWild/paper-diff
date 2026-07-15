# paper-diff 产品重构计划：项目本体 · 比较区 · 内置 Git · Agent 接口

> **Status:** L0 main path done; L1–L2 partial (API/stub ≠ full product) — 2026-07-15  
> **Honesty note:** Phase 0–3 solid; 5–7 partially stub/API-only; Phase 8 partial.  
> **Follow-up plan:** `2026-07-15-hardening-followups.md`（复审缺口补强 R0–R5）  
> **Supersedes (model):** 旧「base + revised + merged」双 zip 对照主路径  
> **Preserves:** 工作台布局、树、编译、Monaco 词/句级可视化、i18n、Docker TeX 等能力底座  
> **Related:**  
> - 旧 MVP：`2026-07-15-paper-diff-implementation.md`  
> - 工作台：`2026-07-15-workbench-git-async-diff.md`  
> - 设计：`docs/superpowers/specs/2026-07-15-paper-diff-design.md`

---

## 完成摘要（2026-07-15）

| Phase | 状态 | 交付 | 缺口（见 hardening plan） |
|-------|------|------|---------------------------|
| 0 基线 | partial | 兼容策略、API 契约 | design spec v2 章节未写全 → R0 |
| 1 项目本体 | **done (L0)** | `work/`、单 zip、export/compile | — |
| 2 比较区 | **done (L0)** | zones CRUD、激活、Accept→work | — |
| 3 Git 时间线 | **done (L0)** | log/commit/restore、两提交 diff/show、zone-from-commit UI | — |
| 4 工作台对齐 | mostly | async compare、活动栏、i18n | 上传进度、预设/命令面板 → R1.4/R4 |
| 5 媒介 | **API partial** | sniffer、csv-preview API、binary 文案 | CSV/图片 **无 UI** → R1.2/R1.3 |
| 6 Agent 契约 | **stub done** | analyze/propose/apply + agent_log | 真 provider、徽章 → R3 |
| 7 Inline chat | **API-only** | chat + SSE stub | **无前端 chat** → R1.1 |
| 8 生态硬化 | partial | health v2、push 501 | 远程/多租户/虚拟列表 → R5 |

---

## 关键 API 面

- Work: `POST .../work/import/zip`, tree/file, export
- Zones: CRUD + activate + import zip/files + from-work
- Git: status/log/commit/restore/diff/show/zone-from-commit；push → 501
- Agent: analyze/propose/apply/chat/chat/stream/sessions（`PAPER_DIFF_AGENT_PROVIDER=stub|off|http`）
- CSV: `POST .../diff/csv-preview`
- Health: `GET /api/v1/health` `{model:"v2"}`

---

## 分阶段清单（历史勾选）

### Phase 0 — 基线
- [x] 模型定稿与兼容策略  
- [x] 验收 fixture（单 zip + zone）

### Phase 1 — 项目本体
- [x] work 导入/树/文件  
- [x] 编译 export 指向 work  
- [x] 双 zip 兼容 → work + zone  

### Phase 2 — 比较区
- [x] zone CRUD + zip/files  
- [x] webkitdirectory  
- [x] Diff 左 work 右 zone；Accept → work  

### Phase 3 — Git
- [x] init + commit + log UI  
- [x] 两提交 name-status + show 打开预览  
- [x] restore discard  
- [x] 从提交创建比较区  

### Phase 4 — 工作台
- [x] 异步 path compare work↔zone  
- [x] 点目录默认跳过  
- [x] i18n 项目/比较区文案  

### Phase 5 — 媒介
- [x] text sniffer 扩展  
- [x] CSV 结构 preview（API）  
- [x] 二进制图片提示（编辑器侧）  

### Phase 6 — Agent
- [x] DTO + stub provider  
- [x] UI 分析/草稿/应用  
- [x] apply + agent_log  

### Phase 7 — Chat
- [x] chat API + 选区上下文  
- [x] SSE stream stub  

### Phase 8 — 硬化
- [x] health / version  
- [x] push 显式未实现  
- [ ] 远程鉴权矩阵（后置）  
- [ ] 多租户（后置）  
- [ ] 大仓虚拟列表（后置）  

---

## 验证

```bash
cd apps/api && pytest -v --ignore=tests/test_compile_smoke.py
cd apps/web && npm test && npx vue-tsc -b
```

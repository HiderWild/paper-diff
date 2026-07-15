# paper-diff 产品重构计划：项目本体 · 比较区 · 内置 Git · Agent 接口

> **Status:** Phase 0–8 implemented (MVP + extensions) — 2026-07-15  
> **Supersedes (model):** 旧「base + revised + merged」双 zip 对照主路径  
> **Preserves:** 工作台布局、树、编译、Monaco 词/句级可视化、i18n、Docker TeX 等能力底座  
> **Related:**  
> - 旧 MVP：`2026-07-15-paper-diff-implementation.md`  
> - 工作台：`2026-07-15-workbench-git-async-diff.md`  
> - 设计：`docs/superpowers/specs/2026-07-15-paper-diff-design.md`

---

## 完成摘要（2026-07-15）

| Phase | 状态 | 交付 |
|-------|------|------|
| 0 基线 | done | 模型文档、兼容策略 |
| 1 项目本体 | done | `work/`、单 zip import、export/compile 指向 work |
| 2 比较区 | done | zones CRUD、zip/folder 导入、激活、Accept 写 work |
| 3 Git 时间线 | done | init/commit/log/status/restore、两提交 diff/show、zone-from-commit、UI |
| 4 工作台对齐 | done | 异步 compare work↔zone、点目录/dot 跳过、活动栏 zones/git/agent、i18n 主文案 |
| 5 媒介 | done | media sniffer、CSV preview API、二进制提示 |
| 6 Agent 契约 | done | analyze/propose/apply + stub provider + agent_log |
| 7 Inline chat | done | chat + SSE stream stub |
| 8 生态硬化 | partial | health v2、push 501、OpenAPI via FastAPI；远程鉴权/多租户后置 |

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

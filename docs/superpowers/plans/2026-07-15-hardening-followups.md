# paper-diff 补强 / 强化计划：诚实闭合 · 产品化缺口 · 质量门槛

> **Status:** R0–R4 executed (L1 wiring + tests + presets/palette) — 2026-07-15  
> **Remaining L3 / optional:** R5 platform items only  
> **Origin:** 对 P0–P5、工作台、v2 三份计划的**二次复审**（验收表 × 路由 × 前端接线 × 测试 × 声称 vs 实质）  
> **Does not supersede** 既有主航道交付；本文件是 **gap closure** 清单  
> **Related:**  
> - MVP：`2026-07-15-paper-diff-implementation.md`  
> - 工作台：`2026-07-15-workbench-git-async-diff.md`  
> - 产品 v2：`2026-07-15-project-core-zones-git-llm.md`  
> - 设计：`docs/superpowers/specs/2026-07-15-paper-diff-design.md`

---

## 0. 复审结论（一句话）

**主航道可交付（MVP + 工作台 core + v2 work/zones/本地 Git），但「Phase 0–8 全部完成」存在完成度虚高：Agent/Chat/媒介/工作台高级布局/设计文档/前端测试未达验收表字面标准。**

本计划把所有发现项拆成 **可勾选阶段**，按优先级推进；**P0 优先纠正文档与阻塞体验的接线缺口**。

---

## 1. 问题总表（按证据分类）

### 1.1 文档过誉 / 口径漂移

| ID | 问题 | 证据 | 严重度 |
|----|------|------|--------|
| D1 | v2 文档 Status 写「Phase 0–8 implemented」 | `project-core-zones-git-llm.md` 头部；Phase 5–8 多项仅 API/stub | P0 |
| D2 | design spec 仍是 base/revised 旧模型 | `paper-diff-design.md` Goals/Core model 无 work/zones | P0 |
| D3 | implementation plan「0–8 implemented」同步过满 | `paper-diff-implementation.md` Next major track | P0 |
| D4 | 工作台 M5「VS Code 高级」易被读成完整阶段 5 | 命令面板/布局预设未做，仅活动栏+底栏 | P1 |

### 1.2 API 有、产品未接（接线空洞）

| ID | 问题 | API | Store | App UI | 严重度 |
|----|------|-----|-------|--------|--------|
| W1 | Agent chat 无入口 | `POST .../agent/chat` + stream | 仅 `api.ts#agentChat` | 无 | P0 |
| W2 | CSV 结构 preview 无入口 | `POST .../diff/csv-preview` | 无 | 无 | P1 |
| W3 | 图片无真实预览 | 无 raw/blob 端点 | `binaryPreview` 文案 | 无 `<img>` | P1 |
| W4 | agent sessions / stream 未接 | sessions + chat/stream | 无 | 无 | P2 |

### 1.3 能力实质是 stub / 降级却被写成「完成」

| ID | 问题 | 实际 | 目标口径 | 严重度 |
|----|------|------|----------|--------|
| S1 | Agent 分析/提议 | 启发式 stub | 文档标明 stub；可选 http provider | P1（文档）/ P2（真 provider） |
| S2 | Chat SSE | 后端 2-token stub | UI + 流式展示；provider 可选 | P0 UI / P2 真流 |
| S3 | git push | 501 | 保持 501 直到鉴权设计 | OK（勿标完成） |
| S4 | 插件式解析器 | 未实现 | Phase 后置或删验收 | P2 |

### 1.4 工作台 / UX 字面缺口

| ID | 问题 | 计划出处 | 严重度 |
|----|------|----------|--------|
| U1 | 布局预设切换 + 导入/导出 JSON | 工作台 A5 / 阶段 5 | P2 |
| U2 | 命令面板 Ctrl/Cmd+Shift+P | 工作台阶段 5 | P2 |
| U3 | 大 zip 上传进度条 | v2 E5 / 工作台 F | P1 |
| U4 | i18n/高级区仍保留 base/revised 兼容文案 | 可接受，但需标注 advanced | P2 |
| U5 | 真机浏览器 walkthrough 未做 | MVP deferred | P1（人工） |

### 1.5 质量 / 测试门槛

| ID | 问题 | 现状 | 严重度 |
|----|------|------|--------|
| T1 | 前端几乎无特性测试 | 仅 sentenceMapper + buildTree | P0 |
| T2 | 无 web↔api 关键 smoke | 手测依赖 | P1 |
| T3 | compile smoke 依赖镜像常跳过 | 需文档/CI 策略 | P2 |
| T4 | Accept 在 git preview 模式行为需回归用例 | 已禁用 chips，缺自动测 | P1 |

### 1.6 产品语义 / 一致性（非阻塞，应收敛）

| ID | 问题 | 建议 |
|----|------|------|
| C1 | file-pair 仍暴露 base/revised/merged | 保留兼容键 + 文档强调 left=work/right=zone |
| C2 | Monaco left=merged 别名 work | 注释/类型别名 `WorkPair` |
| C3 | legacy base/revised 目录仍落盘 | 兼容需要；加 deprecation 注释 |

---

## 2. 目标与非目标

### 2.1 目标

1. **文档诚实**：主航道 / stub / 后置 三层口径固定。  
2. **接线闭合**：已有 API 的 chat / CSV / 图片预览在 UI 可用或明确「未做」。  
3. **体验补强**：上传进度、Agent 对话、媒体预览达到「可用」而非「有路由」。  
4. **质量门槛**：关键路径有自动测；CI 可跑无 Docker 套件。  
5. **设计对齐**：design spec 增加 v2 领域模型章节。

### 2.2 非目标（本补强计划仍不做）

- 完整远程 Git 鉴权矩阵与 PR UI  
- 多租户 / 生产 Auth  
- VS Code mosaic 任意分屏  
- 真 CRDT 协同  
- 浏览器内 TeX 引擎  
- 像素级图片 diff / PDF 文本层 diff  

---

## 3. 完成度分层（强制采用）

| 层 | 含义 | 当前 paper-diff |
|----|------|-----------------|
| **L0 主航道** | 单 work、zones、对照 Accept、编译、本地 Git 提交 | **已交付** |
| **L1 接线完整** | API 与 UI 一一对应；无死链接 API | **未完全**（chat/CSV/图片） |
| **L2 产品深度** | 真 provider、进度条、预设、命令面板 | **部分** |
| **L3 平台化** | 远程 Git、多租户、MCP、性能 | **后置** |

之后所有文档「完成」必须标明层：例如「L0 done / L1 partial」。

---

## 4. 分阶段执行计划

### R0 — 口径修正与设计对齐（0.5–1 天）**【立即】**

**目标：** 停止过誉；设计与代码同一模型。

| 步骤 | 任务 | 验收 |
|------|------|------|
| R0.1 | 改 v2 plan Status → `L0 done; L1 partial; Phase 5–8 partial/stub` | 头部与完成摘要表一致 |
| R0.2 | 改 implementation plan Next track 同口径 | 无「0–8 fully implemented」 |
| R0.3 | design spec 新增「v2 领域模型」：`work` / `zones` / 内置 git / left-right 规则；标注 base/revised 为兼容 | 可从 design 读懂 v2 |
| R0.4 | AGENTS.md 增加本补强计划指针 + 完成度分层说明 | 指针可点 |

**交付物：** 仅文档（可单独 commit：`docs: honest status and v2 design chapter`）

**风险：** 无。

---

### R1 — API↔UI 接线闭合（1–2 天）**【优先工程】**

**目标：** 消灭「有 API 无入口」的 P0/P1 空洞。

#### R1.1 Agent Chat 面板（闭合 W1 / Phase 7 最低验收）

| 步骤 | 任务 | 文件 |
|------|------|------|
| R1.1.1 | store: `doAgentChat(message, selection?)`、`agentChatLog[]` | `stores/project.ts` |
| R1.1.2 | api 已有 `agentChat`；可选 `agentChatStream` 读 SSE | `shared/api.ts` |
| R1.1.3 | Agent 活动栏：消息列表 + 输入框 + 发送；展示 reply / not_configured | `App.vue` |
| R1.1.4 | 可选：从 Monaco 取选区（若 API 易拿）→ selection | `MonacoDiff.vue` / store |
| R1.1.5 | i18n `agent.chat*` | `zh-CN.ts` / `en.ts` |

**验收：**

- [x] 打开文件后 Agent 面板可发送消息  
- [x] stub provider 返回 reply；`PROVIDER=off` 显示 not_configured  
- [x] 至少 1 个 API 测（已有）+ 1 个前端单元/组件测（新建轻测或 e2e 手测清单）

#### R1.2 CSV Preview 最小 UI（闭合 W2）

| 步骤 | 任务 |
|------|------|
| R1.2.1 | store `doCsvPreview()`：对当前 pair left/right 调 API |
| R1.2.2 | 若 path 以 `.csv/.tsv` 结尾，Agent 或 Diff 旁显示「表 diff」面板：changed_rows 列表 |
| R1.2.3 | 非表格文件隐藏入口 |

**验收：**

- [x] 打开 csv + 激活 zone 后可见变更行摘要  
- [x] 上限 max_rows 不炸 UI（≤200）

#### R1.3 图片预览（闭合 W3）

| 步骤 | 任务 |
|------|------|
| R1.3.1 | API：`GET .../work/file-raw?path=` 与 `GET .../zones/{zid}/file-raw?path=`（`FileResponse` / bytes + content-type） |
| R1.3.2 | 安全：复用 `resolve_under`；仅允许图片扩展名 |
| R1.3.3 | 前端：`ImagePreview.vue` 并排 work | zone（若 zone 无则单图） |
| R1.3.4 | openFile 遇 image → 不进 Monaco，显示 ImagePreview |

**验收：**

- [x] png/jpg 可预览  
- [x] path traversal 仍 400  
- [x] 非图片 binary 仍提示文案  

#### R1.4 上传进度（闭合 U3）

| 步骤 | 任务 |
|------|------|
| R1.4.1 | `importWorkZip` / zone zip 改用 `XMLHttpRequest` 或 fetch+Readable 进度回调 |
| R1.4.2 | store `uploadProgress: 0–100 | null` |
| R1.4.3 | toolbar 显示细进度条 |

**验收：** >50MB zip 导入可见进度（本地 mock 可测）。

**R1 完成定义：** L1「主路径 API 无悬空」对 chat/csv/image/upload 成立。

---

### R2 — 质量门槛（1–2 天，可与 R1 并行后半）

**目标：** 关键路径可回归，防再次虚标。

| 步骤 | 任务 | 验收 |
|------|------|------|
| R2.1 | 前端 vitest：store 方法 mock fetch（import work、activate zone、gitDiff、agentAnalyze） | ≥8 新用例 |
| R2.2 | 前端：buildTree / 布局 load 边界已有则扩展；git preview 时 accept 禁用断言 | 绿 |
| R2.3 | API：chat stream 事件形状测；push 501 测；file-raw 安全测 | 绿 |
| R2.4 | `docs/.../manual-smoke.md` 手工 15 步清单（导入→zone→accept→compile→git 两提交） | 文档 |
| R2.5 | CI 建议命令写入 AGENTS：`pytest --ignore=test_compile_smoke` + `npm test` + `vue-tsc` | 可复制 |

**非目标：** Playwright 全量 E2E（可标 R4）。

---

### R3 — Agent / Provider 产品化（2–4 天）

**目标：** stub 诚实；可选真模型。

| 步骤 | 任务 | 验收 |
|------|------|------|
| R3.1 | UI 角标：`provider=stub|off|http`（GET health 或 agent 响应） | 用户可知是否真 AI |
| R3.2 | `PAPER_DIFF_AGENT_HTTP_URL` + key；http 失败降级 stub/off | 有测 |
| R3.3 | apply 走与 accept 相同 undo 快照（若尚未） | undo 可回滚 agent apply |
| R3.4 | agent_log 导出按钮（对接 accept-report 或独立 JSON） | 可下载 |
| R3.5 | Chat stream UI：逐 token 追加 | stream 可见 |

**完成定义：** Phase 6–7 达到「契约 + stub 可用 + http 可插」；**不**要求自研模型质量。

---

### R4 — 工作台高级项（可选 3–5 天）

**目标：** 工作台阶段 5 字面剩余。

| 步骤 | 任务 | 优先级 |
|------|------|--------|
| R4.1 | 布局预设：`files|editor|pdf` / `editor|pdf` / `files|editor` + localStorage | P2 |
| R4.2 | 导出/导入 layout JSON | P2 |
| R4.3 | 命令面板雏形：Compile、Toggle PDF、Commit、Import | P2 |
| R4.4 | 多标签打开文件（可选） | P3 |
| R4.5 | Playwright smoke 1 条 | P2 |

**明确仍属 L（不做）：** 任意方向 mosaic、插件系统。

---

### R5 — 平台与后置（不排期，只列 issue）

| ID | 项 |
|----|-----|
| R5.1 | 远程 git push/pull + 鉴权 |
| R5.2 | MCP / 对外 OpenAPI 稳定版发布说明 |
| R5.3 | 多租户 / Auth |
| R5.4 | 大仓树虚拟列表 / sparse compare |
| R5.5 | 像素级图 diff / CSV 键对齐专业表 |
| R5.6 | design 全量替换旧 base/revised 表述（兼容附录保留） |

---

## 5. 建议实施顺序

```
R0 文档口径 + design v2
  └─▶ R1.1 Chat UI ─┬─▶ R1.2 CSV UI
                    ├─▶ R1.3 图片 raw + preview
                    └─▶ R1.4 上传进度
  └─▶ R2 测试门槛（与 R1 后半并行）
        └─▶ R3 Agent provider 产品化
              └─▶ R4 工作台高级（可选）
                    └─ R5 后置
```

**推荐最小闭环：** **R0 → R1.1 → R1.3 → R2.1 → R2.4**（约 3–5 天可感提升）。

---

## 6. 验收清单（补强完成的定义）

### 6.1 文档

- [x] 任何「完成」均标注 L0/L1/L2/L3  
- [x] design 含 v2 work/zones/git 章节  
- [x] v2 plan 头部不再写全量 0–8 done  

### 6.2 产品

- [x] Agent 可对话（stub）  
- [x] csv 文件有变更摘要入口  
- [x] 常见图片可预览  
- [x] 大 zip 有进度反馈  
- [x] 布局预设 + 命令面板雏形  

### 6.3 质量

- [x] `pytest --ignore=test_compile_smoke` 全绿  
- [x] `npm test` + `vue-tsc` 全绿  
- [x] 前端关键 store 路径有测  
- [x] 手工 smoke 清单可走通（`docs/superpowers/manual-smoke.md`）

---

## 7. 与旧计划的映射（防重复开工）

| 旧项 | 归入本计划 |
|------|------------|
| v2 Phase 7 inline chat | R1.1 + R3.5 |
| v2 Phase 5 CSV/图片 | R1.2 + R1.3 |
| v2 E5 上传进度 | R1.4 |
| v2 Phase 6 真 provider | R3 |
| 工作台阶段 5 预设/命令面板 | R4 |
| 工作台阶段 L / v2 Phase 8 远程 | R5 |
| MVP deferred 真机验收 | R2.4 + U5 |

---

## 8. 风险与决策

| 风险 | 缓解 |
|------|------|
| 继续扩 scope 导致再次虚标 | 每阶段只关一条 L 层；合并前对照 §6 |
| 图片 raw 端点安全 | 强制扩展名白名单 + resolve_under |
| XHR 进度与现有 fetch 风格分裂 | 封装 `uploadWithProgress` 单点 |
| stub 被用户当成真 AI | R3.1 强制 provider 徽章 |

**决策默认：**

1. stub 默认开（开发友好）；生产文档写清 `PROVIDER=off|http`。  
2. 双 zip 高级入口 **保留** 至 L3 废弃公告。  
3. push 保持 501 直到 R5.1 设计评审。

---

## 9. 首批 Issue 拆分（可直接开）

1. `docs: honest L0/L1 status + design v2 chapter`（R0）  
2. `feat(web): agent chat panel wired to /agent/chat`（R1.1）  
3. `feat(api+web): work/zone file-raw image preview`（R1.3）  
4. `feat(web): csv-preview panel for .csv/.tsv`（R1.2）  
5. `feat(web): zip upload progress`（R1.4）  
6. `test(web): pinia store smoke with mocked fetch`（R2.1）  
7. `docs: manual smoke checklist`（R2.4）  
8. `feat(api): optional http agent provider + degrade`（R3.2）  
9. `feat(web): layout presets + command palette`（R4，可选）  

---

## 10. 总结

| 维度 | 状态 |
|------|------|
| 能否用于论文 work + 比较区 + Accept + 编译 + 本地 Git | **能（L0）** |
| 能否宣称「三份计划每一格验收通过」 | **不能** |
| 本补强计划角色 | **把复审缺口变成可执行阶段，先 R0 诚实，再 R1 接线，再 R2 质量** |

**下一步开工默认：R0 → R1.1。**

# paper-diff 补强计划：比较器真源拉取 · 预览缩放 · 中缝交互

> **Status:** **Steps 1–4 implemented** (true-source client apply, arrow rail geometry, memory v2, Word zoom) — 2026-07-15; Step 5 hover optional; Step 6 manual smoke  
> **Origin:** 对「静默缩放 / 对照源记忆 / 中缝箭头」实现的**二次复审**（显示 vs 接受数据流、Word 缺口、箭头几何）  
> **Does not supersede:** `2026-07-15-ux-gap-closure.md`（工作台/导入/autosave 骨架）；**本文件专收比较器 + 预览闭环**  
> **Related:**  
> - UX 总闸：`2026-07-15-ux-gap-closure.md`  
> - v2：`2026-07-15-project-core-zones-git-llm.md`  
> - 补强总表：`2026-07-15-hardening-followups.md`  
> - Agent：`AGENTS.md`  

---

## 0. 一句话

**对照源 UI 已能「看见」zone/git 右侧内容，但箭头/Accept 仍可能写 active zone 或 revised → Git 对照下应用是假完成；Word 无缩放；箭头未贴真中缝。按下列步骤把「看见什么就拉什么」做实，再补预览与交互。**

### 0.1 禁止的声称（完成前）

在 **Step 1 DoD** 勾选前，文档与对外说明**不得**写：

- 「可从任意 Git 提交接受改动」
- 「比较器完整支持自选对照源拉取」

仅可写：「可预览对照；接受默认仍绑定活动比较区（修复中）」。

---

## 1. 问题总表（证据）

### 1.1 关键：接受源 ≠ 显示源

| ID | 问题 | 证据 | 严重度 |
|----|------|------|--------|
| **C0** | 显示右侧可来自 git / 非 active zone；`doAccept` → API 用 `_active_right_side`（active zone 或 revised） | `ToolBody.vue` gitShow/getZoneFileText；`project.ts#doAccept`；`project_service._active_right_side` | **P0** |
| **C1** | 对照路径可与 work 路径不同，accept 的 `file` 仅 work path，右侧 range 按错文件语义 | 选择器 `zonePath`/`gitPath` vs `currentPath` | **P0** |
| **C2** | 行级箭头 unit 常空文本、range 粗造，易 accept 失败或糊块 | `gutterActions.ts` 逐行 pseudo unit | **P0** |
| **C3** | `accept-all` 同样不跟 git 目标 | `doAcceptAll` + 后端 | **P0** |

### 1.2 预览

| ID | 问题 | 证据 | 严重度 |
|----|------|------|--------|
| **P1** | Word 无 Ctrl+滚轮 / 工具条缩放 | `DocxPreview.vue` 仅首开加载 | **P1** |
| **P2** | PDF 静默缩放已有，大文档重绘仍可能顿 | `PdfPane.rezoom` 全量重绘 | **P2** |
| **P3** | 缩放时避免清空 canvas 闪白 — 已有 frag 策略，需回归 | `paintPages` DocumentFragment | **P1** 回归 |

### 1.3 中缝箭头 UX

| ID | 问题 | 证据 | 严重度 |
|----|------|------|--------|
| **G1** | 箭头 `left: 50%` 非 Monaco 真实分缝 | `MonacoDiff.vue` arrow-layer | **P1** |
| **G2** | line/block/hunk 同位置堆叠 | `placeArrows` offset 硬编码 | **P1** |
| **G3** | 拖动分屏后箭头错位 | 无 diff editor layout 监听 | **P1** |
| **G4** | 对调后箭头方向/「拉取」语义易反 | 显示交换 vs API left=work | **P1** |

### 1.4 记忆与产品语义

| ID | 问题 | 证据 | 严重度 |
|----|------|------|--------|
| **M1** | 记忆是项目级单一目标，非 per-work-path | `compareTarget` map `projectId → target` | **P1** |
| **M2** | 打开新文件仍用上次 git 路径字段，易对错文件 | `zonePath`/`gitPath` 默认不随每次 open 强制同步策略未文档化 | **P1** |
| **M3** | 无「当前对照」状态条长期可见（仅 title 片段） | ComparerChrome | **P2** |

### 1.5 延期交互（产品已降级）

| ID | 问题 | 状态 |
|----|------|------|
| **H1** | 红区悬停 1s 气泡应用词级改动 | **P2 / 明确延期**（用户选箭头为主） |

### 1.6 测试与回归

| ID | 问题 | 严重度 |
|----|------|--------|
| **T1** | 无「选 git → 点箭头 → work 变成右侧片段」集成测 | **P0** |
| **T2** | 无「选非 active zone → accept 源正确」测 | **P0** |
| **T3** | 仅有 gutter 启发式单测 | **P1** |

---

## 2. 产品决策（强制口径，实施前锁定）

### 2.1 对照目标（CompareTarget）

```
target =
  | { kind: "zone", zoneId, path }   // path = 区内相对路径
  | { kind: "git",  ref,    path }   // path = 提交内路径
  | { kind: "active-zone-same-path" } // 兼容：active zone + work 同路径（默认）
```

- **左侧（work）路径** `workPath`：始终是 tree 打开的项目文件。  
- **右侧路径** `target.path`：可与 workPath 不同；**拉取时以 range 从右侧文本切片，写入 workPath 对应左侧 range**。  
- 记忆：**建议 per-project 默认 target + 可选 per-workPath 覆盖**（Step 3）。

### 2.2 拉取实现策略（推荐混合，保证真源）

| 场景 | 策略 |
|------|------|
| active zone 且 `target.path === workPath` | 可继续走服务端 `POST /accept`（已有 merge/revision） |
| 非 active zone 或 path 不同 | **客户端**根据 unit 的 right 文本替换 left 范围 → `PUT work/file`（或新 API `apply-snippet`） |
| git 对照 | **一律客户端**切片 + PUT；禁止假装服务端 accept 读了 git |

> 可选长期：后端 `accept` 增加 `source: { type, id, path }`。本计划 **Step 1 以客户端真源优先**，避免假完成。

### 2.3 箭头语义

| 符号 | 含义 | 行为 |
|------|------|------|
| ← | 行 | 将对照侧对应行文本写入 work 侧该行 |
| ⇐ | 块 | 连续非空行构成的改动块一次写入 |
| ⟸ | hunk | Monaco line-change 整块写入 |

方向固定 **对照 → 项目（work）**；`sidesSwapped` 只改显示，**不改箭头含义**（箭头始终表示「采用对照版」）。

### 2.4 缩放

- PDF/Word：缩放过程 **禁止** 全宽「加载中」条。  
- 允许角落极弱指示（可选）；默认完全静默。

---

## 3. 实施步骤（按序）

每步结束：相关 vitest +（触及 API 时）pytest + `vue-tsc -b` 绿；本文件勾选。

### Step 0 — 基线与复现脚本（≤2h）

- [ ] 手工复现矩阵记入 `docs/superpowers/manual-smoke.md` 小节「Comparer false-accept」：  
  - active zone 同路径 accept 箭头  
  - **git 提交对照 → 箭头后 work 是否等于右侧**（当前期望失败）  
- [ ] 冻结：`compareTarget` key、`doAccept` 调用点  
- [ ] Status → `In progress · Step 0`

**G/W/T：** When 对 git 目标点箭头，Then 录得 work 与右侧不一致（证明 C0）。

---

### Step 1 — 真源拉取闭环（C0–C3, T1–T2）〔P0〕

**目标：** 屏幕右侧是什么，拉进来就是什么。

1. [x] 引入 `applyCompareSnippet(workPath, leftRange, rightText)`：  
   - 在 work 全文中按 line/col 替换为 `rightText`  
   - `putWorkFile` + 更新 revision（`getFilePair` 或 put 返回）  
   - `markDirty`/`clearDirty` 与 autosave 协调（PUT 后 clear）  
   - 落地：`features/diff/applySnippet.ts` + `project.applyCompareUnit` / `applyCompareFileAll`  
2. [x] `onPullUnit` / `doAccept` 分支：  
   - 若 target 为 git 或 zone 非 active 或 path≠work → **snippet 路径**  
   - 若 active zone 同路径 → 可保留 `acceptOps`  
   - 箭头拉取（ToolBody 传入左右 buffer）一律客户端真源  
3. [x] `doAcceptAll`：对 git/异源 → 整文件右侧内容 `putWorkFile`（或逐 hunk snippet）  
4. [x] 行/块 unit 必须带 **真实 rightText**（从当前右侧全文 `sliceRange`），禁止空文本 accept  
5. [x] 测试：  
   - 单元：`applySnippet.test.ts` 替换边界  
   - mock：`project.applyCompare.test.ts`（git/异源 pull → putWorkFile 期望切片）  

**G/W/T：**

- Given 右侧来自 commit `A` 的文案 `R`，When 点箭头，Then work 对应范围变为 `R` 且再次打开仍在  
- Given 非 active zone，When 拉取，Then 不来自 active zone  

**回滚：** feature flag `COMPARE_CLIENT_APPLY=true` 默认真；关则旧 accept-only。

---

### Step 2 — 箭头几何与优先级（G1–G4）〔P1〕

1. [x] 读取 Monaco Diff 中缝：`getOriginalEditor`/`getModifiedEditor` 布局 width 算中线 `left` px  
2. [x] 监听两侧 scroll + layout + option 变化，重放 `placeArrows`  
3. [x] 同一 `leftLine` 只显示一个主箭头；block/hunk 用不同 glyph 或长按/次按钮，避免三箭叠一处  
4. [x] 文档：`sidesSwapped` 下箭头仍「采用对照」  

**G/W/T：** 拖分屏后箭头仍贴中缝 ±4px；滚动不漂。

---

### Step 3 — 记忆与打开策略（M1–M2）〔P1〕

1. [x] `memory[projectId].default` + `memory[projectId].byWorkPath[path]`  
2. [x] 打开 work 文件：优先 byWorkPath，否则 default，再否则 active zone 同路径  
3. [x] UI：对照选择器显示「已记住 · 本文件 / 项目默认」  
4. [x] 切换文件时若 path 变，自动把 zonePath/gitPath 默认填为当前 work path（可改）  

**G/W/T：** 文件 A 记 git:abc，文件 B 记 zone:Z；切换 A/B 右侧正确。

---

### Step 4 — Word 缩放 + PDF 回归（P1–P3）〔P1〕

1. [x] DocxPreview：CSS `transform: scale` 或 font/zoom 控件 + Ctrl+滚轮（**静默**，不 loading）  
2. [ ] PDF：保持 frag 交换；可选缩放时 throttle  
3. [ ] 手工：缩放 10 次无「加载中」横幅、无明显整页空白闪断  

---

### Step 5 — 可选：悬停 1s 词级（H1）〔P2 / 可延期〕

1. [ ] 仅 `granularity===word|sentence`  
2. [ ] 悬停红区 1s → 气泡「采用此改动」→ 走 Step1 snippet  
3. [ ] 与箭头不冲突：词级默认气泡，行/块默认箭头  

---

### Step 6 — 文档与声称（T*, DoD）〔P1〕

1. [ ] `manual-smoke.md`：Comparer 真源矩阵全绿勾选  
2. [ ] 更新 `AGENTS.md` L2：compare target apply 状态  
3. [ ] 本计划 Status → `P0 done` / `complete`  
4. [ ] 删除或改写任何「Git 接受已完成」过誉句  

---

## 4. 排期

| 步骤 | 预估 | 依赖 |
|------|------|------|
| 0 基线复现 | 1–2h | — |
| 1 真源拉取 | 1.5–2.5d | 0 |
| 2 箭头几何 | 0.5–1d | 1 可并行后半 |
| 3 记忆 | 0.5d | 1 |
| 4 Word/PDF | 0.5–1d | — |
| 5 悬停 | 1d | 1 |
| 6 文档 | 0.5d | 1–4 |

---

## 5. 完成定义

### P0 DoD（必须）

- [ ] C0–C3 关闭（git / 非 active zone 拉取 = 右侧可见文本）  
- [ ] T1、T2 自动化绿  
- [ ] manual-smoke 真源矩阵手测通过  
- [ ] 无「假 Git 接受」对外声称  

### P1 DoD（本迭代默认）

- [ ] G1–G3、M1–M2、P1、P3  

### P2

- [ ] H1、P2、M3 可 §6 延期  

---

## 6. 延期登记

| ID | 延期原因 | 重开条件 |
|----|----------|----------|
| H1 | 用户选箭头为主 | 词级纠错抱怨上升 |
| 后端 accept 扩 source | Step1 客户端已够用 | 需审计/并发 revision 与服务端一致时 |

---

## 7. 文件触点

| 区域 | 路径 |
|------|------|
| 拉取真源 | `stores/project.ts`、`components/workbench/ToolBody.vue`、可选 `api.ts` putWorkFile |
| 对照记忆 | `stores/compareTarget.ts`、`ComparerChrome.vue` |
| 箭头 | `features/diff/MonacoDiff.vue`、`gutterActions.ts` |
| 切片工具 | `sentenceMapper.ts` sliceRange / 新 `applySnippet.ts` |
| PDF/Word | `features/preview/PdfPane.vue`、`DocxPreview.vue` |
| 后端（可选） | `project_service.accept`、`dto` 增加 source |
| 测试 | 新 `applySnippet.test.ts`、api/e2e 级 mock |
| 文档 | 本文件、`manual-smoke.md`、`AGENTS.md` |

---

## 8. 与既有计划

```
ux-gap-closure          ── 已交付骨架 ──►  本计划专治「假拉取」
hardening-followups     ── 不重复 R1 媒体 ──►  本计划 P1 Word 缩放
project-core accept API ── 可选增强 source ──►  Step1 优先客户端
```

---

## 9. 执行前检查单

- [ ] 是否理解：右侧 git ≠ 后端 `_active_right_side`？  
- [ ] Step1 是否用真实 `rightText` 而非空 unit？  
- [ ] 异路径是否定义为「切片写入 work」而非「换 work 路径」？  
- [ ] 自动化是否覆盖 git 拉取？  
- [ ] 完成后是否改过誉文档？  

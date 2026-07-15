# paper-diff UX 缺口闭合计划：导入 · 工作台 · 顶栏 · 编辑保存

> **Status:** Ready to execute — 2026-07-15  
> **Origin:** 对「近期对话需求 vs 代码落地」的二次复审（栏/Tab、导入模态、设置主题、工具条、类型拖放 toast、docx、审查清单）  
> **Does not supersede:** `project-core-zones-git-llm.md`、`hardening-followups.md`；本文件专收 **产品可见 UX 缺口**  
> **Related:**  
> - 导入草稿：`2026-07-15-import-diffchrome-autosave.md`（本计划合并并 supersede 其中未执行的 I\*/A\*/S\*/C\* 落地项）  
> - 工作台：`2026-07-15-workbench-git-async-diff.md`  
> - 补强：`2026-07-15-hardening-followups.md`  
> - Agent 说明：`AGENTS.md`  

---

## 0. 一句话

**列/Tab 与统一导入已有骨架，但拖放精度、尺寸调节、导入预览/高级源、顶栏职责、自动保存与设置残留未闭环；按下列步骤逐项勾选到可验收。**

---

## 1. 复审缺口总表（本计划范围）

### 1.1 工作台（栏 / Tab / 输出）

| ID | 缺口 | 现状证据 | 目标 | 严重度 |
|----|------|----------|------|--------|
| **WB1** | 列宽/行高不可拖 | `WorkbenchGrid` 缝仅 drop，无 mousedown sash | 列间/行间 **可拖改 size** 并 persist | P0 |
| **WB2** | 整栏拖动手势过宽 | tab bar 整行 `draggable`，非仅 gutter | **仅 gutter**（无 Tab 占满的空白区）可拖整栏；Tab 本体只拖 Tab | P0 |
| **WB3** | Tab 插入位置粗糙 | 中心 drop→`tab-append` | 栏内 body 中心=并入当前栏；Tab 条按半宽精确 index | P1 |
| **WB4** | 边区/缝高亮反馈弱 | 有 `data-edge`，缝 `active` 偶发不同步 | drop 全程 preview 与最终 intent 一致；离开清除 | P1 |
| **WB5** | 均分非真·三等分 | `size=1` 均分 | 插入后该行 **等分 flex**（文档口径即可）；无需像素三等分 | P2（验收文案） |
| **WB6** | 输出与旧底栏语义并存 | `showBottom` 设置项仍在 | 删除/改写设置「显示底栏」；输出只走 workbench Tab | P1 |
| **WB7** | 旧 layout `mainOrder`/`pdf` 与 workbench 双轨 | `layout.ts` + `workbench.ts` | 文档标明：活动栏+侧栏用 layout；中心编辑区用 workbench；去掉失效假设 | P1 |

### 1.2 导入

| ID | 缺口 | 现状证据 | 目标 | 严重度 |
|----|------|----------|------|--------|
| **IM1** | 项目 zip 仅本地路径列表，无服务端冲突语义 | `listZipEntryPaths` + 确认后 `import_work_zip` | 预览标明「将替换/覆盖项目树」；文件/文件夹可走 dry-run（若已有项目） | P0 |
| **IM2** | 比较区无 dry-run | 仅本地 paths | 可选：比对 work 树标「仅 zone 新增」列表；至少明确「新建 zone、不影响 work」文案 | P1 |
| **IM3** | 冲突策略不可配 | 提示默认覆盖 | 预览冲突时可选 overwrite/skip/rename（复用 `ConflictImportModal` 策略） | P1 |
| **IM4** | 双 ZIP / Git 导入入口丢失 | `doUpload`/`doGitImport` 存 store，无 UI | 导入模态 **高级折叠**：双 ZIP + Git refs | P0 |
| **IM5** | 名称字段用途不一致 | zone 用 name；project 名未写 meta 显示名 | project：写入 status/标签或 `meta.display_name`；zone：继续作 zone.name | P1 |
| **IM6** | 「向项目添加文件」与统一导入双路径 | 顶栏 `import.addFiles` + dry-run 冲突 | 并入导入模态「补充到当前项目」模式，或 Explorer 菜单；顶栏去掉重复 | P1 |

### 1.3 顶栏 / 比较器 chrome

| ID | 缺口 | 现状证据 | 目标 | 严重度 |
|----|------|----------|------|--------|
| **TB1** | 「接受整文件」仍在全局顶栏 | `toolbar.acceptFile` + `onAcceptAll` | 移入 **比较器 Tab 工具条**（有 pair 时）；顶栏删除 | P0 |
| **TB2** | 左右对调 UI 未进 workbench Tab | store `sidesSwapped` | 比较器 chrome 显示 ⇄；标题展示 项目↔区 | P0 |
| **TB3** | 单元 Accept 条与 Monaco 未挂在 Tab 内 | 旧 App 单元条随主比较器移除/弱化 | 活跃 comparer Tab 内恢复 unit chips + 接受整文件 | P0 |
| **TB4** | 顶栏仍偏挤 | compile×2、export、preset… | 本计划只强制 TB1–3；其余可命令面板（可选 P2） | P2 |

### 1.4 编辑 / 自动保存

| ID | 缺口 | 现状证据 | 目标 | 严重度 |
|----|------|----------|------|--------|
| **AS1** | 无全局自动保存 | 无 idle timer | 设置开关默认 **开**；脏编辑 3s 空闲 `PUT work/file` | P0 |
| **AS2** | Monaco 比较器/编辑器可写性未产品化 | Diff 侧仍偏只读 | editor Tab：可编辑 work 侧；comparer：左侧 work 可写（或明确只读+仅 Accept）—— **采用：editor 可写；comparer 左侧可写 + Accept 并存** | P0 |
| **AS3** | 脏标记 / 关闭 Tab 未提示 | 无 | Tab 标题 `·` 脏点；关 Tab 若脏则确认或先 flush | P1 |

### 1.5 设置 / 主题 / 清理

| ID | 缺口 | 现状证据 | 目标 | 严重度 |
|----|------|----------|------|--------|
| **ST1** | 设置「显示底栏输出」过时 | `SettingsPanel` `showBottom` | 改为「确保存在输出 Tab」或删除 | P1 |
| **ST2** | 文件栏/侧栏硬编码色 | 部分已修 `8d14b86` | 审计剩余 `#121a24`/`#243044` 等深色硬编码 | P1（进行中） |
| **ST3** | 自动保存开关入口 | 无 | 设置 → 工作台/编辑 | P0（随 AS1） |

### 1.6 导出 / 审计入口（复审捎带）

| ID | 缺口 | 目标 | 严重度 |
|----|------|------|--------|
| **EX1** | accept-report / agent log 无 UI | Git 面板或命令面板加「导出接受日志」 | P2 |
| **EX2** | 布局预设 JSON 导入/导出 | 设置或命令：export/import `paper-diff-workbench-v2` + layout | P2 |

### 1.7 测试 / 文档

| ID | 缺口 | 目标 | 严重度 |
|----|------|------|--------|
| **QA1** | workbench sash / gutter 无组件测试 | 启发式已测；补 `moveColumn`/`applyDrop` 边界 + 尺寸 persist | P1 |
| **QA2** | ImportModal 无组件/集成测 | zip 列表测已有；补 defaultName、高级分支 mock | P1 |
| **QA3** | AGENTS / 计划状态 | 本文件挂链；更新 completion 说明 | P1 |
| **QA4** | 手工 smoke 清单补 UX | `manual-smoke.md` 增导入/拖栏/自动保存 | P1 |

---

## 2. 范围外（明确不做）

- 远程 Git 鉴权 / push 产品化（L3）
- 多租户 / 虚拟化超大树
- 真 LLM provider 训练与计费
- 插件式解析器全量
- Word 桌面级排版 1:1（docx 继续 best-effort）

---

## 3. 实施步骤（按序执行）

每步结束：**可演示 + 相关 vitest/pytest + `vue-tsc -b` 绿**。勾选时改本文件 Status 行。

### Step 0 — 基线冻结（0.5h）

- [ ] 记录当前 key：`paper-diff-workbench-v2`、`paper-diff-settings-v1`、`paper-diff-layout-v3`
- [ ] 跑：`cd apps/web && npm test && npx vue-tsc -b`；`cd apps/api && pytest -q --ignore=tests/test_compile_smoke.py`
- [ ] 本文件 status → `In progress · Step 0 done`

### Step 1 — 顶栏减负 + 比较器 chrome（TB1–TB3）〔P0〕

**目标：** 会话级动作回到比较器 Tab。

1. [ ] 在 `ToolBody` / 新 `ComparerChrome.vue` 中，当 `tab.kind==='comparer'`：
   - 标题：`比较器 · {left} ↔ {right}`（尊重 `sidesSwapped`）
   - 按钮：⇄ 对调、接受整文件、（有 units 时）粒度 chip
2. [ ] 从 `App.vue` 顶栏移除「接受整文件」
3. [ ] 单元 Accept 仍走 `store.doAccept` / `doAcceptAll`；`MonacoDiff` 继续 `@units` 上报
4. [ ] i18n 确认中英
5. [ ] 手工：打开比较 → 顶栏无接受整文件 → Tab 内可接受/对调

**验收：** TB1–TB3 勾完。

### Step 2 — 工作台 sash + 拖动手势收紧（WB1–WB4, WB6）〔P0–P1〕

**目标：** 可调大小；拖整栏只从 gutter。

1. [ ] `WorkbenchGrid`：列缝 `mousedown` → 调相邻 `column.size`（按 flex 比例或 px→weight）
2. [ ] 行缝同理调 `row.size`
3. [ ] `WorkbenchColumn`：Tab 按钮 `draggable`；**gutter only** `draggable` 设 column payload；禁止整 tabbar 误拖
4. [ ] drop preview：`dragover` 连续更新 `dropPreview`；`dragleave`/`drop` 清除
5. [ ] 设置：去掉 `showBottom` 或改为「打开输出 Tab」按钮调用 `openTool('output')`
6. [ ] 测试：尺寸 persist 读回；gutter intent 单测扩展

**验收：** 用户可拖宽窄/高低；误拖整栏减少；设置无「幽灵底栏」。

### Step 3 — 导入模态闭环（IM1–IM6, IM4 优先）〔P0–P1〕

**目标：** 一个入口覆盖项目/区/补充/高级。

1. [ ] `ImportModal` 扩展：
   - **模式**：自动（无 project→项目；有→区）+ 显式子选项「补充到项目 work」（当已有 project）
   - **高级**：双 ZIP（base+revised）、Git（repo/base/revised/subdir）
2. [ ] 确认前预览：
   - zip/folder/files：路径列表 + 计数
   - 补充：调用 `dry-run`，冲突可打开策略（复用 ConflictImport）
   - 项目全量 zip：警告「将重建/覆盖 work 树」
   - 比较区：说明「新建比较区，不修改 work」
3. [ ] `onImportConfirm` 分支：zip work / files replace / zone zip|files / dual-zip / git / supplement
4. [ ] 顶栏移除「向项目添加文件」；改由导入模态「补充」
5. [ ] 名称：`meta.display_name` 或 status 展示 project 名；zone 用现有 `name`
6. [ ] 测试：modal 路径/高级分支（mock store）；zipList 保持

**验收：** 顶栏只有「导入」；高级 Git/双 ZIP 可用；补充冲突可控。

### Step 4 — 编辑器可写 + 自动保存（AS1–AS3, ST3）〔P0–P1〕

**目标：** 改 work 文件可落盘，默认自动保存。

1. [ ] `settings`：`autoSave: boolean` 默认 `true`；设置面板开关
2. [ ] `editor` Tab 与 `comparer` 左侧：Monaco `originalEditable` / 可写侧打开；变更 → store `dirtyPaths`
3. [ ] debounce 3s：`PUT .../work/file`（现有 API）；手动保存命令可选
4. [ ] 关 Tab：若 dirty → 先 flush 或 confirm
5. [ ] 测试：debounce mock timer；设置默认值

**验收：** 改 tex → 等待 3s → 刷新仍在；关自动保存则不写。

### Step 5 — 主题/残留清理 + 导出入口（ST2, EX1–EX2, WB7）〔P1–P2〕

1. [ ] rg 硬编码 `#121a24|#0b0f14|#243044` 于 `apps/web/src`，能换变量则换
2. [ ] AGENTS.md 标明 layout vs workbench 双 store 职责
3. [ ] 命令面板：`导出接受日志`、`导出/导入布局 JSON`（可选文件下载）
4. [ ] 手工浅色主题截图：文件栏、活动栏、工作台 header

### Step 6 — 质量与文档（QA1–QA4）〔P1〕

1. [ ] 单测覆盖：sash persist、import confirm 分支、autoSave
2. [ ] 更新 `docs/superpowers/manual-smoke.md`：
   - 导入项目/区/补充/Git
   - 拖 Tab 拆栏、拖 gutter、改尺寸
   - 比较器 chrome 接受/对调
   - 自动保存
3. [ ] 本计划 Status → `Steps 0–6 done` 或注明剩余
4. [ ] 可选：将 `import-diffchrome-autosave.md` 头部改为 **Superseded by this plan**（保留历史）

---

## 4. 建议排期（参考）

| 步骤 | 预估 | 依赖 |
|------|------|------|
| 0 基线 | 0.5h | — |
| 1 比较器 chrome | 0.5–1d | — |
| 2 workbench sash/drag | 1–1.5d | — |
| 3 导入闭环 | 1–1.5d | Step0 |
| 4 自动保存/可写 | 1–2d | API put file 已有 |
| 5 清理/导出 | 0.5d | 1–4 |
| 6 测试文档 | 0.5d | 1–5 |

可并行：Step1 ∥ Step2 起手；Step3 与 Step4 在接口层独立。

---

## 5. 完成定义（DoD）

- [ ] 复审表中 **P0 项全部勾选**
- [ ] P1 项完成或有「显式延期 + 原因」写入本文件 §6
- [ ] `npm test` + `vue-tsc -b` + api pytest（ignore smoke）绿
- [ ] `manual-smoke.md` 新增 UX 段可走通
- [ ] 不在文档中声称「VS Code 级」除非 WB1–WB4 完成

---

## 6. 延期登记（执行中填写）

| ID | 延期原因 | 重开条件 |
|----|----------|----------|
| _(none yet)_ | | |

---

## 7. 文件触点（实施索引）

| 区域 | 主要路径 |
|------|----------|
| Workbench | `apps/web/src/stores/workbench.ts`、`components/workbench/*` |
| 导入 | `features/import/ImportModal.vue`、`zipList.ts`、`App.vue` `onImport*`、`stores/project.ts` |
| 比较器 chrome | `components/workbench/ToolBody.vue` 或新 `ComparerChrome.vue`、`features/diff/MonacoDiff.vue` |
| 设置/自动保存 | `stores/settings.ts`、`features/settings/SettingsPanel.vue` |
| 主题 | `styles.css`、FileTree/TreeNodeView/App scoped |
| API | 已有 `PUT work/file`、`work/import/*`、`versions/git`、accept-report export |

---

## 8. 与既有计划关系

```
import-diffchrome-autosave.md  ──(未执行项)──►  本计划 Step 1/3/4
hardening-followups.md         ──EX/布局预设──►  本计划 Step 5 (P2)
workbench-git-async-diff.md    ──sash/命令──►  本计划 Step 2
project-core-zones-git-llm.md  ──L0 保持──►  不回退
```

**声称规范：** 完成后更新 `AGENTS.md` Completion tiers：将「import modal + workbench columns」写入 L1/L2 已交付描述；自动保存写入 L2。

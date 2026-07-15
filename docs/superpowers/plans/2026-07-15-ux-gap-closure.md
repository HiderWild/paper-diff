# paper-diff UX 缺口闭合计划：导入 · 工作台 · 顶栏 · 编辑保存

> **Status:** Ready to execute · **v1.1 二次复审补强** — 2026-07-15  
> **Origin:** 对「近期对话需求 vs 代码落地」的复审 + **对本计划本身的二次复审**（顺序/歧义/回归/验收可测性）  
> **Does not supersede:** `project-core-zones-git-llm.md`、`hardening-followups.md`；本文件专收 **产品可见 UX 缺口**  
> **Related:**  
> - 导入草稿（历史）：`2026-07-15-import-diffchrome-autosave.md`  
> - 工作台：`2026-07-15-workbench-git-async-diff.md`  
> - 补强：`2026-07-15-hardening-followups.md`  
> - Agent：`AGENTS.md`  

---

## 0. 一句话

**列/Tab 与统一导入已有骨架，但拖放精度、尺寸调节、导入预览/高级源、顶栏职责、自动保存与设置残留未闭环；按下列步骤逐项勾选到可验收。**

### 0.1 二次复审发现的计划病（v1.1 已修补）

| 病 | 说明 | 本版处理 |
|----|------|----------|
| **顺序倒置** | 原 Step1 比较器 chrome 依赖 Monaco 可写/units 上报，却把 AS 放 Step4 | **重排：先可写底座(AS 基础) → chrome → sash → 导入** |
| **产品歧义** | 「comparer 左侧可写 + Accept」与 zone 右侧、对调语义冲突未写清 | **§1.4 决策树** |
| **布局双轨** | 顶栏仍有 togglePdf / showPdf，中心已是 workbench | **WB8 新增：拆除失效 PDF 主 pane 假设** |
| **主题未接 Monaco** | Diff 固定 `theme: "vs-dark"` | **ST4 新增** |
| **回归面** | 删高级导入/底栏时无「能力矩阵」 | **§2.1 能力矩阵 + 回归清单** |
| **验收不可测** | 「用户感觉像 VS Code」无法勾选 | 每步 **Given/When/Then + 自动化点** |
| **迁移** | workbench-v2 与旧 views-v1、脏 layout 并存 | **Step 0 迁移规则** |
| **性能/边界** | sash 无 min-size；大 zip 列表；多 comparer Tab 共享 pair | **§1.8 非功能 + 实施注记** |
| **依赖** | put_work_file 已有；缺前端 save API 封装、Monaco props | **§7 补全触点** |
| **范围膨胀** | EX2 布局 JSON 与 EX1 混在 Step5 | EX 明确 P2 可 defer；不阻塞 P0 DoD |

---

## 1. 复审缺口总表（本计划范围）

### 1.1 工作台（栏 / Tab / 输出）

| ID | 缺口 | 现状证据 | 目标 | 严重度 |
|----|------|----------|------|--------|
| **WB1** | 列宽/行高不可拖 | `WorkbenchGrid` 缝仅 drop | 列/行缝 **mousedown sash**；`size` persist；**min 120px / min 80px** | P0 |
| **WB2** | 整栏拖动手势过宽 | tab bar 整行 `draggable` | **仅 gutter** 拖 column；Tab 只拖 tab | P0 |
| **WB3** | Tab 插入位置粗糙 | body 中心 → append | tab 条半宽 index；body 中心 = append 当前栏；边 = split | P1 |
| **WB4** | drop 高亮与 intent 可能不一致 | preview / drop 两套路径 | 同一 `resolveIntent(e)`；leave/drop 清 preview | P1 |
| **WB5** | 「三等分」文案 | flex `size=1` | 验收文案改为「插入后等分权重」 | P2 |
| **WB6** | `showBottom` 幽灵设置 | SettingsPanel | 删除或改为「打开输出 Tab」 | P1 |
| **WB7** | layout vs workbench 双轨 | 两 store | 文档 + 代码注释：侧栏=layout，中心=workbench | P1 |
| **WB8** | 顶栏/设置仍假设独立 PDF pane | `showPdf`、`togglePdf`、`mainOrder` 含 pdf | **废弃主区独立 PDF 栏控制**（保留设置「无操作」或隐藏）；PDF 只通过 workbench Tab | P0 |
| **WB9** | 多 comparer Tab 共用 `project.pair/units` | 单例 store | chrome 以 **focused comparer tab 的 path** 驱动；非焦点 Tab 不抢 units | P1 |
| **WB10** | 列/行 size 无下限与 double-click reset | — | min weight；可选双击缝重置等分 | P2 |

### 1.2 导入

| ID | 缺口 | 现状证据 | 目标 | 严重度 |
|----|------|----------|------|--------|
| **IM1** | 项目全量 zip 危险提示不足 | 确认后 `import_work_zip` | 预览 **红色警告：将重建 work 树**；需确认文案 | P0 |
| **IM2** | 比较区语义文案弱 | 本地 paths | 固定说明：新建 zone、不改 work；路径预览 | P1 |
| **IM3** | 补充冲突策略 | 默认覆盖 | 有冲突 → 策略 UI（overwrite/skip/rename）再确认 | P1 |
| **IM4** | 双 ZIP / Git 入口丢失 | store 有、UI 无 | 模态 **高级** 折叠恢复 | P0 |
| **IM5** | 名称字段 | zone 用；project 未用 | project：`meta.display_name` 或 status 展示（API 若无则先 status） | P1 |
| **IM6** | 双入口补充文件 | 顶栏 addFiles | 并入导入「补充 work」；顶栏删除 | P1 |
| **IM7** | 高级 Git 仅本地路径友好 | 旧 placeholder | 文案：本地路径优先；远程无鉴权则失败可见 | P1 |
| **IM8** | 超大 zip 列表卡顿 | `listZipEntryPaths` 全量 | 预览最多 **N=200** 条 +「共 M 个」；不阻塞确认 | P1 |

### 1.3 顶栏 / 比较器 chrome

| ID | 缺口 | 现状证据 | 目标 | 严重度 |
|----|------|----------|------|--------|
| **TB1** | 接受整文件在顶栏 | `onAcceptAll` | 仅 comparer chrome；无 pair 禁用 | P0 |
| **TB2** | ⇄ 不在 Tab | `sidesSwapped` | chrome 按钮；标题 left↔right | P0 |
| **TB3** | unit chips 未挂 Tab | ToolBody 裸 Monaco | chips + accept 在 Tab 内 | P0 |
| **TB4** | 顶栏仍挤 | compile×2… | 本计划不强制拆 compile；可选命令面板 P2 | P2 |
| **TB5** | chrome 与 focused tab 不同步 | — | 仅 **activeTab 且 kind=comparer** 显示；关 tab 清 units | P1 |

### 1.4 编辑 / 自动保存（含产品决策）

| ID | 缺口 | 目标 | 严重度 |
|----|------|------|--------|
| **AS1** | 无自动保存 | 设置默认 **开**；脏路径 **3s idle** → `PUT /work/file`；失败 toast + 保持 dirty | P0 |
| **AS2** | Monaco 只读写死 | 见下方 **决策** | P0 |
| **AS3** | 关 Tab 无脏提示 | 脏则 flush 或 confirm | P1 |
| **AS4** | Accept 与手改竞态 | 手改后 Accept 整文件 → confirm 覆盖；Accept 单元 → 以服务端返回刷新 model | P0 |
| **AS5** | 自动保存与 undo 栈 | put_work_file 已写 snapshot；保存成功后 status「已保存」；undo 仍可用 | P1 |

#### 决策 AS2 / 对调 / Accept（强制执行口径）

```
editor Tab:
  - 单栏等价内容：左侧 model = work 文件可写；右侧隐藏或同步只读克隆（实现选：renderSideBySide false 或两侧同文仅左可写）
  - 仅 text 类路径；pdf/docx 走各自 preview Tab

comparer Tab:
  - 默认：左 = work（可写），右 = active zone / revised（只读）
  - sidesSwapped=true：视觉左右对调；**可写侧始终是 work 内容**（对调只换显示与 Accept 方向映射，已有 store 逻辑需单测锁定）
  - Accept 单元/整文件：写 work；成功后刷新可写 model，dirty 清

输出/PDF/Word Tab:
  - 不可写；拖入错误类型 toast（已有）
```

**禁止**同时允许「右侧 zone 被手改」—— zone 是快照，只能通过重新导入/快照更新。

### 1.5 设置 / 主题

| ID | 缺口 | 目标 | 严重度 |
|----|------|------|--------|
| **ST1** | showBottom 幽灵 | 改「打开输出」 | P1 |
| **ST2** | 残留硬编码色 | rg 清理 | P1 |
| **ST3** | 无 autoSave 开关 | 设置面板 | P0 |
| **ST4** | Monaco `vs-dark` 固定 | 随 `resolvedTheme` 切 `vs` / `vs-dark` | P1 |
| **ST5** | showPdf 与 workbench | 隐藏或映射为 openTool('pdf') | P0（随 WB8） |

### 1.6 导出（P2，不挡 P0 DoD）

| ID | 目标 | 严重度 |
|----|------|--------|
| **EX1** | 命令面板/Git：「导出接受日志」 | P2 |
| **EX2** | 导出/导入 workbench+layout JSON | P2 |

### 1.7 测试 / 文档

| ID | 目标 | 严重度 |
|----|------|--------|
| **QA1** | sash/gutter/applyDrop 单测；min-size | P1 |
| **QA2** | import 模式矩阵单测（mock） | P1 |
| **QA3** | autosave debounce 假时钟；Accept vs dirty | P1 |
| **QA4** | sidesSwapped + accept 映射锁定 | P1 |
| **QA5** | manual-smoke UX 段 | P1 |
| **QA6** | 本计划勾选与 AGENTS L1/L2 表述 | P1 |

### 1.8 非功能（执行时遵守）

| ID | 规则 |
|----|------|
| **NF1** | sash 拖动用 `pointermove` + `requestAnimationFrame`，mouseup 再 persist（避免每 px 写 localStorage） |
| **NF2** | zip 预览路径上限 200；确认仍上传完整包 |
| **NF3** | 多 Tab 同 path：保存后广播刷新所有绑定该 path 的 Tab model |
| **NF4** | HTML5 DnD 与 sash：缝上 mousedown 优先 resize，不启动 tab drag |
| **NF5** | 自动保存失败：不静默；不关脏标 |

---

## 2. 范围外（明确不做）

- 远程 Git 鉴权 / push 产品化（L3）
- 多租户 / 虚拟化超大树
- 真 LLM 计费
- 插件式解析器全量
- Word 桌面级 1:1 排版
- 完整 VS Code grid 嵌套（仅 行→列 两层，本阶段不引入任意 depth split tree）

### 2.1 能力矩阵（防回归）

| 能力 | 改造后必须保留 |
|------|----------------|
| 项目 zip / 文件夹 / 多文件导入 | ✅ 模态 |
| 比较区 zip / 文件夹 / 多文件 | ✅ 模态 |
| work 补充 + 冲突策略 | ✅ 模态子模式 |
| 双 ZIP 兼容导入 | ✅ 高级 |
| Git 双 ref 导入 | ✅ 高级（本地路径） |
| zone from work 快照 | ✅ 比较区侧栏保留 |
| 编译 latexmk / latexdiff | ✅ 顶栏或 compile 活动 |
| 本地 git commit/restore/log | ✅ Git 活动 |
| Accept 单元 / 整文件 | ✅ 仅 comparer chrome |
| Undo | ✅ 顶栏或命令 |
| 导出 work zip | ✅ |
| 输出日志查看 | ✅ output Tab |
| 设置语言/主题 | ✅ |
| 类型不匹配 toast | ✅ |

改造中若删入口，必须改矩阵并写 §6 延期。

---

## 3. 实施步骤（**修订后顺序**）

每步：**演示 + 对应测试 + `vue-tsc -b` + 更新本文件勾选**。  
**依赖：** Step A 完成前禁止宣称「可写比较器已交付」。

### Step 0 — 基线 · 迁移 · 范围确认（≤1h）

- [ ] 跑通：`apps/web` test + vue-tsc；`apps/api` pytest ignore smoke
- [ ] 列出 storage keys；文档写明：
  - 忽略/删除废弃 `paper-diff-workspace-views-v1`（若存在）
  - `workbench-v2` 损坏 → `defaultState()`
- [ ] 确认 API：`PUT /projects/{id}/work/file`、import/*、git versions 可用
- [ ] Status → `In progress · Step 0`

**G/W/T：** When 测试全绿 → Then 可进入 A。

---

### Step A — 可写底座 + 自动保存（AS1–AS5, ST3–ST4）〔P0〕

> 原 Step4 前移：chrome 与多 Tab 都依赖保存管线。

1. [ ] `shared/api.ts`：`putWorkFile(projectId, path, content)` 封装（若无）
2. [ ] `project` store：`dirtyPaths`、`markDirty`、`savePath`、`flushAll`；接 put + undo 友好
3. [ ] `settings.autoSave` 默认 true；Settings 开关
4. [ ] `MonacoDiff.vue` 扩展 props：`editableLeft?: boolean`、`theme?: string`；`originalEditable`/`readOnly` 按 props；`onDidChangeModelContent` → emit `leftChange`
5. [ ] `ToolBody`：editor / comparer 接 editable + change → markDirty；3s debounce save
6. [ ] 主题：watch `resolvedTheme` 设 Monaco theme
7. [ ] 测试：debounce（vi.useFakeTimers）、save 失败保持 dirty、主题切换不抛错

**验收 G/W/T：**

- Given 打开 editor Tab 的 `main.tex`，When 键入并等待 3s，Then 磁盘/再开内容一致  
- Given autoSave 关，When 键入等待，Then 未 PUT  
- Given 脏文件，When 关 Tab，Then 提示或自动 flush  

**回滚点：** props 默认保持只读则旧行为恢复。

---

### Step B — 比较器 chrome + 顶栏减负（TB1–TB3, TB5, WB9）〔P0〕

1. [ ] 新 `ComparerChrome.vue`：⇄、接受整文件、unit chips、标题  
2. [ ] 仅 `focused && active comparer tab` 渲染；path 与 `openFile` 同步  
3. [ ] App 顶栏移除接受整文件  
4. [ ] Accept 后清 dirty、刷新 model（`setLeftContent` 或 reload）  
5. [ ] 测试：sidesSwapped 时 accept 左右映射（QA4）

**G/W/T：** 顶栏无「接受整文件」；comparer Tab 内可对调/接受；editor Tab 无 Accept 条。

---

### Step C — 工作台 sash / 拖放 / 设置清理（WB1–WB4, WB6, WB8, ST1, ST5）〔P0–P1〕

1. [ ] 列/行 sash（NF1, NF4）；min size  
2. [ ] gutter-only column drag（WB2）  
3. [ ] 统一 `resolveIntent`（WB4）  
4. [ ] Settings：showBottom → 打开输出；showPdf → `openTool('pdf')` 或隐藏  
5. [ ] 顶栏 `togglePdf` 改为打开/聚焦 PDF Tab（若仍暴露）  
6. [ ] 测试：persist sizes；intent 启发式保持 + 新增 min

**G/W/T：** 拖缝变宽 persist 刷新后仍在；拖 Tab 标题不拖走整栏；设置无幽灵底栏。

---

### Step D — 导入模态闭环（IM1–IM8）〔P0–P1〕

1. [ ] 模式：项目 | 比较区 | 补充 work（有 project 时）  
2. [ ] 高级：双 ZIP、Git  
3. [ ] 预览警告 / 路径 cap / 冲突策略  
4. [ ] 接线 doImport\* / doUpload / doGitImport / supplement  
5. [ ] 顶栏去掉 addFiles  
6. [ ] 测试：模式矩阵 mock；zip 列表 cap

**G/W/T：** 能力矩阵 §2.1 导入相关行全 ✅；误点全量 zip 有明确警告。

---

### Step E — 主题扫尾 · 文档 · 可选导出（ST2, EX*, QA5–QA6, WB5, WB7）〔P1–P2〕

1. [ ] rg 硬编码色清理  
2. [ ] EX1/EX2 若时间不够 → §6 延期  
3. [ ] `manual-smoke.md` 增补  
4. [ ] AGENTS completion 表述更新  
5. [ ] 本计划 P0 全勾；Status `P0 done` 或 `v1.1 complete`

---

## 4. 排期（修订）

| 步骤 | 预估 | 阻塞项 |
|------|------|--------|
| 0 | 0.5–1h | — |
| A 可写+autosave | 1–2d | put API 已有 |
| B chrome | 0.5–1d | **A** |
| C sash/设置 | 1–1.5d | 可与 B 后半并行 |
| D 导入 | 1–1.5d | 可与 C 并行 |
| E 扫尾 | 0.5d | A–D |

---

## 5. 完成定义（DoD）

### P0 DoD（必须）

- [ ] WB1, WB2, WB8  
- [ ] IM1, IM4  
- [ ] TB1, TB2, TB3  
- [ ] AS1, AS2, AS4, ST3  
- [ ] §2.1 能力矩阵无未声明删入口  
- [ ] web test + vue-tsc + api pytest（ignore smoke）绿  

### P1 DoD（默认本迭代完成，除非 §6）

- [ ] WB3, WB4, WB6, WB9  
- [ ] IM2, IM3, IM6, IM8  
- [ ] AS3, AS5, ST1, ST2, ST4  
- [ ] QA1–QA5  

### P2

- 可全部 §6 延期，不挡发版声明「UX gap P0 closed」

---

## 6. 延期登记

| ID | 延期原因 | 重开条件 |
|----|----------|----------|
| _(none yet)_ | | |

---

## 7. 文件触点

| 区域 | 路径 |
|------|------|
| Workbench | `stores/workbench.ts`、`components/workbench/*` |
| 导入 | `features/import/*`、`App.vue` onImport\*、`stores/project.ts` |
| Diff/保存 | `features/diff/MonacoDiff.vue`、`components/workbench/ToolBody.vue`、新 `ComparerChrome.vue` |
| API | `shared/api.ts` putWorkFile；后端已有 `put_work_file` |
| 设置/主题 | `stores/settings.ts`、`SettingsPanel.vue`、`styles.css` |
| 布局清理 | `stores/layout.ts`、`App.vue` toolbar |
| 测试 | `workbench.layout.test.ts`、新建 `autosave`/`importModal` 测 |

---

## 8. 与既有计划

```
import-diffchrome-autosave  ──►  Step A/B/D（本文件为准）
hardening R* 导出          ──►  Step E / EX* P2
workbench sash 字面        ──►  Step C
```

**声称：** 仅当 **P0 DoD** 全勾后，可写「UX gap P0 closed」；勿写「VS Code 完整」除非未来引入更深 grid。

---

## 9. 二次复审检查单（执行前再过一遍）

- [ ] 每条 P0 是否有 G/W/T？  
- [ ] 是否误把 zone 侧做成可写？  
- [ ] 删 UI 后能力矩阵是否仍 ✅？  
- [ ] sash 与 DnD 是否互斥处理？  
- [ ] Monaco 主题是否随 settings？  
- [ ] 多 comparer Tab 是否不抢 pair？  
- [ ] 全量 zip 是否双确认/强警告？  
- [ ] 自动保存失败是否可见？  

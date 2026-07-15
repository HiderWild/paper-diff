# paper-diff UX 实施计划：统一导入 · Diff 内接受整文件 · 全局自动保存

> **Status:** **Superseded for execution** by `2026-07-15-ux-gap-closure.md` (2026-07-15). Keep as historical requirements inventory.  
> Partial progress already in tree: unified Import button + `ImportModal` (zip/folder/files + default name); workbench columns/tabs; settings theme/locale. Remaining I\*/A\*/S\*/C\* → execute via **ux-gap-closure** Steps 1/3/4.  
> **Original status was:** Draft / ready-to-execute — 2026-07-15  
> **Scope:** 导入入口重组、对比器 chrome、自动保存（默认开）  
> **Related:**  
> - **Active plan:** `2026-07-15-ux-gap-closure.md`  
> - v2 模型：`2026-07-15-project-core-zones-git-llm.md`  
> - 补强：`2026-07-15-hardening-followups.md`  
> - 设计：`docs/superpowers/specs/2026-07-15-paper-diff-design.md`

---

## 0. 需求摘要

| ID | 需求 | 优先级 |
|----|------|--------|
| I1 | **任意时刻全局只有一个「导入」按钮**；点击弹出模态窗 | P0 |
| I2 | **未打开项目**：模态内仅「导入项目」（单 zip 为主） | P0 |
| I3 | **已打开项目**：模态内「导入比较区」—— zip / 目录 / 散文件 | P0 |
| A1 | **「接受整文件」移出全局顶栏**，放入对比器（Diff）顶部 chrome | P0 |
| R1 | 澄清并（可选）迁移「接受报告」入口 | P1 |
| S1 | **全局自动保存**开关，**默认开启** | P0 |
| S2 | 计时策略：无脏改不计时；有改动 3s 空闲后一次性落盘；新改动重置计时 | P0 |
| C1 | 比较器标题默认只写 **「比较器」**；有内容时再写「谁 vs 谁」 | P0 |
| C2 | 默认左=项目、右=比较区；**允许用户颠倒左右** | P0 |
| C3 | 「导入项目后显示目录树」等文案 **仅出现在目录树空态**，不出现在比较器/其他栏 | P0 |
| P1 | 目录树点击 **.pdf** → PDF 预览打开该文件（非强制「最新编译产物」） | P0 |
| P2 | PDF 预览 **不加锁**；同一路径文件被更新时预览自动刷新 | P0 |

---

## 1. 背景：现状与问题

### 1.1 导入（当前）

全局工具栏同时暴露：

- 项目 zip 文件选择 +「导入项目」
- 「高级：双 ZIP」展开后的 base/revised + Git 双 ref
- 比较区导入分散在「比较区」活动栏（zip / 文件夹 / 快照）

**问题：** 入口过多，冷启动与「已有项目加对照」心智混杂。

### 1.2 接受整文件（当前）

- 工具栏按钮调用 `onAcceptAll` → 整文件用右侧内容替换 work（`accept-all` / 或整文件语义）。
- 树上还有 per-file `add / delete / replace_all`（对比层面操作）。

**问题：** 顶栏塞「对比会话」动作，项目级动作（编译/导出）与会话级动作搅在一起。

### 1.3 接受报告是什么？（说明，不是新功能）

后端：`GET /api/v1/projects/{id}/export/accept-report.json`

```json
{
  "project_id": "...",
  "root_file": "...",
  "versions": {},
  "alignment": {},
  "revisions": { "path": rev },
  "accept_log": [ /* 每次 accept / accept-file / put_work_file 等审计条目 */ ],
  "dirty": true/false,
  "active_zone_id": "..."
}
```

**含义：** 本项目**接受/写入审计日志**的 JSON 导出（谁改了哪些文件、revision 轨迹、ops 快照引用），用于：

- 复盘「相对 zone 采纳了哪些改动」
- 协作/送审时附带变更说明（非 PDF）
- 调试 merge 冲突 / revision

**不是：** 编译报告、也不是 git patch。

**产品建议：** 文案改为「接受日志」/「Accept log」；入口从顶栏挪到 **Git / 导出菜单 / 命令面板**（本计划 R1）。

### 1.4 编辑与保存（当前）

- `MonacoDiff`：`readOnly: true`，`originalEditable: false` — **两侧只读**。
- 左侧更新靠 Accept API 返回后 `setLeftContent`。
- `PUT /work/file` 与 `put_work_file` 已有（含 undo 快照），但**编辑器不走这条路径**。

→ 自动保存要先定义「可编辑 work 左侧」+ 脏缓冲，否则无对象可存。

---

## 2. JetBrains 自动保存参考（与我们模型对照）

| JetBrains (PyCharm/IDEA) | 说明 | 我们是否照抄 |
|--------------------------|------|----------------|
| 几乎**无法彻底关闭**自动保存 | 构建/运行/VCS/关页必存 | 否：我们提供显式开关 |
| `Save files if the IDE is idle for N seconds` | **全局空闲**计时存盘 | **部分**：用户要的是**「有脏改才计时」**的 debounce，不是纯 idle |
| Frame deactivation 存盘 | 切到其他应用时存 | 可选增强 S3 |
| Tab 蓝点 = 未保存 | 脏文件标记 | **应做**（S2 体验） |
| Local History | 更细粒度历史 | 我们已有 accept/put 快照栈；不复刻 Local History |
| Safe write（备份再写） | 防写坏 | 后端已有快照；可后置 |

**结论：** 更接近 **VS Code 式文档 debounce 保存** + **JetBrains 脏标记**；默认 3s 符合「键入停顿后落盘」。不与 JB 完全一致处：我们**允许关闭**自动保存（关时需手动保存或仅 Accept 落盘）。

---

## 3. 目标体验

### 3.1 导入

```
[导入 ▾]  ──点击──▶  模态窗
                         ├─ 无 projectId / status=empty
                         │     └─ 「导入项目」 zip（主）
                         │         [高级] Git 绑定 / 双 zip 兼容（可折叠）
                         └─ 已有 project ready
                               └─ 「导入比较区」
                                     · ZIP
                                     · 文件夹 (webkitdirectory)
                                     · 多文件（相对路径：webkitRelativePath 或扁平）
                               可选次要：从当前 work 快照 / 从 Git commit（链接到现有能力）
```

顶栏**删除**并排 zip 选择器、高级双 zip 常驻展开；高级仅模态内折叠区。

比较区活动栏仍可保留「快捷再导入」，但与模态文案一致（可选本计划 I4：侧栏按钮也打开同一模态）。

### 3.2 比较器 chrome（示意）

**无打开文件时标题仅：**

```
┌ 比较器                                              ┐
│ （空：不要写「导入项目后显示目录树」）                 │
```

**有内容时标题：**

```
┌ 比较器 · 项目 ↔ 比较区「imported」  [⇄ 对调]  dirty● ─┐
│ [接受整文件]  chips…                                   │
│ ┌──── 左（默认可编辑 work） ──┬── 右（zone 只读） ──┐ │
```

两提交预览：`比较器 · 提交 a1b2c3d ↔ e4f5g6h`。

**对调：** 显示对调；Accept 时 range 映射回「work←zone」语义（见 §5.1）。

### 3.2b PDF 预览

| 动作 | 行为 |
|------|------|
| 树点击 `*.pdf` | 预览 **该路径** 的 work 文件（raw）；显示文件名 |
| 编译成功 | 若当前预览源是 **编译产物** 或用户在看 artifacts/同源路径 → 用新 URL（cache-bust）刷新 |
| 预览中文件被 PUT/重新导入 | 对同一 path 加 `?t=` 刷新 PdfPane |
| 锁 | **无锁**；允许多次打开切换 |

空态文案：`pdf.empty` = 「尚无 PDF」类短句，**禁止**复用 `tree.empty`。

### 3.3 自动保存

- 全局开关 `autoSave`（Pinia + localStorage），**默认 true**。
- 与现有 `autoCompile` **独立**（编译仍可关；保存默认开）。
- 脏文件集合 `dirtyPaths: Set<path>`；任意 work 缓冲变更：
  1. 标记 path dirty  
  2. 重置 3s 计时器  
  3. 计时到 → `flushAutosave()` 对**所有 dirty** 调 `PUT work/file`（并行有限、串行 revision 更安全）  
- 关闭自动保存：显示「未保存」点；提供 **手动保存**（Ctrl/Cmd+S）与切换文件时确认（S2.5）。

---

## 4. 非目标

- 多标签完整 VS Code 级（可预留单文件缓冲 map）
- 协同 CRDT / 冲突实时合并
- 完整复刻 JetBrains Local History UI
- 自动保存触发 git commit（永不静默 commit）
- 改掉 zone 导入的后端契约（只重组 UI）

---

## 5. 编辑语义（自动保存前置决策）

| 模式 | 左 work | 右 | Accept 芯片 | 自动保存 |
|------|---------|----|-------------|---------|
| work + active zone | **可编辑** | 只读 zone | 开（落盘后 recompute） | 左侧缓冲 → work |
| 仅 work（无 zone） | 可编辑（可单栏或右空） | 空/隐藏 | 关 | 同上 |
| 两提交 git preview | **只读** | 只读 | 关 | 关 |
| binary / image | 无 Monaco | — | 关 | 关 |
| 左右颠倒 | 显示 zone / work | 见 §5.1 | 映射 Accept | 仍写 work |

### 5.1 左右颠倒与 Accept

Monaco 显示：

- 默认：`left=work, right=zone`
- 颠倒：`left=zone, right=work`（仅显示）

Accept API 永远：`replacement = extract(zone, zone_range)` → `apply(work, work_range)`。

颠倒时 unit 来自 swapped 两侧，提交 Accept 前 **对调 left_range/right_range**（unit.left 对应显示左=zone → 作为 right_range 源；unit.right 作为 left_range 目标）。

### 5.2 PDF 打开语义

- `openFile('foo.pdf')` → `pdfHref = work/file-raw?path=foo.pdf&t=…`，`pdfSource='file'`, `pdfPath='foo.pdf'`
- `doCompile` 成功 → `pdfHref = artifacts/pdf?job_id=&t=`，`pdfSource='compile'`, `pdfPath=null`（或 root 对应产物名）
- 若 `pdfSource==='file' && pdfPath` 且 work 该路径变更（导入/保存）→ 更新 `t`
- PdfPane `watch(url)` 已重建渲染；确保 cache-bust 改变 url

**Accept 与脏缓冲：**

- Accept 前若当前文件 dirty → 先 flush 再 accept，或 Accept 以服务端 revision 为准失败则提示「请先保存」。
- 推荐：**Accept 前自动 flush 当前 path**（避免 409）。

**Undo：**

- `put_work_file` 已写 snapshot → 自动保存产生的修改可用现有 Undo（若 accept_log 含 put）。
- UI 标明 Undo 覆盖「接受 + 自动保存写入」。

---

## 6. 分阶段实施

### 阶段 U0 — 方案冻结与文案（0.5 天）

| 步骤 | 任务 | 验收 |
|------|------|------|
| U0.1 | 本文件评审；「接受报告」→「接受日志」i18n 键规划 | 产品确认 |
| U0.2 | 列出受影响文件（见 §8） | 清单 |
| U0.3 | 自动保存参数默认：`delayMs=3000`，可配置常量 | 文档写死 |

**交付：** 无代码或仅 i18n 键草稿。

---

### 阶段 U1 — 统一导入按钮 + 模态（1–2 天）**【优先】**

#### U1.1 组件

新建 `apps/web/src/features/import/ImportModal.vue`（或 `components/ImportModal.vue`）：

**Props / 行为：**

- `open: boolean`
- `hasProject: boolean`（`projectId && status!=='empty'` 或 files 已加载）
- emits: `close`, 内部调 store

**面板 A — 无项目：**

- 文件选择 zip → `doImportWork`
- 进度条：已有 `uploadProgress`
- 折叠「高级」：双 zip `doUpload`、Git `doGitImport`（从现顶栏挪入）

**面板 B — 有项目：**

- Tab 或三段：`ZIP` | `文件夹` | `多文件`
- ZIP → `doAddZoneZip`
- 文件夹 → `doAddZoneFiles` + webkitdirectory
- 多文件 → 同 import files API（已有 zone files / work files；比较区用 zone）
- 次要链接：`doZoneFromWork`、提示到 Git 面板 zone-from-commit

#### U1.2 App 顶栏

- 只保留：`[导入]` 按钮（打开模态）
- 删除：裸 `<input type=file>` 标签、「导入项目」第二按钮、高级双 zip 展开区（内容进模态）

#### U1.3 Store

- `projectStatus` 暴露 empty/ready（若尚未从 meta 刷新）
- 可选：`ensureProject` 仅在「导入项目」路径创建；加 zone 时已有 project

#### U1.4 i18n

- `import.modalTitle` / `import.project` / `import.zoneZip` / `import.zoneFolder` / `import.zoneFiles` / `import.advanced` …

**验收：**

- [ ] 无项目：模态无「比较区」主入口  
- [ ] 有项目：主入口是比较区三种方式；仍可折叠看到双 zip（可选）  
- [ ] 顶栏导入相关控件仅 1 按钮  

---

### 阶段 U2 — Diff 内 chrome：接受整文件（0.5–1 天）

| 步骤 | 任务 |
|------|------|
| U2.1 | 顶栏移除「接受整文件」 |
| U2.2 | Diff 区域 `panel-header` 旁或 unit-bar 左侧增加：`接受整文件` → 现 `onAcceptAll` |
| U2.3 | 禁用条件：`!pair \|\| busy \|\| gitPreviewPair \|\| !activeZoneId`（无右侧无意义） |
| U2.4 | 树上的 replace_all 保留（路径级） |

**验收：** 无全局接受整文件；仅在有对照打开文件时在 Diff 顶可见。

---

### 阶段 U3 — 接受日志入口整理（0.5 天）

| 步骤 | 任务 |
|------|------|
| U3.1 | i18n：`acceptReport` → `接受日志` / `Accept log`；tooltip 说明审计用途 |
| U3.2 | 从顶栏移除；放入：命令面板 + Git 侧栏底部或导出下拉 |
| U3.3 | README/AGENTS 一句说明 |

**验收：** 用户不误解为编译报告；功能仍可达。

---

### 阶段 U4 — 左侧可编辑 + 全局自动保存（2–3 天）**【核心】**

#### U4.1 Monaco 可编辑

`MonacoDiff.vue`：

```ts
// 目标
originalEditable: props.leftEditable ?? true
readOnly: false  // 整体不全只读；右侧 modified 用
// DiffEditor: original = work, modified = right(zone)
// 右侧：通过 updateOptions / getModifiedEditor().updateOptions({ readOnly: true })
```

Props 扩展：

- `leftEditable: boolean`
- `rightEditable: boolean`（默认 false）
- emit：`leftChange: [text: string]`

订阅 `original` model `onDidChangeContent`（注意 `setLeftContent`/props 同步时 `ignoreChange` 标志防循环）。

#### U4.2 Store 脏缓冲与计时

```ts
autoSave: ref(true)           // default true, localStorage paper-diff-autosave
autoSaveDelayMs: 3000
dirtyMap: Map<path, string> // path -> latest buffer
autoSaveTimer: ReturnType<typeof setTimeout> | null
dirtyCount / isDirty(path)

function onWorkBufferChange(path, text) {
  dirtyMap.set(path, text)
  if (!autoSave) return
  resetTimer() // 3s
}

async function flushAutosave() {
  // for each dirty: PUT work/file, update pair.revision, clear dirty
  // concurrency: 1 or 2 sequential per path lock
}

function saveNow(path?) // 手动
```

- 切换文件：若 `!autoSave && dirty` → confirm 保存/丢弃/取消  
- 若 `autoSave` → 切换前 `flush` 当前 path（或全部）  
- 关闭页面：`beforeunload` 若 dirty 提示  

#### U4.3 UI

- 全局开关：设置区或顶栏「自动保存」checkbox（默认勾）
- Diff 标题旁：脏点 `●` / 「保存中…」  
- Cmd/Ctrl+S → `saveNow`  
- 与 `autoCompile` 分离：保存成功可**可选**触发 debounce 编译（现逻辑在 accept 后；保存后是否编译 → **默认否**，避免键入触发重编译）

#### U4.4 与 Accept 协调

- Accept chip：flush current → 再 POST accept  
- Accept 整文件：同上  
- Undo：flush 取消计时再 undo  

**验收：**

- [ ] 默认自动保存开；改左侧 3s 无操作后服务器 work 更新（刷新/再 open 一致）  
- [ ] 连续输入只产生一次（或尾部一次）PUT  
- [ ] 关闭自动保存后修改不 PUT，S 可手存  
- [ ] git preview 左右不可编辑、不计时  

---

### 阶段 U5 — 测试与文档（1 天）

| 步骤 | 任务 |
|------|------|
| U5.1 | 前端：ImportModal 条件渲染单测（shallow）；dirty timer 用 fake timers |
| U5.2 | API：put 已有；可加 flush 无关回归 |
| U5.3 | `manual-smoke.md` 增补：导入模态、Diff 接受整文件、自动保存 |
| U5.4 | AGENTS 指针本计划 |

---

## 7. 实施顺序

```
U0 冻结
 └─▶ U1 导入模态（纯 UI，风险低，立刻更清晰）
      └─▶ U2 Diff 接受整文件
           └─▶ U3 接受日志搬迁
                └─▶ U4 可编辑 + 自动保存（最大）
                     └─▶ U5 测试文档
```

**建议首迭代：U1 + U2**（半天–2 天可见）；U4 单独 PR。

---

## 8. 受影响文件（预估）

| 区域 | 文件 |
|------|------|
| 新建 | `apps/web/src/features/import/ImportModal.vue` |
| 改 | `apps/web/src/App.vue`（顶栏瘦身、模态、Diff chrome、autoSave 开关） |
| 改 | `apps/web/src/features/diff/MonacoDiff.vue`（可编辑 + change 事件） |
| 改 | `apps/web/src/stores/project.ts`（dirty/autoSave/flush/saveNow） |
| 改 | `apps/web/src/shared/api.ts`（若需 save 封装） |
| 改 | `apps/web/src/i18n/locales/zh-CN.ts`, `en.ts` |
| 可选 | `FileTree` 不改；zones 侧栏按钮可 `emit openImport` |
| 文档 | `manual-smoke.md`, `AGENTS.md`, 本计划勾选 |
| 后端 | **无需新 API**（work import / zone import / put_work_file 已有） |

---

## 9. API 复用（无需新后端）

| UI 动作 | API |
|---------|-----|
| 导入项目 zip | `POST .../work/import/zip` |
| 区 zip | `POST .../zones` + `.../import/zip` + activate |
| 区目录/散文件 | `.../zones/{id}/import/files` |
| 双 zip 兼容 | `.../versions/upload` |
| Git 双 ref | `.../versions/git` |
| 整文件接受 | `POST .../accept-all` 或 `accept-file replace_all` |
| 自动保存 | `PUT .../work/file?path=` |
| 接受日志 | `GET .../export/accept-report.json` |

---

## 10. 风险与决策

| 风险 | 缓解 |
|------|------|
| Monaco Diff 左编右读配置踩坑 | 先 spike 半日；失败则 U4 改为「单栏编辑器 + 可选右栏」 |
| setValue 触发 onDidChange 循环 | `applyingRemote` 标志 |
| 3s flush 与 Accept 竞态 | Accept 前 await flush；path 级锁 |
| 大文件频繁 PUT | 仅 dirty 且 debounce；可上限 MB 警告 |
| 用户关自动保存丢数据 | beforeunload + 脏点 + Ctrl+S |
| 自动保存误触发编译 | **不**绑 autoCompile |

**默认决策：**

1. 右栏永远只读（zone/历史）。  
2. 自动保存默认 **开**，delay **3000ms**。  
3. 双 zip/Git 双 ref 保留在导入模态 **高级** 折叠，不删 API。  
4. 接受日志改名，进命令面板 / Git 区，不进主对比路径。

---

## 11. 验收清单（本需求完成定义）

- [ ] 顶栏仅一个导入按钮；模态按是否已开项目切换内容  
- [ ] 已开项目可 zip/目录/散文件加比较区  
- [ ] 接受整文件仅在 Diff 顶栏（或 unit-bar）  
- [ ] 接受日志不叫「报告」且不霸占顶栏主路径  
- [ ] 默认可编辑 work 左栏 + 3s 防抖自动保存  
- [ ] 脏标记与手动保存可用  
- [ ] git preview 下不可编辑、不自动保存  
- [ ] 测试：timer + import 模态关键路径；`vue-tsc` / pytest 绿  

---

## 12. 可直接开 Issue

1. `feat(web): ImportModal single entry by project state`（U1）  
2. `feat(web): move accept-all into diff chrome`（U2）  
3. `chore(i18n): accept log rename + relocate`（U3）  
4. `feat(web): editable work pane + debounced autosave`（U4）  
5. `test(web): autosave timer and import modal`（U5）  

---

## 13. 总结

| 主题 | 方案要点 |
|------|----------|
| 导入 | 单按钮 + 模态；无项目=导入 work；有项目=导入 zone |
| 接受整文件 | Diff 会话 chrome，非全局 |
| 接受报告 | 实为 **accept_log 审计 JSON**；改名迁移入口 |
| 自动保存 | 默认开、脏改 3s debounce、参考 JB 脏点与空闲思想但**可关闭** |

**下一步执行建议：** 先 **U1+U2**（体验立刻清晰，不动编辑模型），再 **U4**（自动保存）。

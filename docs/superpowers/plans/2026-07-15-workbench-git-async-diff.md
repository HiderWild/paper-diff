# paper-diff 下一代工作台计划：可伸缩布局 · 异步 Diff · Git 封装

> **Status:** Implemented (M1–M5 core) — 2026-07-15  
> **Date:** 2026-07-15  
> **Depends on:** P0–P5 MVP（`2026-07-15-paper-diff-implementation.md`）

---

## 1. 背景与问题

当前 MVP 工作台是固定三栏（文件列表 / Diff / PDF），文件列表「摊平」展示，导入后即全量对齐 + 打开文件时前端算 diff。真实论文工程通常：

- 树深、文件多、含大量图床/资源；
- 用户先要「打开项目看结构、读文件」，再按需对比；
- 希望布局像 VS Code 一样可调、可藏；
- 版本比较最终要贴近 **Git 工作流**（提交之间对比、合并结果写回仓库）。

本计划在不推翻 MVP 的前提下，把「双版本 review」升级为 **可伸缩科研工作台 + 异步差异计算 + 面向论文场景的 Git 封装**。

---

## 2. 目标与非目标

### 2.1 目标

1. **目录树 UX**：树状展开/折叠；`.` 开头目录/文件默认可藏；文件栏整栏可隐藏。
2. **可伸缩布局**：文件树、编辑器（源/对比）、PDF 预览宽度可拖；PDF 可隐藏；当前三栏布局作为**默认推荐布局**持久化。
3. **渐进式打开项目**：导入只物化树与快照，**不在导入时全量 diff**；先显示树 + 单文件内容。
4. **按需 / 异步比较**：点开头目录默认不参与比较；用户开启后加入异步队列；结果可查询/轮询，前端刷新可用性与差异摘要（非强推送通知）。
5. **Git 为主的版本比较**：同一项目不同 commit/ref 之间的比较优先交给 Git；本产品负责**可视化**（尤其词/短语级）与 Accept 工作流。
6. **合并结果写回 Git**：封装 `commit` / `status` / 可选 branch，让 Git 服务论文场景，隐藏命令行细节。

### 2.2 非目标（本计划不一次做完）

- 完整复刻 VS Code 扩展系统、拖拽任意分屏到四边、浮动编辑器多实例（列为长期愿景 L 阶段）。
- CRDT 多用户实时协同。
- 把 Git 替换掉（我们是 **封装** Git，不是替代对象存储 diff）。
- 二进制图片像素级 diff（先只做存在性/哈希变化指示）。
- 完整 Git 托管 UI（PR、远程鉴权矩阵等）——先本地/已 clone 仓库，远程 push 后置。

---

## 3. 需求清单（按主题）

### A. 工作台布局（Workbench Shell）

| ID | 需求 | 验收标准 |
|----|------|----------|
| A1 | 文件栏可整栏隐藏/显示 | 快捷键 + 工具栏按钮；隐藏后编辑器吃掉宽度 |
| A2 | PDF 预览栏可隐藏/显示 | 同上 |
| A3 | 三区水平分隔可拖拽改宽 | 最小宽度约束；拖完写入 localStorage |
| A4 | 默认布局 = 当前推荐三栏 | 重置布局按钮恢复默认 |
| A5 | 布局预设（后续） | `files\|editor\|pdf` 可切换到 `editor\|pdf`、`files\|editor` 等 |
| A6 | 长期：VS Code 风格面板 | 见阶段 L（活动栏、底栏日志、命令面板） |

### B. 文件树

| ID | 需求 | 验收标准 |
|----|------|----------|
| B1 | 树状展开/折叠，非扁平列表 | 文件夹节点 chevron；记忆展开状态（会话内） |
| B2 | 以 `.` 开头的目录/文件默认可隐藏 | 开关默认 **关显示**（即默认隐藏）；打开后可见 |
| B3 | 树显示 diff 状态徽章 | `same/modified/added/removed/pending/comparing/skipped` |
| B4 | 点开头目录默认 **不比较** | meta/配置 `include_dot_paths: false`；开启后才入队 |
| B5 | 资源文件可见（图/pdf 等） | 树中显示；点击策略见 B6 |
| B6 | 文本打开编辑器；二进制仅预览/提示 | 不强制进 Monaco 双栏空内容 |

### C. 打开与 Diff 流水线

| ID | 需求 | 验收标准 |
|----|------|----------|
| C1 | 导入只建立 workspace + 文件索引 | `upload/git import` **不**阻塞在全量文本 diff |
| C2 | 打开项目立即可见目录树 | `GET tree` 或索引 API 毫秒～秒级返回（视文件数） |
| C3 | 打开文件显示内容（可非 diff 模式） | 先单栏/双栏「内容查看」；diff 就绪后切对比 |
| C4 | Diff 异步、按文件/目录入队 | 队列可取消；并发可配置 |
| C5 | 前端轮询/SSE **数据刷新** | 比较完成后 index 状态变，UI 徽章更新；**不** toast 轰炸 |
| C6 | 未比较的文件点开可触发「即时比较该文件」 | 优先级高于后台批量 |
| C7 | 词/短语/句级可视化仍以前端 sentence-mapper + Accept 为准 | 后端提供路径级摘要 + 可选服务端单元（后置） |

### D. Git 比较与写回

| ID | 需求 | 验收标准 |
|----|------|----------|
| D1 | 指定 `base_ref` / `revised_ref` 比较（已有 import 基础） | 继续用 `git archive`/`show` 物化，或 **不落地** 用 git diff 管道（择优） |
| D2 | 变更列表来自 Git | `git diff --name-status base...revised` 驱动树徽章 |
| D3 | 文件内容来自 Git 或工作区 | 打开文件时 `git show ref:path` 或已 materialize 路径 |
| D4 | 可视化词/短语级修改 | 继续 Monaco + sentence-mapper；Git 只提供双方文本 |
| D5 | Accept 后可 `git commit` | 封装：stage 变更路径 + commit message 模板（论文场景） |
| D6 | `status` / 可选 `checkout -b` 草稿分支 | UI 展示「未提交接受数」 |
| D7 | push 可选且显式 | 默认不自动 push；鉴权后置 |

### E. 编译（衔接既有 + 前序需求）

| ID | 需求 | 说明 |
|----|------|------|
| E1 | 资源随 zip/git 完整进入树 | 已支持字节级；继续保证 merged 树含图 |
| E2 | 主入口启发式候选 + 用户必选 | 编译前选 root；纯比较不必选（前序需求，可放本计划阶段 2） |
| E3 | 入口选择与布局无关 | 工具栏下拉 |

### F. 国际化 / 容量（延续）

| ID | 需求 |
|----|------|
| F1 | zh-CN 默认 UI 文案覆盖新控件 |
| F2 | 大 zip 上限 500MB（已做）；大仓库树分页/虚拟列表后置 |

---

## 4. 概念模型升级

```
Project
  ├── source: zip_pair | git_repo
  ├── refs: { base, revised }          # git 时有意义
  ├── workspace sides: base | revised | merged
  ├── tree_index                        # 结构 + 类型 + 比较状态
  ├── diff_jobs / compare_queue         # 异步比较任务
  └── layout_prefs (client)             # 本地布局

Compare policy
  ├── include_dot_paths: bool = false
  ├── compare_mode: on_demand | auto_modified_only | all
  └── priority: open_file > user_toggle_dir > batch

File node status
  unknown → queued → comparing → ready(same|modified|added|removed|binary)
                    ↘ skipped (dot / user)
```

**原则：**

- **结构优先、比较惰性**：树先上，diff 后到。
- **Git 是真相来源（路径级）**；**Monaco 是可视化真相来源（行内）**。
- **布局状态在前端**；**比较任务状态在后端**（可恢复、可多端）。

---

## 5. 架构方案摘要

### 5.1 前端

| 模块 | 职责 |
|------|------|
| `WorkbenchShell` | 可拖拽分栏、面板显隐、默认布局 |
| `FileTree` | 树构建、展开、点文件切换、dot 过滤开关 |
| `EditorHost` | 单文件 view / Diff 模式切换 |
| `PdfPane` | 已有；挂 hide 与 resize |
| `compareStore` | 轮询 diff-index 增量；队列状态 |
| `layoutStore` | 宽度、可见性 localStorage |
| `gitStore` | refs、commit 对话框（阶段 4） |

### 5.2 后端

| 模块 | 职责 |
|------|------|
| `tree_service` | 快速列树 + kind + 可选 git name-status |
| `compare_queue` | 按 path 异步算 sha / 粗 diff 摘要 |
| `root_detect` 扩展 | 候选列表 + 用户选定 root |
| `git_service` 扩展 | diff name-status、show、commit、status |
| 现有 `merge_engine` / `compile` | 保持；入口强制用户选择后编译 |

### 5.3 比较队列语义（前端「可用即刷新」）

```
POST /compare/enqueue   { paths?: [], include_dot?: bool, recursive?: bool }
GET  /diff-index        { cursor?, since? }  →  各 path status + revision
GET  /compare/jobs/{id} optional
# 可选 SSE：compare.path.ready  —— 前端只更新 store，不弹窗
```

实现首选：**短轮询 diff-index**（2s，busy 时 0.5s）；SSE 作为增强。

---

## 6. 分阶段执行计划

### 阶段 0 — 基线整理（0.5–1 天）

**范围**

- 文档定稿（本文件 + design 增补链接）
- 列出受影响文件清单与 API 破坏性评估
- 加 E2E 手工验收检查表

**交付**

- [ ] PR 说明「不破坏现有 accept/compile 主路径」
- [ ] 明确 `diff-index` 是否兼容字段扩展

**风险**

- 无

---

### 阶段 1 — 工作台布局与文件树 UX（前端为主，2–4 天）

**用户价值**：立刻改善「摊大饼」与定死布局。

#### 1.1 可拖拽三栏 + 显隐

- [ ] 引入轻量 split（自研 mousedown bar 即可，不必 heavy 库）
- [ ] `layoutStore`：`{ filesWidth, editorWeight, pdfWidth, showFiles, showPdf }`
- [ ] 默认值对齐当前样式（约 240px | 1fr | 1fr）
- [ ] 工具栏：`切换文件树` `切换 PDF` `重置布局`
- [ ] CSS：`.main` 从固定 `grid-template-columns` 改为动态

#### 1.2 树状文件树

- [ ] 从 flat `files[]` 构建 `TreeNode`
- [ ] 展开/折叠；双击文件夹或 chevron
- [ ] 过滤：隐藏 `^\.` 路径段（默认开）
- [ ] 文件栏 header 放小开关「显示点文件」
- [ ] i18n 文案

#### 1.3 验收

- [ ] 隐藏文件树后编辑器铺满；再显示恢复宽度
- [ ] 隐藏 PDF 后中间变宽
- [ ] 刷新页面布局恢复
- [ ] 树折叠/展开正常；隐藏 `.git` 等

**不做**：异步 compare（阶段 3）、Git commit（阶段 4）

---

### 阶段 2 — 编译入口选择 + 资产明确化（后端+前端，1–2 天）

> 承接先前口头需求：启发式 root + 用户必选；比较不需要 root。

#### 2.1 Root 候选

- [ ] `detect_root_candidates()`：magic / main.tex / documentclass 打分排序
- [ ] meta：`root_candidates[]`，`root_file` 仅在用户选择后写入（或暂存 recommend）
- [ ] `POST /projects/{id}/root` body `{ root_file }`
- [ ] 编译无 root → 400 `ROOT_REQUIRED` 明确文案

#### 2.2 前端

- [ ] 工具栏 root 下拉：推荐标 ⭐；必选后才能 Compile
- [ ] Diff/对比流程不依赖 root

#### 2.3 资产

- [ ] 确认 zip/git 导入保留图片等到 merged（回归测试）
- [ ] 树展示 binary 节点

#### 2.4 验收

- [ ] 多 `\documentclass` 时全部出现在候选
- [ ] 不选 root 点编译有提示
- [ ] `includegraphics` 图在 merged 树中存在

---

### 阶段 3 — 惰性 / 异步比较管道（核心，3–5 天）

**用户价值**：大项目可打开；dot 目录默认可跳过。

#### 3.1 后端

- [ ] 导入 `_finalize_versions`：**只**建树索引 + 拷贝 merged；路径状态 `unknown`/`pending`
- [ ] 可选快速路径：对 text 只算 sha 对齐粗状态（仍不打开 Monaco）
- [ ] `CompareService` 队列（进程内线程池即可，与 compile 类似 serial/limit）
- [ ] enqueue 规则：
  - 默认跳过 path 中任一段以 `.` 开头的节点
  - 用户 `include_dot_paths=true` 或对某目录「启用比较」则入队
- [ ] `diff-index` 字段：`status, kind, compare_state, error?`
- [ ] 单文件 `POST .../compare/file` 高优先级

#### 3.2 前端

- [ ] 打开项目 → 拉 tree → 点文件：
  - text：`file-pair` 显示内容；若 `compare_state!=ready` 可先 view-only 再触发 compare
  - ready 后挂 MonacoDiff
- [ ] 定时刷新 diff-index（增量 merge 到 pinia）
- [ ] 树徽章：pending / comparing / modified…

#### 3.3 验收

- [ ] 1000+ 文件项目：导入后 <N 秒出树（N 目标本地标）
- [ ] 默认不比较 `.git` / `.cache` 下路径
- [ ] 用户勾选某目录后出现 comparing → ready
- [ ] 对比就绪文件可 Accept 回归通过

**风险**：队列与 accept 竞态 → path 级锁 / revision 已有机制复用。

---

### 阶段 4 — Git 驱动比较 + 写回（3–6 天）

**用户价值**：论文版本管理回到 Git；我们做「好用的壳」。

#### 4.1 比较模式

| 模式 | 行为 |
|------|------|
| Zip pair | 现有物化 + 异步 compare |
| Git refs | `git diff --name-status A B` 得变更集；内容 `git show` 或 archive 子集 |
| Git working tree vs ref | 后置：`git diff ref` |

- [ ] `GitService.diff_name_status(base, revised, subdir?)`
- [ ] 树默认只高亮 **Git 认为有变化的路径**；未变更可折叠「未修改」
- [ ] 打开文件：左右内容来自两 ref；merged 仍从工作副本初始化（base）

#### 4.2 写回

- [ ] `GET .../git/status`
- [ ] `POST .../git/commit` `{ message, paths? }`  
  - 将 merged 相对 base 的变更同步回 **repo worktree** 策略二选一（实现时决断）：
  - **A.** 项目即绑定已有 clone 的 worktree（推荐）  
  - **B.** 导出 patch 再 `git apply`（更绕）
- [ ] 推荐策略 **A**：import 时记录 `repo_path`；accept 直接写文件到 worktree 可选同步路径
- [ ] Commit message 模板：`paper-diff: accept N ops` / 用户编辑

#### 4.3 可视化

- [ ] 保持 word/sentence Accept chips
- [ ] 路径列表 = Git 变更 ∪ 用户强制打开的文件

#### 4.4 验收

- [ ] 同一仓库两 tag/commit 导入后树与 `git diff --name-status` 一致
- [ ] Accept 后 commit，`git log -1` 可见
- [ ] 无 Git 时 zip 模式不受影响

**风险**：远程 URL clone、大 LFS → 文档标明限制；LFS 后置。

---

### 阶段 5 — 工作台高级布局（向 VS Code 靠拢，4–8 天，可切分）

**用户价值**：面板灵活切换。

- [ ] 活动栏（左侧窄条）：资源管理器 / 搜索（可选）/ Git / 编译
- [ ] 底栏：Compile log 从 PDF 下拆出为可调整高度面板
- [ ] 布局预设切换 + 导出/导入 JSON 布局
- [ ] 命令面板雏形（Ctrl/Cmd+Shift+P）：Compile、Toggle PDF、Commit…
- [ ] 多标签打开多个文件（后置增强）

**验收**：能做到「关文件树 + 关 PDF + 底栏日志」等价常见 VS Code 单栏编辑；一键恢复默认推荐布局。

---

### 阶段 L — 长期愿景（不排期）

- 任意方向拆分编辑器（grid mosaic）
- 扩展 API / 插件
- 远程 Git 鉴权与 Push UI
- 二进制/图片视觉 diff
- 服务端 sentence-level unit 缓存

---

## 7. 建议实施顺序与依赖

```
阶段0 基线
  └─▶ 阶段1 布局+树        ─┐
  └─▶ 阶段2 root+资产      ─┼─▶ 阶段3 异步比较 ─▶ 阶段4 Git  ─▶ 阶段5 高级工作台
                             │
                             └─ 阶段1 与 2 可并行
```

**推荐首发迭代：阶段 1（纯前端、立即可感）→ 阶段 2（编译安全）→ 阶段 3（大项目可开）→ 阶段 4（Git 闭环）。**

---

## 8. API 变更草案（随阶段落地）

### 阶段 2

```
GET  /projects/{id}                 + root_candidates: string[]
POST /projects/{id}/root            { "root_file": "chapters/main.tex" }
POST /projects/{id}/compile         无 root → 400 ROOT_REQUIRED
```

### 阶段 3

```
GET  /projects/{id}/tree            { nodes: [{ path, type: file|dir, kind, compare_state, ...}] }
POST /projects/{id}/compare/enqueue { paths?: string[], include_dot_paths?: bool }
GET  /projects/{id}/diff-index      + compare_state, summary?
POST /projects/{id}/compare/file    { path }  // high priority
```

### 阶段 4

```
GET  /projects/{id}/git/status
POST /projects/{id}/git/commit      { message, paths?: string[] }
# 已有 POST .../versions/git 保留；增强返回 name-status 摘要
```

兼容策略：旧字段 `root_file` / 扁平 `files` 暂留；前端逐步迁到 tree API。

---

## 9. 数据 / 状态机（阶段 3 重点）

```
[import]
   → tree_index 全部 compare_state=pending|skipped
   → (optional) auto-enqueue: Git name-status 中的 modified 文本 或 用户偏好

[user opens file]
   → enqueue path priority=high
   → file-pair 立即可读
   → compare ready → 挂载 DiffEditor + units

[user enables compare on dir ".foo"]
   → include that prefix → enqueue recursive

[compare worker]
   → hash align → status same|modified|...
   → persist → 下一次 GET diff-index 可见
```

---

## 10. 测试计划

| 层级 | 内容 |
|------|------|
| 单元 | tree builder、dot 过滤、root 候选打分、compare 跳过规则 |
| API | enqueue、diff-index 状态迁移、invalid zip、git name-status |
| 前端 | layout store 持久化、树折叠、隐藏面板、i18n |
| 手工 | 大 zip 论文工程；双 commit 论文；Accept→commit→log |
| 回归 | 既有 accept/undo/compile smoke |

---

## 11. 风险与决策点

| 决策点 | 选项 | 建议 |
|--------|------|------|
| Git 物化 vs 按需 show | 全量 archive vs 按文件 show | 大仓 **按文件 show** + name-status；小仓 archive |
| merged 与 git worktree | 独立 workspace vs 直连 worktree | 阶段 4 优先 **绑定 clone path** |
| 比较算力 | 仅 sha vs 全文 | 索引用 sha；打开文件再全文 |
| SSE vs 轮询 | | 先轮询，SSE 可选 |
| 点文件默认 | | 默认隐藏且 **不入比较队列** |

---

## 12. 里程碑勾选（执行时更新）

- [x] M1 可伸缩布局 + 树 + 点文件过滤（阶段 1）
- [x] M2 Root 用户选择 + 资产回归（阶段 2）
- [x] M3 异步按需比较（阶段 3）
- [x] M4 Git 对比与 commit 封装（阶段 4）
- [x] M5 VS Code 风格高级工作台（阶段 5）— 活动栏 + 底栏日志 + 布局重置；完整 mosaic 仍属 L

---

## 13. 与既有文档关系

- 替换/延伸：`2026-07-15-paper-diff-implementation.md` 的 **Deferred** 与 UX 部分。
- 设计增量：在 `2026-07-15-paper-diff-design.md` 增加「Workbench / Async Compare / Git facade」章节（实现阶段 0 时补）。
- 实现时同步 `AGENTS.md` 命令与架构指针。

---

## 14. 首期建议拆分任务（可直接开 issue）

1. `feat(web): resizable workbench panes + panel toggles`
2. `feat(web): hierarchical file tree with dot-path filter`
3. `feat(api): root candidates + set-root endpoint`
4. `feat(api): lazy diff-index + compare queue`
5. `feat(web): poll compare state; view-then-diff file open`
6. `feat(api): git name-status driven index`
7. `feat(api+web): commit accepted changes via git facade`
8. `feat(web): activity bar + bottom panel layout presets`

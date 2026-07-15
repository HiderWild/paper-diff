# paper-diff 产品重构计划：项目本体 · 比较区 · 内置 Git · Agent 接口

> **Status:** Draft / approved-for-planning — 2026-07-15  
> **Supersedes (model):** 旧「base + revised + merged」双 zip 对照主路径  
> **Preserves:** 工作台布局、树、编译、Monaco 词/句级可视化、i18n、Docker TeX 等能力底座  
> **Related:**  
> - 旧 MVP：`2026-07-15-paper-diff-implementation.md`  
> - 工作台：`2026-07-15-workbench-git-async-diff.md`  
> - 设计：`docs/superpowers/specs/2026-07-15-paper-diff-design.md`（将增量修订）

---

## 0. 一句话定位

**paper-diff = 面向科研/论文场景的「可持久化项目工作区」+「内置 Git 时间线」+「可插拔比较区」+「可选 Agent 审稿辅助」。**

用户只需导入 **一个** 项目（zip / 本地目录 / 已有 git 仓），在 **项目本体** 上持续写作与编译；所有外来修订稿、评审稿、局部片段都以 **比较区（Compare Zone）** 的形式附着在侧边，按需对照、接受、丢弃。

---

## 1. 为什么从 base/revised 迁走

| 旧模型 | 问题 | 新模型 |
|--------|------|--------|
| 必须成对上传 base + revised | 冷启动摩擦大；不符合「我已有一版论文」心智 | **单 zip / 单目录即可进入项目** |
| base / revised / merged 三棵树 | 概念多、UI 难讲清 | **一棵本体树 `work` + N 个比较区快照** |
| 修订只来自另一完整 zip | 局部对照、敏捷评审不方便 | 比较区支持 **完整包 / 子目录 / 多文件散装** |
| Git 是外部双 ref 物化 | 与项目生命期脱节 | **项目内 Git 即时间线**（提交间对比/捡回/丢弃） |
| 审稿靠人工 Accept chips | 大规模改动费力 | 预留 **LLM/Agent 接口**：解析差异、利弊、第三方案、inline 修改 |

---

## 2. 核心概念（新领域模型）

```
Project（项目）
├── work/                    # 项目本体工作树（用户可编辑、可编译）—— 唯一「真相草稿」
├── .git/                    # 项目内建或绑定的 Git 仓（历史与恢复）
├── zones/
│   ├── <zone_id>/           # 比较区快照（只读为主；可标注/可局部编辑策略后置）
│   │   ├── files/...
│   │   └── meta.json        # 名称、来源、创建时间、路径映射
│   └── ...
├── artifacts/               # 编译 PDF / log
├── jobs/                    # 异步任务
└── project.json             # 项目元数据（root tex、布局无关偏好等）
```

| 对象 | 含义 | 生命周期 |
|------|------|----------|
| **Project** | 持久化科研工作单元 | 创建 → 导入本体 → 日常编辑/提交 → 导出 |
| **Work tree** | 项目本体，等价于「当前在写的论文树」 | 可编辑；编译/导出都针对它 |
| **Compare Zone** | 一份参照快照（完整或局部） | 创建（zip/目录/多文件）→ 对照 → 删除 |
| **Git history** | work 树的提交时间线 | commit / checkout / 对比两提交 / 丢弃草稿变更 |
| **Diff session** | 某一时刻「左=左源，右=右源」的编辑会话 | 例如 `work@HEAD` vs `zone:abc`，或 `work@commitA` vs `work@commitB` |
| **Accept / Apply** | 把右（或 Agent 第三稿）写入 work 指定路径 | 受 revision/锁保护，可 undo，可再 commit |
| **Agent session**（后） | 对 DiffUnit 或文件的自然语言审阅与补丁 | 只写 work 或生成 zone 候选 |

### 2.1 Diff 左右侧规则（固定直觉）

| 位置 | 默认显示 | 可选 |
|------|----------|------|
| **左编辑器** | 项目本体 `work`（可编辑） | `work` 某历史 commit 的只读视图 |
| **右编辑器** | 当前激活的比较区（只读） | 另一 commit、或 Agent 提议草案 |

> 不再出现「基准版 / 修订版」产品文案；UI 文案改为「项目 / 比较区 / 历史」。

### 2.2 比较区 = 快照，不是第二项目

- 可与 work **同构**（完整论文 zip），也可是 **局部**（几张图说明改的 tex、或评审给的 chapter 目录）。
- 路径按「相对路径」对齐到 work；对不齐的文件单独列表（仅右有 / 仅左有）。
- **与 work 磁盘隔离**：删 zone 不影响 work；删 work 文件不影响 zone。
- 可多开、可命名、可删、默认识别为 `比较区 YYYY-MM-DD HH:mm:ss`。

---

## 3. 完整需求清单

### A. 项目本体（Project Core）

| ID | 需求 | 优先级 | 验收 |
|----|------|--------|------|
| A1 | 创建空项目 | P0 | `POST /projects` → 本地 work 目录 + 可选 init git |
| A2 | **单 zip 导入为本体** | P0 | 不必再传第二份 zip 即可浏览/编辑/编译 |
| A3 | 导入后 hoist 单顶层目录、过滤 __MACOSX | P0 | 与现有 zip 安全逻辑一致 |
| A4 | 文本 + 科研常用媒介进树 | P0 | tex/bib/cls/sty/md/csv/json/yml 等；二进制图/pdf 存盘可见 |
| A5 | 主 tex 启发式 + **用户选定**后编译 | P0 | 已有 root 候选能力迁移 |
| A6 | 导出 work 为 zip | P0 | 现有 export 指向 work |
| A7 | 持久化（可跨重启） | P1 | 配置 `CLEAR_WORKSPACE_ON_STARTUP=false` 时保留；文档说明 dev 默认清 |
| A8 | 从本地文件夹「打开项目」 | P2 | 非浏览器安全限制时：本机路径或已绑 worktree |
| A9 | 从已有 Git 仓绑定为本体 | P1 | clone 或 link local path，history 直接用 |

### B. 比较区（Compare Zones）

| ID | 需求 | 优先级 | 验收 |
|----|------|--------|------|
| B1 | 多比较区列表；默认时间戳名；可自定义名 | P0 | UI 列表 + rename |
| B2 | **zip 上传**创建 zone | P0 | 可完整/局部结构 |
| B3 | **多文件选择**上传（敏捷） | P0 | 相对路径可扁平或用户指定 prefix |
| B4 | **目录上传**并保留目录结构 | P0 | 使用 `webkitdirectory` 或等价；路径正确 |
| B5 | 文本检测：不可解析为文本的导入策略 | P0 | 默认跳过非文本并提示清单；图片可「作为资源并存」选项后置 |
| B6 | 表格类文本（csv/tsv）进入可比较集合 | P0 | 按文本 diff；后续专用表格 diff |
| B7 | 删除比较区 | P0 | 盘空间释放，不碰 work |
| B8 | 激活某个 zone 作为右侧对照 | P0 | Diff 右=zone 对应路径 |
| B9 | 按路径异步 compare；点目录默认跳过 | P1 | 复用现有 compare queue 思想 |
| B10 | zone 内资源只读预览（图） | P2 | 点击显示，不进 Monaco 强制 |
| B11 | zone 从 git commit 一键生成 | P1 | `zone from commit` |
| B12 | zone 从 work 当前树克隆为快照 | P2 | 「存一版对照」 |

### C. 对照与接受（Diff / Accept）

| ID | 需求 | 优先级 | 验收 |
|----|------|--------|------|
| C1 | 左 work / 右 zone 对照打开文件 | P0 | 路径映射策略明确 |
| C2 | 词/句/块 Accept：写回 **work** | P0 | 保留 merge_engine 行级补丁 |
| C3 | 整文件采用 zone 版本 / 保留 work | P0 | replace / ignore |
| C4 | Undo 最近接受 | P0 | 快照栈 |
| C5 | 与 zone 无关的纯编辑 work | P0 | 单栏编辑模式 |
| C6 | **两 Git commit 之间**对照 | P1 | 左右都是只读历史 或 左 work 当前 vs 某 commit |
| C7 | Accept 后可选自动提示 commit | P1 | 不默认强制 |

### D. 项目内 Git（时间线）

| ID | 需求 | 优先级 | 验收 |
|----|------|--------|------|
| D1 | 项目创建时 `git init`（若未绑定外部仓） | P0 | 首次提交可空或「Initial import」 |
| D2 | status / stage / commit 封装 | P0 | 论文友好 message 模板 |
| D3 | **可视化树形/列表 Git 历史** | P0 | 时间序 + 摘要；可筛选 path |
| D4 | 对比任意两提交（name-status + 打开文件 diff） | P0 | 驱动右侧对照源 |
| D5 | **捡回**：将某提交某文件/树恢复到 work | P1 | checkout path / restore |
| D6 | **丢弃**：丢弃 work 未提交变更 | P1 | restore --worktree |
| D7 | 分支：简单 create / switch（可选） | P2 | 先单 branch 也可 |
| D8 | 与远程 push/pull（显式、后置） | P3 | 鉴权后置 |
| D9 | LFS 提示与降级 | P3 | 大文件不静默损坏 |

### E. 工作台与 UX（承接已有）

| ID | 需求 | 优先级 | 验收 |
|----|------|--------|------|
| E1 | 默认布局：文件树 + 对照编辑器 + PDF | P0 | flex 稳定，不挤没中间栏 |
| E2 | 树状展开；点文件过滤；栏可藏可拖 | P0 | 已修复方向上持续 polish |
| E3 | 活动栏：资源 / 比较区 / Git / 编译 | P0 | zone 列表进「比较区」视图 |
| E4 | 中英文 i18n | P0 | 去 base/revised 文案 |
| E5 | 大包上传进度与 500MB 限制 | P1 | 进度条 UX |
| E6 | 启动清理工作区可配 | P0 | 已有 CLEAR_WORKSPACE… |

### F. 编译

| ID | 需求 | 优先级 | 验收 |
|----|------|--------|------|
| F1 | 仅编译 **work**（合并结果不再是第三树） | P0 | Docker latexmk |
| F2 | 资源（图等）必须在 work 树内 | P0 | 接受 zone 图时拷进 work |
| F3 | latexdiff 可选：work@A vs work@B 或 work vs zone 根 tex | P2 | PDF 侧路 |

### G. 可解析媒介与富 diff（中长期）

| ID | 需求 | 优先级 | 验收 |
|----|------|--------|------|
| G1 | 扩展「文本可比较」扩展名与 sniff | P1 | csv/tsv/json/yaml/xml/md/R/py 等 |
| G2 | 启发式 binary vs text（扩展名 + 空字节） | P0 | 上传报告 |
| G3 | CSV 表结构感知 diff | P2 | 行键对齐后标 cell |
| G4 | 图片 perceptual / 并排预览 | P2 | 非 git-only |
| G5 | PDF 文本层抽取后 diff（可选） | P3 | 重 |
| G6 | 自研 parse+diff 插件位 | P2 | 注册表接口 |

### H. LLM / Agent 接口（面向后续接入）

| ID | 需求 | 优先级 | 验收 |
|----|------|--------|------|
| H1 | **只读分析 API**：输入 left/right 文本 + DiffUnits → 结构化利弊/侧重点 | P1 契约 / P2 实现 | Schema 稳定 |
| H2 | **第三方案生成**：产出 patch 或完整文件建议 | P2 | 不直接覆盖 work 除非确认 |
| H3 | **Inline chat 上下文**：当前文件、选区、zone id、commit 范围 | P2 | 类似 copilot inline |
| H4 | **Apply agent patch**：统一走 merge_engine / 整文件写 | P2 | 带 undo |
| H5 | Provider 可插拔（HTTP webhook / OpenAI 兼容 / 本地） | P2 | env 配置 |
| H6 | 无密钥时 graceful degrade | P1 | UI 隐藏或禁用并说明 |
| H7 | 审计：agent 操作写入 accept_log / agent_log | P2 | 可导出 |
| H8 | MCP 或 OpenAPI 文档给外部 agent 调用 | P3 | |

### I. 非目标（明确不做或暂缓）

- 把 paper-diff 做成通用 GitHub 客户端  
- 实时多用户 CRDT  
- 浏览器内完整 TeX 引擎替代 Docker  
- 第一次迭代就做全媒介视觉 diff  
- 强制云端存储  

---

## 4. 信息架构（UI）

```
┌─ Toolbar: 打开/导入项目 · 导出 · 编译 · 语言 · 布局 ─────────────┐
├─ Activity ─┬─ Side ──────────┬─ Editor ────────────┬─ PDF ──────┤
│  📂 项目    │  work 目录树     │  左: work            │  预览      │
│  ⧉ 比较区   │  zone 列表+树    │  右: zone|历史|草案   │            │
│  ⎇ Git     │  提交树/历史      │  Accept chips / Chat │            │
│  ⚙ 编译    │  入口/错误        │                      │            │
└────────────┴──────────────────┴──────────────────────┴────────────┘
└─ 底栏：Log / Agent 输出 ─────────────────────────────────────────┘
```

**导入入口简化：**

1. 「打开/新建项目」→ 上传 **一个** zip（或后续本地路径）  
2. 「添加比较区」→ zip / 文件夹 / 多文件 + 名称  

---

## 5. 存储与 API 草案

### 5.1 磁盘

```
{workspace_root}/{project_id}/
  project.json
  work/                 # 本体
  zones/{zone_id}/
    meta.json           # { id, name, created_at, source, path_prefix? }
    tree/...            # 快照文件
  .git/                 # 若内建
  artifacts/
  jobs/
  snapshots/            # accept undo
```

### 5.2 HTTP（增量，阶段落地）

```
# 项目本体
POST   /projects
POST   /projects/{id}/work/import/zip
POST   /projects/{id}/work/import/files      # multipath + relative paths
GET    /projects/{id}/work/tree
GET    /projects/{id}/work/file?path=
PUT    /projects/{id}/work/file?path=        # 可选整文件保存
POST   /projects/{id}/work/export.zip

# 比较区
GET    /projects/{id}/zones
POST   /projects/{id}/zones                  # { name? }
POST   /projects/{id}/zones/{zid}/import/zip
POST   /projects/{id}/zones/{zid}/import/files
DELETE /projects/{id}/zones/{zid}
PATCH  /projects/{id}/zones/{zid}            # rename
GET    /projects/{id}/zones/{zid}/tree
GET    /projects/{id}/zones/{zid}/file?path=

# 对照会话
POST   /projects/{id}/diff/session           # { left, right } 源描述符
GET    /projects/{id}/diff/pair?path=&left=&right=
POST   /projects/{id}/accept                 # 仍 line/col，目标固定为 work

# Git
GET    /projects/{id}/git/log?max=
GET    /projects/{id}/git/status
POST   /projects/{id}/git/commit
POST   /projects/{id}/git/restore            # discard or path from commit
POST   /projects/{id}/git/zone-from-commit

# 编译（目标 work）
POST   /projects/{id}/compile
POST   /projects/{id}/root

# Agent（契约先行）
POST   /projects/{id}/agent/analyze
POST   /projects/{id}/agent/propose
POST   /projects/{id}/agent/apply
GET    /projects/{id}/agent/sessions/{sid}
```

**源描述符示例：**

```json
{ "kind": "work", "ref": "HEAD" }
{ "kind": "work", "ref": "abc1234" }
{ "kind": "zone", "zone_id": "z1" }
{ "kind": "agent_draft", "draft_id": "d9" }
```

---

## 6. 与现有代码的迁移策略

| 现有 | 迁移 |
|------|------|
| `base/` `revised/` `merged/` | 逐步改为 `work/` + `zones/`；兼容期：import 单 zip → work，第二 zip 可选转 zone |
| `merge_engine` | **保留**；目标侧固定 work |
| `compare_service` | 改为 work↔zone 或 commit↔commit 路径队列 |
| `compile_service` | side 默认 work |
| `git_service` | 升为项目核心时间线，不只绑定外部 repo |
| 前端 `base/revised` 文案 | i18n 全换「项目/比较区」 |
| 双 zip 上传 UI | 改为「导入项目」+「添加比较区」 |

**兼容层（Phase 0–1）：**  
旧 `POST .../versions/upload` 可映射：`base→work`，`revised→自动建 zone「imported revised」`，避免瞬间踩烂测试；Phase 2 废弃。

---

## 7. 长程分阶段路线图

### Phase 0 — 基线与模型冻结（0.5–1 周）

**目标：** 文档、契约、不写大迁移。

- [ ] 本文件评审定稿；更新 design spec 核心模型章节  
- [ ] OpenAPI/DTO 草图 review  
- [ ] 列出破坏性 API 清单与兼容策略  
- [ ] 验收清单与 fixture 设计（单 zip 论文 + 局部 chapter zone）

**产出：** 团队对齐「无 base/revised 产品语义」。

---

### Phase 1 — 项目本体单树（1–2 周）**【优先开工】**

**目标：** 用户 **只导一个 zip** 就能用。

- [ ] 后端：`work/` 目录、import zip、tree、file get  
- [ ] 编译/export 指向 work  
- [ ] 前端：导入入口改为单文件；树绑 work  
- [ ] 兼容：旧双 zip API → work + 自动 zone  
- [ ] 测试：单 zip 全流程  

**价值：** 冷启动体验立刻正确。

---

### Phase 2 — 比较区 MVP（1–2 周）

**目标：** 多 zone、隔离、对照、删除。

- [ ] zone CRUD + zip/files 导入  
- [ ] 目录上传（webkitdirectory）保结构  
- [ ] 多文件敏捷上传 + 文本 sniff + 跳过报告  
- [ ] Diff 左 work 右 zone；Accept 写 work  
- [ ] 活动栏「比较区」列表；默认时间名/可改名  
- [ ] 删除 zone  

**价值：** 「修订参照」模型落地。

---

### Phase 3 — 项目内 Git 时间线（1–2 周）

**目标：** 本体可提交、可看历史、可两提交对比。

- [ ] import 后 init + initial commit  
- [ ] status / commit UI  
- [ ] log 可视化（列表→简易树）  
- [ ] 两提交 name-status + 打开 diff  
- [ ] restore path / discard dirty  
- [ ] 「从提交创建比较区」  

**价值：** 论文版本管理回归 Git，但更好用。

---

### Phase 4 — 工作台打磨与路径对齐（并行 ~1 周）

**目标：** 默认三栏稳、树可靠、大项目可开。

- [ ] 异步 path compare（work↔zone）  
- [ ] 点目录默认跳过  
- [ ] 布局/i18n 清扫残留 base/revised  
- [ ] 上传进度、错误可读  

---

### Phase 5 — 媒介扩展（1–2 周，可切片）

**目标：** 多学科文本/表格可进。

- [ ] 扩展文本 sniffer + 白名单  
- [ ] CSV 结构 diff 试验  
- [ ] 图片并排预览  
- [ ] 插件式解析器注册接口草案  

---

### Phase 6 — Agent 契约与最小闭环（2–3 周）

**目标：** 可插 provider 的分析 + 提议 + 确认应用。

- [ ] DTO：AnalyzeRequest/Response、Propose、Apply  
- [ ] Stub provider（规则/回显）保证无密钥可测  
- [ ] UI：侧栏/inline 面板展示「左优势/右优势/建议」  
- [ ] Apply → accept/undo 同管道  
- [ ] agent_log 审计  
- [ ] 真实 provider 适配（可选）  

**价值：** 为后续接 Hermes/外部 agent 留稳定接口。

---

### Phase 7 — Inline chat 体验（2+ 周）

**目标：** 逼近编辑器内 Copilot 改法。

- [ ] 选区上下文打包  
- [ ] 流式输出（SSE）  
- [ ] 预览补丁高亮 → 一键应用  
- [ ] 从 zone 全文「请按期刊意见改」  

---

### Phase 8 — 生态与硬化（持续）

- [ ] 远程 git、鉴权  
- [ ] MCP / OpenAPI 公开  
- [ ] 多租户、权限  
- [ ] 富媒体 diff 加深  
- [ ] 性能：大仓 sparse、虚拟列表  

---

## 8. 阶段依赖图

```
Phase0 模型冻结
   │
   ▼
Phase1 单本体 work  ◄── 可立刻替代「双 zip 必传」
   │
   ├──────────────► Phase4 工作台/异步 polish（可并行）
   ▼
Phase2 比较区 MVP
   │
   ▼
Phase3 内置 Git 时间线
   │
   ├──────────────► Phase5 媒介扩展
   ▼
Phase6 Agent 契约 + stub
   │
   ▼
Phase7 Inline chat
   │
   ▼
Phase8 生态硬化
```

**推荐执行顺序：**  
`0 → 1 → 2 → 3` 为 **主航道**；`4` 与 `2/3` 穿插；`5` 按用户痛点插入；`6/7` 在主航道稳定后全力推进。

---

## 9. 风险与决策

| 风险 | 缓解 |
|------|------|
| 大迁移踩烂现有测试 | 兼容层 1–2 阶段；测试分「legacy mapping」与「new model」 |
| 浏览器目录上传路径不一 | 统一 `webkitRelativePath` 规范化 |
| 用户误删 zone | 删除确认；无回收站 MVP，可后续 trash |
| Git 历史图复杂 | Phase3 先线性 log，树图 Phase3.5 |
| Agent 胡写论文 | 默认只提议；Apply 需确认；全程 undo |
| 启动清理与「持久化项目」矛盾 | 开发默认 clear=true；产品文档强调生产 false |
| 局部 zone 路径对不齐 | 导入时可设 `path_prefix`；UI 显示未对齐文件 |

### 已拍板建议（可改）

1. **左永远可编辑的是 work 当前树**（看历史时临时只读切换要显式）。  
2. **Zone 默认只读**；要改 zone 不如新建 zone。  
3. **Git 历史是第一公民**；zone 是第二公民（外来参照）。  
4. **Agent 先契约后实现**，禁止没 schema 就绑死某家模型。  

---

## 10. 成功度量

| 里程碑 | 用户可感知结果 |
|--------|----------------|
| M1 (Ph1) | 一个 zip 进项目，编译 PDF |
| M2 (Ph2) | 丢进比较区对照章节，Accept 回本体 |
| M3 (Ph3) | 提交历史里对比两版引言，捡回误删 |
| M4 (Ph6) | Agent 列出双方修改侧重点并给第三稿预览 |
| M5 (Ph7) | 选中段落 inline 让 agent 改语气并应用 |

---

## 11. 立即可开的工程任务包（Issue 级）

1. `docs: freeze project-core + zones domain model`（本文）  
2. `refactor(api): introduce work/ tree + single zip import`  
3. `feat(api): zones CRUD + zip/files import + delete`  
4. `feat(web): import project / add zone UX; remove dual-zip requirement`  
5. `feat(web): activate zone as right-hand diff source`  
6. `feat(api+web): project-local git init/log/commit/restore`  
7. `feat(web): git history panel`  
8. `feat(api): agent analyze/propose/apply schemas + stub`  
9. `test: fixtures single-zip + partial zone chapter`  
10. `chore: deprecate base/revised paths after Ph2`  

---

## 12. 文档与仓库指针（落地后维护）

| 文件 | 动作 |
|------|------|
| 本文 | **主长程计划** |
| `AGENTS.md` | 增加指针与新 env |
| `2026-07-15-paper-diff-design.md` | 追加「v2 领域模型」章节 |
| 旧 base/revised 文案 | Phase1–2 逐步替换 |

---

## 13. 总结

新体系用 **「一个可持久化的项目本体 + 任意多个比较区快照 + 内置 Git 时间线」** 替代 **「成对 base/revised」**，心智更简单、更贴合真实论文协作：

- 导入变轻：一 zip 开工  
- 对照变灵活：整包、目录、散文件都是 zone  
- 历史变正经：Git 可视化捡回/丢弃  
- 未来变聪明：Agent 分析与 inline 改稿走同一套 work 写入管线  

**主航道 Phase 0→1→2→3 完成后，产品已可独立交付价值；Agent 与富媒介是增强层，不挡主航道。**

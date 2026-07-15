# paper-diff 长文件浏览 / 比较性能方案（收紧版）

> **Status:** Design ready · v1.1 **语义锁定 + 防过度设计** — 2026-07-15  
> **Scope:** 超长/超大 **文本** 在编辑器与比较器中的性能；**不改变** 产品既有功能语义  
> **Related:**  
> - 真源拉取：`2026-07-15-comparer-preview-hardening.md`（C0 语义优先）  
> - UX：`2026-07-15-ux-gap-closure.md`  
> - Agent：`AGENTS.md`  

---

## 0. 一句话

**卡顿来自「全文下载 + 全文 diff/unit」，不是 Monaco 不会虚拟滚。用「门槛 + 少算 + 按行切片」三档治；比较器大文件走「变更目录 + 局部 Diff」，禁止另起一套交互语义。**

---

## 1. 语义不漂移（硬约束）

下列 **现有产品语义** 优化后必须保持；任何实现若做不到，**降级为慢路径**，不得 silent 改行为。

| ID | 语义 | 大文件下的要求 |
|----|------|----------------|
| **S1** | 文本单击 → **编辑器**；右键「新建比较」→ **比较器** | 不变 |
| **S2** | 比较器左 = **work 路径**；右 = **CompareTarget**（zone/git + path） | 不变；目标选择/记忆 API 不变 |
| **S3** | 箭头/拉取 = **对照侧可见文本 → work**（真源） | 窗口模式下必须用 **全局行号 + range 写**；禁止 put 半截全文 |
| **S4** | autosave / undo / 整文件接受 的用户可见含义 | 可改 **实现**（range PUT）；用户仍感知「改的是这个文件」 |
| **S5** | 小文件体验 | **零新概念**；无「变更地图」强制 UI |
| **S6** | 坏文件/二进制 | 与现网一致：不进文本比较器 |

### 1.1 明确不做什么（防过度设计）

| 不做 | 原因 |
|------|------|
| 自研编辑器 / 替换 Monaco | 成本高，Monaco 已有视口渲染 |
| 默认模式 B「假全文高度 + 仅窗口 model」 | 滚动/选区/跳转易漂语义；留给 XL 可选 |
| 一上来 WASM diff / OT / 协作 | 非瓶颈首解 |
| 服务端全文流式 SSE | 复杂度高；slice 足够 |
| 多 Worker 并行灌同一全文 | 增加拷贝与主线程压力 |
| 为长文件重做整套「侧边预览语言」 | 与比较器/编辑器概念分叉 |
| 改变 accept 的「应用对照」含义 | 与真源计划冲突 |

### 1.2 允许的唯一 UX 增量（且仅在大文件）

当且仅当文件达到 **L 档**（§3）时，比较器可多一块：

- **变更目录（hunk list）**：点击后主区展示 **该 hunk ± 上下文** 的 Diff（仍是同一比较器工具，不是新工具类型）。

小文件 **不得** 出现该目录强占 UI。

---

## 2. 现状瓶颈（对照实现）

| 环节 | 代码现实 | 问题 |
|------|----------|------|
| 读 | `work/file`、`file-pair` 整文件 | 大 JSON + 内存 |
| 模型 | Monaco `setValue` 全文 | 分配与 tokenization |
| Diff | DiffEditor advanced 全文 | CPU |
| Unit | `buildDiffUnits` 主线程全量 | 二次放大 |
| 写 | `PUT` 全文 | 大回写 |

结论：优先 **少传、少 diff、少 unit**；再做切片。

---

## 3. 门槛（简单、可调）

| 档 | 条件（任一满足） | 行为 |
|----|------------------|------|
| **S** | &lt; 256KiB 且 &lt; 3k 行 | 现状全量；可选 idle 调度 unit |
| **M** | 256KiB–2MiB 或 3k–20k 行 | 仍可全量载入；**默认** legacy diff、限制开局 unit 数量、箭头视口裁剪 |
| **L** | &gt; 2MiB 或 &gt; 20k 行 | 编辑：滑动窗口读；比较：**hunk 目录 + 局部 Diff**；range 写 |
| **硬顶** | 单次 slice &gt; 4000 行或响应 &gt; 配置字节 | API 422 |

元数据：`byte_size` + `line_count`（缺省则先流式数行或首次打开时统计并缓存）。

---

## 4. 目标架构（只保留必要层）

```
┌─────────────────────────────────────────┐
│  L0  便宜开关：算法/unit 上限/idle/Worker │  ← 先做
├─────────────────────────────────────────┤
│  L1  按行 slice + meta（work/zone/git）   │  ← 数据面
├─────────────────────────────────────────┤
│  L2  编辑器窗口：视口 → 后 H → 前 H        │  ← 浏览
├─────────────────────────────────────────┤
│  L3  比较器：行 hash 目录 + 局部 Diff      │  ← 比较
├─────────────────────────────────────────┤
│  L4  range 写回（保存/拉取/autosave）       │  ← 正确性
└─────────────────────────────────────────┘
```

### 4.1 L0 — 不改 API 的降载（P0 体验）

| 动作 | 语义影响 |
|------|----------|
| 大文件 `diffAlgorithm: 'legacy'` | 无；仅速度 |
| 开局 **不** 跑全量 sentence/word unit；箭头仅用 line/hunk 且 **视口附近** | 无顶栏 chips 依赖（已去掉） |
| `requestIdleCallback` 建 unit | 无 |
| 保持 Monaco worker | 无 |

### 4.2 L1 — Slice / Meta API（P0 数据）

最小集：

```
GET .../work/file-meta?path=
GET .../work/file-slice?path=&start_line=&end_line=

GET .../zones/{id}/file-meta|file-slice?...
GET .../git/show-meta|show-slice?ref=&path=&start_line=&end_line=
```

规则：

- 行号 **1-based 闭区间**；单次行数上限。  
- 返回 `{ start_line, end_line, line_count, content, sha256? }`。  
- **path 安全** 与现有 file API 一致。  

可选（非阻塞）：服务端 line-offset 缓存，仅当 slice 过慢再做。

### 4.3 L2 — 编辑器窗口（P1，语义 S1/S4）

Prefetch（粒度=**行**，与用户描述一致）：

1. 视口 `[V0,V1]`，`H = V1-V0+1`  
2. 后文 `[V1+1, V1+H]`  
3. 前文 `[V0-H, V0-1]`  
4. 沿滚动方向半屏扩展；总缓存 ≤ `Wmax`（约 3–5 屏）淘汰远端  

**集成（唯一推荐实现，避免双模式纠结）：**

- Monaco model 仍表示 **逻辑全文**，但对未加载行使用 **统一占位行**（如空行或 `·`）+ decoration 标明「未加载」；  
- 进入视口前/后按上式 fetch，用 `applyEdits` 换成真文本；  
- **禁止**在仍有占位洞时 `PUT` 全文；保存/autosave 见 L4。  

不实现模式 B（假高度），除非 L 实测内存仍炸再开附录。

### 4.4 L3 — 比较器（P0 比较语义 S2/S3）

对 **L 档** 两侧：

1. **Worker** 按行 hash（或长度+采样 hash）→ 行级对齐 → **hunk 列表**（全局行号）。  
2. UI：hunk 列表 + 主区 **只 Diff 当前 hunk ± K 行**（仍是 comparer Tab）。  
3. 拉取：对当前局部 buffer 做真源 snippet，写入用 **全局行号** 的 L4。  
4. S/M 档：保持现有双边 DiffEditor + 真源 apply，**不**强塞 hunk 列表。

**不做**「窗口双边硬 Diff 全文连贯阅读」作为默认——那是复杂度陷阱；连贯阅读用编辑器窗口即可。

### 4.5 L4 — 写回（P0 正确性，S3/S4）

```
PUT .../work/file-range
{ path, start_line, end_line, content, base_sha256? }
```

- autosave / 箭头拉取 / 局部编辑：优先 range。  
- 小文件可继续全文 PUT。  
- **绝对禁止** 用「仅窗口文本」当全文 PUT。  
- undo：继续现有 snapshot 策略即可（可先整文件快照，不必第一步就 range-undo）。

---

## 5. 实施步骤（短、可交付）

### Step 0 — 门槛与观测（≤1d）

- [ ] open 路径取 size/lines（先客户端粗算也可：length + split 计数，仅 M+ 提示）  
- [ ] 设置预留：`largeFileMode: auto`（暂不暴露复杂 UI）  
- [ ] 记录基线：10k/30k 行打开卡顿  

### Step 1 — L0 降载（≤1d）〔必须先做〕

- [ ] 阈值触发：legacy diff、unit 上限、箭头视口过滤  
- [ ] idle 调度 `buildDiffUnits`  
- [ ] 回归：S 档行为与现在一致  

### Step 2 — Meta + Slice 读 API（1–2d）

- [ ] work/zone/git slice+meta  
- [ ] pytest：边界、超限、遍历拒绝  

### Step 3 — 编辑器窗口读（2d）

- [ ] 视口→后 H→前 H  
- [ ] 占位 + applyEdits  
- [ ] 状态：`已加载 a–b / 共 N`（可放 tab 副标题或 status 一行）  

### Step 4 — range 写 + 接 autosave/拉取（1–2d）

- [ ] `file-range` PUT  
- [ ] 大文件 autosave / `applyCompareUnit` 走 range  
- [ ] 有洞则先补 slice 再写或拒绝并 toast  

### Step 5 — 比较器 hunk 目录 + 局部 Diff（2–4d）

- [ ] Worker 行 hash 索引  
- [ ] L 档 UI 切换到「列表 + 局部」；S/M 不变  
- [ ] 拉取用真源 + 全局行号 + range  

### Step 6 — 文档与声称

- [ ] manual-smoke：大文件打开/滚动/保存/拉取  
- [ ] AGENTS：写明 L 档比较器形态  

---

## 6. 验收（防语义漂）

| 场景 | 期望 |
|------|------|
| 小 `.tex` 单击 | 编辑器，全功能，无 hunk 强制 UI |
| 大文件滚动 | 先清视口再扩展，可卡顿提示但不可假死 |
| 大文件保存 | 磁盘与编辑一致；无截断 |
| L 比较：选 git 目标拉一行 | work 该行 = 右侧该行（真源） |
| 非 active zone 对照 | 与 hardening 计划一致 |
| 关闭大文件 Tab | 缓存释放，无泄漏暴涨 |

---

## 7. 风险（只列真的）

| 风险 | 处理 |
|------|------|
| 占位行被用户误存 | 写前检测洞；toast |
| hash 粗 diff 漏/多 hunk | 可接受索引误差；局部 Diff 再确认 |
| 无 line-index 时 slice 慢 | 懒建缓存；首包可稍慢 |
| 与 word wrap | L 默认建议关 wrap（已有 Alt+Z） |

---

## 8. 决策锁定（默认已拍板，无需再开产品会）

| 项 | 默认 |
|----|------|
| Prefetch | **视口 → 后 1 屏 → 前 1 屏** |
| L 比较 UI | **hunk 目录 + 局部 Diff** |
| 大文件编辑 | **允许**，range 写 |
| 模式 B 虚拟高度 | **不做**（附录） |
| WASM / 搜索全集 | **不做**（本计划） |

---

## 9. 附录：仅当 Step 3 内存仍爆再考虑

- 模式 B：仅窗口 model + 虚拟 scrollHeight  
- 须单独立项，重验收滚动与选区  

---

## 10. 文件触点（实现时）

| 层 | 路径 |
|----|------|
| API | `routes.py`，`workspace_fs` / project_service 读切片写 range |
| Web | 新 `textWindow.ts`（尽量薄）；`MonacoDiff` 选项；`project` open/save 分流 |
| Worker | `workers/lineHash.ts`（可仅 Step 5） |
| 测试 | slice/range pytest；窗口 merge vitest；大文件 smoke |

---

## 11. 与既有计划关系

```
comparer-preview-hardening  ──真源──►  本计划 L4/L3 不得违背
ux-gap-closure              ──骨架──►  本计划不重做工作台
本计划                       ──只加性能路径与 L 档比较形态──
```

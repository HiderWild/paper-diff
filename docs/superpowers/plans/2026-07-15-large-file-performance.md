# paper-diff 长文件浏览 / 比较性能方案

> **Status:** Design ready · not implemented — 2026-07-15  
> **Scope:** 超长/超大文本在 **编辑器** 与 **比较器** 中的卡顿治理；API 按需读、前端渲染与 diff 计算分层  
> **Related:**  
> - 比较器真源：`2026-07-15-comparer-preview-hardening.md`  
> - UX 骨架：`2026-07-15-ux-gap-closure.md`  
> - Agent：`AGENTS.md`  

---

## 0. 一句话

**Monaco 已自带视口虚拟渲染，但我们目前仍「全量下载 + 全量 `setValue` + 全量 diff/unit」——卡顿主因在载荷与计算，不在 DOM 行数。方案分三层：资源/Worker 加速、按阈值窗口加载、比较器专用分块 diff。**

你提出的「目标区 → 后文 1 屏 → 前文 1 屏」**可采纳**，作为 **L2 窗口策略** 的默认 prefetch 形状；再补 **行级索引 API、阈值化门槛、Worker 与降级策略**。

---

## 1. 现状瓶颈（对照代码）

| 环节 | 现状 | 卡顿点 |
|------|------|--------|
| 传输 | `GET work/file` / `file-pair` 整文件 JSON | 大文件主线程 JSON.parse + 内存翻倍 |
| 模型 | `createModel(fullText)` + `setValue` | 大字符串分配、tokenizer 扫描 |
| Diff | DiffEditor 默认 advanced 对两份全文 | CPU 爆；行级 change 列表巨大 |
| Units | `buildDiffUnits` 在 **主线程** 遍历所有 lineChanges → hunk/word/sentence | 二次放大 CPU/GC |
| 箭头 | 每次 diff 更新 `placeArrows` | change 多时布局抖动 |
| 保存 | `PUT` 全文 | 大文件写回延迟 |

结论：**不是「没有虚拟列表」**，而是 **还没虚拟「数据面」**。浏览器层加速不能替代分块策略。

---

## 2. 设计原则

1. **渲染层**：继续用 Monaco（已有 viewport 渲染）；不开「整页滚动手写虚拟列表」替代 Monaco。  
2. **数据层**：按 **行区间** 拉取/缓存；客户端维护 **稀疏全文件模型** 或 **滑动窗口模型**。  
3. **比较层**：先 **粗 diff（行哈希）**，再对可见/近可见 hunk **细 diff**；unit 延迟到需要 accept 时。  
4. **计算层**：重活进 **Web Worker**（hash / 行切 / 可选 diff）；主线程只改 model 与 UI。  
5. **门槛分级**：小文件零成本；中等优化选项；大文件强制窗口模式。  
6. **正确性**：accept / autosave / 真源拉取必须定义「全局行号 ↔ 窗口」映射；**禁止在仅加载窗口时写出残缺全文**。

---

## 3. 规模门槛（建议默认）

| 级别 | 条件（约） | 策略 |
|------|------------|------|
| **S 小** | &lt; 256 KiB 且 &lt; 3k 行 | 现状全量；可开 Worker 可选 |
| **M 中** | 256 KiB–2 MiB 或 3k–20k 行 | 全量可载，但 **关 word 级 unit**、diff 用 `legacy`/`advanced` 可配置；Worker 做 hash |
| **L 大** | &gt; 2 MiB 或 &gt; 20k 行 | **窗口加载** + 粗 diff 索引；禁止开局全量 sentence unit |
| **XL 极大** | &gt; 8 MiB 或 &gt; 80k 行 | 强制只读预览优先；编辑需「明确打开」确认；比较默认 **分块侧车 UI**（见 §5） |

阈值用服务端 `HEAD`/meta：`byte_size` + `line_count`（Step A 增加）。

---

## 4. 三层架构

### 4.1 L0 — 浏览器 / 框架资源（低成本、先做）

| 项 | 做法 | 收益 |
|----|------|------|
| **Monaco Worker** | 确保 `MonacoEnvironment.getWorker` 分离；可选增加 editor worker 配额 | 语法/排版不堵 UI |
| **差分算法** | 大文件 `diffAlgorithm: 'legacy'` 或降采样；可设置开关 | 立刻降 CPU |
| **关闭昂贵 UI** | 大文件默认 `renderIndicators` 可关、wordWrap 默认关、箭头上限 N | 减 layout |
| **Scheduler** | `requestIdleCallback` / `scheduler.postTask` 做 unit 构建 | 减卡死 |
| **Offscreen 不适用** | 文本编辑不用 Canvas；PDF 已单独优化 | — |
| **WASM**（可选） | 后期再议 LCS/diff（如 patience/histogram 的 wasm 实现） | 非 P0 |

**不建议**：盲目多 WebWorker 并行打开同一文件（抢主线程 postMessage 带宽）。

### 4.2 L1 — 后端按行窗口 API（数据面）

新增（示意）：

```
GET /projects/{id}/work/file-slice?path=&start_line=&end_line=
→ { path, start_line, end_line, line_count, content, encoding, truncated? }

GET /projects/{id}/work/file-meta?path=
→ { path, byte_size, line_count, sha256, mtime }

# 比较侧
GET .../zones/{zid}/file-slice?...
GET .../git/show-slice?ref=&path=&start_line=&end_line=
```

约束：

- **行闭区间**，1-based；`end_line` 可封顶（如单次 ≤ 4000 行）。  
- 超大响应拒绝（与 `max_upload` 类似的 `max_slice_bytes`）。  
- 提供 **line index**：可选 companion `.lineidx` 或首次扫描缓存 offset 表（服务端，便于 O(1) seek）。

### 4.3 L2 — 前端滑动窗口（你提的加载形状）

对每个打开的 path 维护：

```
Window = {
  startLine, endLine,     // 已加载闭区间
  targetStart, targetEnd, // 视口 ± overscan
  lines: Map<lineNo, string> | rope,
  fullLineCount,
  sha256?
}
```

**Prefetch 策略（默认，与你描述对齐，粒度=行）**

设视口可见 `[V0, V1]`（行），`H = V1 - V0 + 1`（约一屏行数）：

1. **优先**：加载 `[V0, V1]`  
2. **后文**：`[V1+1, V1+H]`（一倍浏览长度）  
3. **前文**：`[V0-H, V0-1]`  
4. 之后按滚动方向 **半屏步进** 扩展，合并相邻空洞  
5. 窗口总行数上限 `Wmax`（如 3H～5H）；超出则 **丢弃远离视口** 的一侧（方向：反滚动方向）

Monaco 集成两种模式（二选一，推荐 **B 进阶**）：

| 模式 | 做法 | 利弊 |
|------|------|------|
| **A 填充占位** | 模型仍是「全文件」，未加载行用 `…` 或空行 + decoration；滚动到洞时 fetch 再 `applyEdits` | 实现快；仍占行结构内存 |
| **B 虚拟模型 + 固定虚拟高度** | model 仅窗口文本；`scrollTop` 用 **总行数 × lineHeight** 伪装文档高度；换窗口时重设 model 并校正 scroll | 内存最小；滚动条/跳转/选区复杂 |

**推荐路径：** S/M 用全量；L 用 **A 填充占位 + 真切片**；XL 评估 B 或侧车。

### 4.4 L3 — 比较器专用（比单文件更重）

全量 DiffEditor 对「两侧各 5 万行」不现实。建议 **双轨**：

**轨 1：快速导航（索引）**

1. 两侧按行 hash（Worker）→ 列表对齐（Patience/Myers 行级，或简单 LCS 在行序列上 **分块**）。  
2. 得到 **hunk 目录**：`[{left:[a,b], right:[c,d]}]`，UI 显示「变更列表」可跳转。  
3. 用户跳到 hunk 时，只对 **该 hunk ± 上下文 K 行** 开 Monaco Diff（小窗口全文）。

**轨 2：连贯阅读（窗口 Diff）**

1. 视口仍用滑动窗口同步两侧（共同滚动策略：锁「逻辑行锚点」）。  
2. 仅对 **当前窗口交集** 跑 DiffEditor 或内联 diff。  
3. 跨窗口的 accept：通过 **全局行号** 把 snippet 应用到服务端或客户端 full buffer 策略：

| 编辑策略 | 说明 |
|----------|------|
| **整文件写回** | 若本会话曾全量加载或服务端有 patch API：`PUT` 或 `PATCH` 带 range |
| **range PUT**（推荐新增） | `PUT work/file-range { start_line, end_line, content }` 服务端 splice |

**accept 与真源：** 继续遵循 comparer-preview-hardening——拉取文本来自当前对照缓冲；大文件缓冲只含窗口时，**accept 必须带绝对行号并向服务端 range 写入**，不能 `put` 残缺全文。

---

## 5. 「更好 / 更系统」的补充方案

### 5.1 变更地图 + 局部 Diff（强烈推荐作 L 默认）

比「超长双边 DiffEditor 硬撑」更接近 VS Code/IDE 对超大 diff 的做法：

- 顶部/侧栏：**Hunk list**（统计 + 过滤）  
- 主区：只渲染 **当前 hunk 上下文**  
- 「在全文中打开」：再进编辑器窗口模式  

### 5.2 搜索与跳转

- `GET file-search?q=` 或客户端只在已加载窗口搜 + 「全文件搜索」异步任务  
- `Ctrl+G` 行号 → 先 seek slice 再定位  

### 5.3 二进制 / 伪文本

- 超过阈值：默认不进 Monaco，提示下载或十六进制/只读前缀  

### 5.4 内存预算

- 每项目打开 Tab 的窗口缓存 **总字节上限**（如 32–64 MiB），超出 LRU 关闭非焦点缓冲  

### 5.5 与 autosave

- 脏区只记 **编辑过的行范围**；autoSave 用 range PUT，避免无改动大文件回写  

---

## 6. 实施步骤（可执行）

### Step 0 — 度量与门槛（0.5–1d）

- [ ] 统计典型卡顿：打开 10k/50k 行的 TTI、内存、`buildDiffUnits` 耗时  
- [ ] 落地 `file-meta`（size/lines）到 open 路径  
- [ ] 设置项：`largeFileMode: auto | full | window`  

### Step A — 低成本开关（L0，0.5–1d）〔P0 体验〕

- [ ] 行数/体积超 M：默认 `diffAlgorithm: 'legacy'`、禁用开局 sentence unit  
- [ ] unit 构建 `requestIdleCallback` + 上限（如前 200 hunk）  
- [ ] 比较器箭头只渲染 **视口附近** hunk  

**验收：** 10k 行打开主线程 long task &lt; 基线 50%。

### Step B — Slice API（L1，1–2d）〔P0 数据〕

- [ ] `file-meta` / `file-slice`（work + zone + git show-slice）  
- [ ] 单测：边界行、超限 422、path 安全  

### Step C — 编辑器窗口加载（L2，2–3d）〔P1〕

- [ ] `TextWindowStore`：按视口 prefetch（后文 1H、前文 1H）  
- [ ] 模式 A 接入单文件 Editor Tab  
- [ ] 跳转行号、status 显示「已加载 L–R / 共 N」  

**验收：** 50k 行可滚动浏览，内存远低于全文。

### Step D — 比较器分块（L3，3–5d）〔P0 比较〕

- [ ] Worker 行 hash 粗 diff → hunk index UI  
- [ ] 点击 hunk → 局部 Diff 会话（小 buffer）  
- [ ] accept → `file-range` PUT + 真源 snippet  

**验收：** 两侧 30k 行可浏览变更列表并完成单 hunk 拉取，无整页冻死。

### Step E — range 写回与 autosave（1–2d）〔P0 正确性〕

- [ ] `PUT work/file-range`  
- [ ] dirty 区间合并；autoSave 走 range  
- [ ] 与 undo 策略文档化（range undo 或整文件 snapshot 继续）  

### Step F — 可选增强（P2）

- [ ] 模式 B 虚拟高度  
- [ ] WASM diff  
- [ ] 全文件后台 index 任务进度条  

---

## 7. 与「按需更多计算资源」的对应关系

| 诉求 | 方案位置 |
|------|----------|
| 浏览器/框架加速 | §4.1 Worker、idle、算法降级 |
| 动态加载目标区 + 后文 1× + 前文 1× | §4.3 Prefetch（默认） |
| 行粒度 | 全程以 line 为 API 与窗口单位 |
| 更系统 | §5 变更地图 + 局部 Diff + range PUT |

---

## 8. 风险与非目标

| 风险 | 缓解 |
|------|------|
| 窗口未加载就 accept 写坏文件 | 强制 range API；缺行时先补全再写 |
| Diff 行错位（两侧窗口不同步） | 粗索引锚点 + 禁止跨未加载区 fine diff |
| word wrap + 虚拟高度不准 | 大文件默认关 wrap |
| 服务端缺 line index 首次慢 | 缓存 offset 表；异步建索引 |

**非目标（本方案不做）：** 多用户 OT；服务端流式 SSE 全文；替代 Monaco 的自研编辑器。

---

## 9. 完成定义（分阶段）

| 阶段 | DoD |
|------|-----|
| **A** | 大文件打开明显减轻；无错误写回 |
| **B+C** | 50k 行可滑览；meta/slice 测通 |
| **D+E** | 大文件比较可导航 + 可安全拉取/保存 |
| **声称** | 文档写清「全量 Diff 仅用于 S/M」 |

---

## 10. 文件触点（未来实现）

| 层 | 路径 |
|----|------|
| API | `routes.py` slice/meta/range；`workspace_fs` line seek |
| Web store | 新 `textWindow.ts`；`project.ts` open 分流 |
| UI | `MonacoDiff.vue` 选项；可选 `HunkNav.vue` |
| Worker | `apps/web/src/workers/lineHash.ts` |
| 设置 | `settings.largeFileMode` |

---

## 11. 建议排期（摘要）

1. **先 A**（一周内可感）  
2. **再 B+C**（浏览长文件）  
3. **然后 D+E**（比较器才真正可用）  
4. F 视资源  

---

## 12. 决策待确认（实施前可选）

若产品拍板，请勾：

- [ ] L 默认 **变更地图** 还是 **双边窗口 Diff**？  
- [ ] 大文件是否允许 **编辑** 还是默认只读？  
- [ ] Prefetch 是否严格 **后 1H 再 前 1H**，还是 **双向同时**？  

（未勾选时实现默认：**变更地图 + 局部 Diff**、**可编辑但 range 写**、**先后再前** 如你所述。）
